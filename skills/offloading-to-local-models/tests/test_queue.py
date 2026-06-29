from tests.base import TmpProjectTestCase
from offload.queue import JobQueue
from offload import contracts

class TestQueue(TmpProjectTestCase):
    def q(self):
        return JobQueue(self.project_dir / "q.db")

    def test_enqueue_and_get(self):
        q = self.q()
        jid = q.enqueue({"task_id": "1", "spec": "x"})
        job = q.get(jid)
        self.assertEqual(job["status"], contracts.PENDING)
        self.assertEqual(job["payload"]["task_id"], "1")

    def test_claim_is_exclusive(self):
        q = self.q()
        q.enqueue({"task_id": "1"})
        first = q.claim_next()
        second = q.claim_next()
        self.assertIsNotNone(first)
        self.assertEqual(first["status"], contracts.RUNNING)
        self.assertEqual(first["attempts"], 1)
        self.assertIsNone(second)  # only one pending job, already claimed

    def test_complete_records_stats(self):
        q = self.q()
        jid = q.enqueue({"task_id": "1"})
        q.claim_next()
        q.complete(jid, result={"files": [], "confidence": "high"},
                   verify_passed=True, files_written=["src/util.py"],
                   model="m", prompt_tokens=10, completion_tokens=20, latency_ms=99)
        job = q.get(jid)
        self.assertEqual(job["status"], contracts.DONE)
        self.assertEqual(job["verify_passed"], 1)
        self.assertEqual(job["files_written"], ["src/util.py"])
        self.assertEqual(job["latency_ms"], 99)

    def test_fail_and_requeue(self):
        q = self.q()
        jid = q.enqueue({"task_id": "1"})
        q.claim_next(); q.fail(jid, "boom")
        self.assertEqual(q.get(jid)["status"], contracts.ERROR)
        q.requeue(jid)
        self.assertEqual(q.get(jid)["status"], contracts.PENDING)
        self.assertEqual(q.count_pending(), 1)

    def test_wal_enabled(self):
        q = self.q()
        self.assertEqual(q.journal_mode().lower(), "wal")
