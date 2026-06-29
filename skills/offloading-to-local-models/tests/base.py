import shutil, tempfile, unittest
from pathlib import Path

class TmpProjectTestCase(unittest.TestCase):
    """Base case giving each test an isolated temp 'project' directory."""
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="offload-test-"))
        self.project_dir = self._tmp
    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

def sample_task(**over):
    """A minimal eligible task dict; override fields per test."""
    t = {
        "task_id": "1",
        "target_files": ["src/util.py"],
        "verify_command": "python -c \"import sys; sys.exit(0)\"",
        "spec": "Implement slugify(s)->str.",
        "acceptance_criteria": ["lowercases", "spaces to hyphens"],
        "offload_eligible": None,   # hint absent
        "category": "utility",
        "is_modify": False,
        "max_existing_lines": None,
    }
    t.update(over)
    return t
