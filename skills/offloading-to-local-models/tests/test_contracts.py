import json, unittest
from pathlib import Path
from tests.base import TmpProjectTestCase
from offload import contracts

class TestContracts(TmpProjectTestCase):
    def test_defaults_present(self):
        c = contracts.DEFAULT_CONFIG
        self.assertEqual(c["workhorse_model"], "qwen2.5-coder:14b")
        self.assertEqual(c["quality_model"], "ornith:35b-q4_K_M")
        self.assertEqual(c["num_ctx"], 32768)
        self.assertEqual(c["keep_alive"], "30m")
        self.assertEqual(c["concurrency"], 1)
        self.assertEqual(c["line_threshold"], 150)
        self.assertIn("boilerplate", c["allowed_categories"])

    def test_load_config_defaults_when_absent(self):
        cfg = contracts.load_config(self.project_dir)
        self.assertEqual(cfg["num_ctx"], 32768)

    def test_load_config_merges_override(self):
        off = self.project_dir / ".offload"
        off.mkdir(parents=True, exist_ok=True)
        (off / "config.json").write_text(json.dumps({"concurrency": 2}))
        cfg = contracts.load_config(self.project_dir)
        self.assertEqual(cfg["concurrency"], 2)        # overridden
        self.assertEqual(cfg["num_ctx"], 32768)         # default preserved

    def test_result_schema_shape(self):
        s = contracts.RESULT_SCHEMA
        self.assertEqual(s["type"], "object")
        self.assertIn("files", s["properties"])
        self.assertIn("confidence", s["required"])

    def test_db_schema_creates_jobs(self):
        self.assertIn("CREATE TABLE", contracts.DB_SCHEMA.upper())
        for col in ("task_id", "status", "payload", "result", "verify_passed",
                    "attempts", "latency_ms", "files_written"):
            self.assertIn(col, contracts.DB_SCHEMA)
