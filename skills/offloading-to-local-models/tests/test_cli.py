import io, json, contextlib
from pathlib import Path
from tests.base import TmpProjectTestCase, sample_task
from offload import cli, contracts
from offload.queue import JobQueue

def run_cli(args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(args)
    return rc, buf.getvalue()

class TestCli(TmpProjectTestCase):
    def test_enqueue_then_status(self):
        job = {"task_id":"1","target_files":["src/util.py"],"verify_command":"true","spec":"s"}
        jf = self.project_dir/"job.json"; jf.write_text(json.dumps(job))
        rc, out = run_cli(["--project", str(self.project_dir), "enqueue", "--file", str(jf)])
        self.assertEqual(rc, 0)
        jid = int(out.strip())
        rc, out = run_cli(["--project", str(self.project_dir), "status", "--job-id", str(jid)])
        self.assertEqual(json.loads(out)["status"], contracts.PENDING)

    def test_gate_prints_verdict(self):
        tf = self.project_dir/"task.json"; tf.write_text(json.dumps(sample_task(category="utility")))
        rc, out = run_cli(["--project", str(self.project_dir), "gate", "--task", str(tf)])
        self.assertEqual(json.loads(out)["verdict"], "eligible")
