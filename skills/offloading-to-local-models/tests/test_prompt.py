import re, unittest
from tests.base import sample_task
from offload.prompt import build_prompt, SYSTEM_PROMPT

TEMPLATE = "File: {target_path}\nSpec: {spec}\nCriteria:\n{acceptance_criteria}\nVerify: {verify_command}\n"

class TestPrompt(unittest.TestCase):
    def test_system_forbids_diffs(self):
        low = SYSTEM_PROMPT.lower()
        self.assertIn("complete", low)
        self.assertIn("never", low)
        self.assertIn("diff", low)
        self.assertIn("patch", low)
        self.assertIn("elision", low)
        self.assertIn("fence", low)

    def test_build_injects_fields(self):
        t = sample_task(target_files=["src/util.py"],
                        acceptance_criteria=["lowercases", "spaces to hyphens"])
        out = build_prompt(t, TEMPLATE)
        self.assertIn("src/util.py", out)
        self.assertIn("lowercases", out)
        self.assertIn("spaces to hyphens", out)
        self.assertIn(t["verify_command"], out)

    def test_no_leftover_placeholders(self):
        out = build_prompt(sample_task(), TEMPLATE)
        self.assertNotRegex(out, r"\{[a-z_]+\}")
