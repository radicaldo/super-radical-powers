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

    def test_gate_modify_too_large_is_ineligible(self):
        big = self.project_dir / "src" / "big.py"
        big.parent.mkdir(parents=True)
        big.write_text("\n".join(f"x{i} = 1" for i in range(200)) + "\n")  # 200 lines > default threshold 150
        task = sample_task(target_files=["src/big.py"], category="utility")  # is_modify defaults to False
        tf = self.project_dir / "task.json"; tf.write_text(json.dumps(task))
        rc, out = run_cli(["--project", str(self.project_dir), "gate", "--task", str(tf)])
        self.assertEqual(json.loads(out)["verdict"], "ineligible")  # CLI set is_modify=True + max=200 -> rule 4 blocks

    def test_gate_missing_task_file_returns_rc1(self):
        rc, out = run_cli(["--project", str(self.project_dir), "gate", "--task", str(self.project_dir / "nonexistent.json")])
        self.assertEqual(rc, 1)
