import json
from pathlib import Path
from tests.base import TmpProjectTestCase
from offload.queue import JobQueue
from offload import contracts, runner
from offload.ollama_client import GenerationResult

class TestRunner(TmpProjectTestCase):
    def _job(self, q, path, verify_ok=True):
        vc = 'python -c "import sys;sys.exit(0)"' if verify_ok else 'python -c "import sys;sys.exit(1)"'
        return q.enqueue({"task_id":"1","target_files":[path],"spec":"s",
                          "acceptance_criteria":[],"verify_command":vc,
                          "model": contracts.DEFAULT_CONFIG["workhorse_model"]})

    def test_pass_writes_file(self):
        q = JobQueue(self.project_dir / "q.db")
        jid = self._job(q, "src/util.py", verify_ok=True)
        job = q.claim_next()
        gen = lambda **kw: GenerationResult(
            {"files":[{"path":"src/util.py","content":"VALUE=1\n"}],"confidence":"high"}, "m",1,2,5)
        runner.process_job(job, config=contracts.load_config(self.project_dir),
                           project_dir=self.project_dir, queue=q, client_generate=gen)
        self.assertEqual((self.project_dir/"src/util.py").read_text(), "VALUE=1\n")
        self.assertEqual(q.get(jid)["status"], contracts.DONE)
        self.assertEqual(q.get(jid)["verify_passed"], 1)

    def test_fail_removes_created_file_and_requeues(self):
        q = JobQueue(self.project_dir / "q.db")
        jid = self._job(q, "src/new.py", verify_ok=False)
        job = q.claim_next()
        gen = lambda **kw: GenerationResult(
            {"files":[{"path":"src/new.py","content":"bad\n"}],"confidence":"low"}, "m",1,2,5)
        runner.process_job(job, config=contracts.load_config(self.project_dir),
                           project_dir=self.project_dir, queue=q, client_generate=gen)
        self.assertFalse((self.project_dir/"src/new.py").exists())   # tree clean
        self.assertEqual(q.get(jid)["status"], contracts.PENDING)    # requeued (attempt 1 < 2)

    def test_fail_restores_modified_file(self):
        q = JobQueue(self.project_dir / "q.db")
        target = self.project_dir / "src/exists.py"
        target.parent.mkdir(parents=True); target.write_text("ORIGINAL\n")
        jid = self._job(q, "src/exists.py", verify_ok=False)
        job = q.claim_next()
        gen = lambda **kw: GenerationResult(
            {"files":[{"path":"src/exists.py","content":"CLOBBERED\n"}],"confidence":"low"}, "m",1,2,5)
        cfg = contracts.load_config(self.project_dir); cfg["max_attempts"] = 1
        runner.process_job(job, config=cfg, project_dir=self.project_dir, queue=q, client_generate=gen)
        self.assertEqual(target.read_text(), "ORIGINAL\n")            # restored
        self.assertEqual(q.get(jid)["status"], contracts.ERROR)

    def test_worker_drains_then_exits(self):
        q = JobQueue(self.project_dir / "q.db")
        self._job(q, "src/a.py", verify_ok=True)
        gen = lambda **kw: GenerationResult(
            {"files":[{"path":"src/a.py","content":"A=1\n"}],"confidence":"high"}, "m",1,2,5)
        runner.run_worker(config=contracts.load_config(self.project_dir),
                          project_dir=self.project_dir, concurrency=1,
                          idle_timeout=1, poll=0.1, client_generate=gen,
                          db_path=self.project_dir/"q.db")
        self.assertEqual(q.count_pending(), 0)

    def test_multifile_verify_fail_restores_tree(self):
        """
        CRITICAL 1 guard: envelope with a brand-new file AND a modification of an
        existing file, where verify FAILS.  After process_job:
          - the new file must be absent (tree clean)
          - the existing file must be restored byte-for-byte
          - the job must be requeued (attempt 1 < max_attempts=2)
        """
        q = JobQueue(self.project_dir / "q.db")

        # Pre-create the existing file
        existing = self.project_dir / "src/existing.py"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text("ORIGINAL\n")

        # Enqueue a job that will fail verify
        vc = 'python -c "import sys;sys.exit(1)"'
        jid = q.enqueue({
            "task_id": "multi",
            "target_files": ["src/existing.py", "src/brand_new.py"],
            "spec": "s",
            "acceptance_criteria": [],
            "verify_command": vc,
            "model": contracts.DEFAULT_CONFIG["workhorse_model"],
        })
        job = q.claim_next()

        # gen returns a 2-file envelope: modifies existing + creates brand-new
        def gen(**kw):
            return GenerationResult(
                {
                    "files": [
                        {"path": "src/existing.py", "content": "CLOBBERED\n"},
                        {"path": "src/brand_new.py", "content": "NEW\n"},
                    ],
                    "confidence": "low",
                },
                "m", 1, 2, 5,
            )

        cfg = contracts.load_config(self.project_dir)
        runner.process_job(job, config=cfg, project_dir=self.project_dir,
                           queue=q, client_generate=gen)

        # brand-new file must be gone
        self.assertFalse((self.project_dir / "src/brand_new.py").exists(),
                         "brand-new file should be removed after verify failure")
        # existing file must be restored
        self.assertEqual(existing.read_text(), "ORIGINAL\n",
                         "existing file must be restored byte-for-byte")
        # job requeued (attempt 1, max_attempts default 2)
        self.assertEqual(q.get(jid)["status"], contracts.PENDING,
                         "job should be requeued after first verify failure")

    def test_out_of_tree_path_rejected(self):
        """
        Security guard: if the model returns a path that escapes the project tree
        (e.g. '../escape.py'), no file must be written and the job must NOT be DONE.
        """
        q = JobQueue(self.project_dir / "q.db")
        vc = 'python -c "import sys;sys.exit(0)"'
        jid = q.enqueue({
            "task_id": "evil",
            "target_files": ["src/safe.py"],
            "spec": "s",
            "acceptance_criteria": [],
            "verify_command": vc,
            "model": contracts.DEFAULT_CONFIG["workhorse_model"],
        })
        job = q.claim_next()

        # Inject a gen that returns a malicious out-of-tree path
        gen = lambda **kw: GenerationResult(
            {"files": [{"path": "../escape.py", "content": "x=1\n"}], "confidence": "high"},
            "m", 1, 2, 5,
        )

        runner.process_job(
            job,
            config=contracts.load_config(self.project_dir),
            project_dir=self.project_dir,
            queue=q,
            client_generate=gen,
        )

        # The escape file must NOT exist in the parent directory
        escape_path = self.project_dir.parent / "escape.py"
        self.assertFalse(escape_path.exists(),
                         "out-of-tree file must not be written")

        # The job must NOT be DONE
        status = q.get(jid)["status"]
        self.assertNotEqual(status, contracts.DONE,
                            f"job reached DONE despite out-of-tree path (status={status!r})")

    def test_concurrent_worker_drains_all_jobs(self):
        """
        CRITICAL 2 guard: concurrency=2 worker drains all 3 enqueued jobs.
        Each job writes a distinct file; gen returns the correct content per path.
        After run_worker: count_pending()==0 and all 3 jobs are DONE.
        """
        db_path = self.project_dir / "q.db"
        q = JobQueue(db_path)

        paths = ["src/a.py", "src/b.py", "src/c.py"]
        contents = {"src/a.py": "A=1\n", "src/b.py": "B=2\n", "src/c.py": "C=3\n"}
        jids = []
        for p in paths:
            vc = 'python -c "import sys;sys.exit(0)"'
            jid = q.enqueue({
                "task_id": p,
                "target_files": [p],
                "spec": "s",
                "acceptance_criteria": [],
                "verify_command": vc,
                "model": contracts.DEFAULT_CONFIG["workhorse_model"],
            })
            jids.append(jid)

        # gen inspects prompt to figure out which file is being targeted.
        # For simplicity: use a counter-free approach — each call returns an envelope
        # for the path mentioned in the user prompt (payload target_files[0]).
        # Because process_job builds the prompt from payload["target_files"],
        # we can extract the path from prompt kwarg.
        import re

        def gen(**kw):
            prompt_text = kw.get("prompt", "")
            # target_files appear in the prompt; match the first src/... path
            match = re.search(r"src/[a-z]\.py", prompt_text)
            if match:
                p = match.group(0)
                content = contents.get(p, "X=0\n")
            else:
                # fallback: return first path
                p = paths[0]
                content = contents[p]
            return GenerationResult(
                {"files": [{"path": p, "content": content}], "confidence": "high"},
                "m", 1, 2, 5,
            )

        runner.run_worker(
            config=contracts.load_config(self.project_dir),
            project_dir=self.project_dir,
            concurrency=2,
            idle_timeout=2,
            poll=0.05,
            client_generate=gen,
            db_path=db_path,
        )

        # All jobs must be DONE with none pending
        self.assertEqual(q.count_pending(), 0, "no jobs should remain pending")
        for jid in jids:
            job_rec = q.get(jid)
            self.assertEqual(job_rec["status"], contracts.DONE,
                             f"job {jid} should be DONE, got {job_rec['status']}")
