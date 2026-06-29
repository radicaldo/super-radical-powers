"""
End-to-end integration test for the offload pipeline.

Exercises the WHOLE local pipeline through run_worker with an injected fake
client_generate — no network, no Ollama required.

Two jobs are enqueued:
  Job A — src/good.py: verify_command exits 0  → ends DONE / verify_passed
  Job B — src/bad.py:  verify_command exits 1  → exhausts max_attempts=1 → ERROR
                                                  file must NOT exist (tree clean)
"""

import json
import re
import unittest
from pathlib import Path

from tests.base import TmpProjectTestCase
from offload.queue import JobQueue
from offload import contracts, runner
from offload.ollama_client import GenerationResult


GOOD_CONTENT = "def greet(): return 'hello'\n"
BAD_CONTENT  = "def broken(): ???\n"


class TestEndToEndIntegration(TmpProjectTestCase):
    """Full pipeline: two jobs, one passes, one fails, worker drains to zero pending."""

    def setUp(self):
        super().setUp()
        # Write a project-level config with max_attempts=1 so the bad job
        # exhausts its retries on the first failure instead of requeueing.
        offload_dir = self.project_dir / ".offload"
        offload_dir.mkdir(parents=True, exist_ok=True)
        (offload_dir / "config.json").write_text(
            json.dumps({"max_attempts": 1}), encoding="utf-8"
        )

    def _make_queue(self):
        db_path = self.project_dir / "q.db"
        return JobQueue(db_path), db_path

    def _enqueue_job(self, q, target_path, verify_ok=True):
        # target_path must be included in "target_files" so that build_prompt
        # embeds it via the template's {target_path} placeholder.  The injected
        # `gen` function below routes to GOOD_CONTENT or BAD_CONTENT by
        # searching for the path in the rendered prompt text — if target_path
        # were absent from "target_files", the routing re.search would miss it
        # and every job would fall through to the BAD_CONTENT branch.
        vc = (
            'python -c "import sys;sys.exit(0)"'
            if verify_ok
            else 'python -c "import sys;sys.exit(1)"'
        )
        return q.enqueue(
            {
                "task_id": target_path,
                "target_files": [target_path],
                "spec": f"Implement {target_path}.",
                "acceptance_criteria": [],
                "verify_command": vc,
                "model": contracts.DEFAULT_CONFIG["workhorse_model"],
            }
        )

    def test_end_to_end_good_and_bad_jobs(self):
        q, db_path = self._make_queue()

        jid_good = self._enqueue_job(q, "src/good.py", verify_ok=True)
        jid_bad  = self._enqueue_job(q, "src/bad.py",  verify_ok=False)

        # Injected generator: inspect prompt to determine which file is targeted.
        # Routing relies on the target path appearing in the rendered prompt via
        # the template's {target_path} placeholder.  "target_files" in the job
        # payload must contain the routable path for build_prompt to embed it;
        # see _enqueue_job above for why this matters.
        def gen(**kw):
            prompt_text = kw.get("prompt", "")
            m = re.search(r"src/(good|bad)\.py", prompt_text)
            if m and m.group(1) == "good":
                return GenerationResult(
                    {
                        "files": [{"path": "src/good.py", "content": GOOD_CONTENT}],
                        "confidence": "high",
                    },
                    "qwen2.5-coder:14b", 10, 20, 500,
                )
            else:
                # bad.py — content doesn't matter; verify will fail regardless
                return GenerationResult(
                    {
                        "files": [{"path": "src/bad.py", "content": BAD_CONTENT}],
                        "confidence": "low",
                    },
                    "qwen2.5-coder:14b", 10, 20, 500,
                )

        cfg = contracts.load_config(self.project_dir)  # picks up max_attempts=1
        runner.run_worker(
            config=cfg,
            project_dir=self.project_dir,
            concurrency=1,
            idle_timeout=2,
            poll=0.05,
            client_generate=gen,
            db_path=db_path,
        )

        # --- Outcome assertions ---

        # 1. No jobs left pending
        self.assertEqual(q.count_pending(), 0, "all jobs should be drained")

        # 2. Good job: file written with correct content, status DONE, verify_passed
        good_file = self.project_dir / "src/good.py"
        self.assertTrue(good_file.exists(), "src/good.py should exist after successful job")
        self.assertEqual(good_file.read_text(), GOOD_CONTENT)
        good_rec = q.get(jid_good)
        self.assertEqual(good_rec["status"], contracts.DONE,
                         f"good job should be DONE, got {good_rec['status']}")
        self.assertEqual(good_rec["verify_passed"], 1,
                         "good job verify_passed should be 1")

        # 3. Bad job: file must NOT exist (tree clean / restored), status ERROR
        bad_file = self.project_dir / "src/bad.py"
        self.assertFalse(bad_file.exists(),
                         "src/bad.py should NOT exist — tree must be clean after verify failure")
        bad_rec = q.get(jid_bad)
        self.assertEqual(bad_rec["status"], contracts.ERROR,
                         f"bad job should be ERROR after exhausting max_attempts=1, got {bad_rec['status']}")


if __name__ == "__main__":
    unittest.main()
