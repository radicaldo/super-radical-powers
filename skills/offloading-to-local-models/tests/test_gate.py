from tests.base import TmpProjectTestCase, sample_task
from offload.gate import evaluate, ELIGIBLE, INELIGIBLE, NEEDS_REVIEW
from offload import contracts

CFG = contracts.DEFAULT_CONFIG

class TestGate(TmpProjectTestCase):
    def test_eligible_basic(self):
        self.assertEqual(evaluate(sample_task(category="utility"), CFG).verdict, ELIGIBLE)

    def test_hint_false_blocks(self):
        self.assertEqual(evaluate(sample_task(offload_eligible=False), CFG).verdict, INELIGIBLE)

    def test_requires_verify(self):
        self.assertEqual(evaluate(sample_task(verify_command=""), CFG).verdict, INELIGIBLE)

    def test_single_file_only(self):
        t = sample_task(target_files=["a.py", "b.py"])
        self.assertEqual(evaluate(t, CFG).verdict, INELIGIBLE)

    def test_large_modify_blocked(self):
        t = sample_task(is_modify=True, max_existing_lines=500)
        self.assertEqual(evaluate(t, CFG).verdict, INELIGIBLE)

    def test_small_modify_ok(self):
        t = sample_task(is_modify=True, max_existing_lines=40, category="docstring")
        self.assertEqual(evaluate(t, CFG).verdict, ELIGIBLE)

    def test_excluded_category(self):
        self.assertEqual(evaluate(sample_task(category="security"), CFG).verdict, INELIGIBLE)

    def test_unknown_category_needs_review(self):
        self.assertEqual(evaluate(sample_task(category=None), CFG).verdict, NEEDS_REVIEW)

    def test_hint_true_trusts_category(self):
        t = sample_task(category=None, offload_eligible=True)
        self.assertEqual(evaluate(t, CFG).verdict, ELIGIBLE)

    def test_reason_present(self):
        self.assertTrue(evaluate(sample_task(offload_eligible=False), CFG).reason)

    def test_hint_true_does_not_bypass_verify(self):
        t = sample_task(offload_eligible=True, verify_command="")
        self.assertEqual(evaluate(t, CFG).verdict, INELIGIBLE)

    def test_hint_true_does_not_bypass_single_file(self):
        t = sample_task(offload_eligible=True, target_files=["a.py", "b.py"])
        self.assertEqual(evaluate(t, CFG).verdict, INELIGIBLE)

    def test_hint_true_does_not_bypass_excluded_category(self):
        t = sample_task(offload_eligible=True, category="security")
        self.assertEqual(evaluate(t, CFG).verdict, INELIGIBLE)

    def test_hint_true_does_not_bypass_large_modify(self):
        t = sample_task(offload_eligible=True, is_modify=True, max_existing_lines=500)
        self.assertEqual(evaluate(t, CFG).verdict, INELIGIBLE)
