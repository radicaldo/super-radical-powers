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
