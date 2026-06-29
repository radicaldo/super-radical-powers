import json, unittest
from tests.fake_ollama import fake_ollama
from offload.ollama_client import generate, health_check, OllamaError
from offload import contracts

ENVELOPE = json.dumps({"files": [{"path": "src/util.py", "content": "x=1\n"}], "confidence": "high"})

class TestClient(unittest.TestCase):
    def test_generate_parses_envelope_and_request(self):
        with fake_ollama(chat_content=ENVELOPE) as (url, srv):
            r = generate(base_url=url, model="qwen2.5-coder:14b", system="sys",
                         prompt="do it", schema=contracts.RESULT_SCHEMA,
                         num_ctx=32768, keep_alive="30m", timeout_s=10)
            self.assertEqual(r.envelope["files"][0]["path"], "src/util.py")
            self.assertEqual(r.prompt_tokens, 11)
            self.assertEqual(r.completion_tokens, 22)
            self.assertGreaterEqual(r.latency_ms, 0)
            body = srv.captured["body"]
            self.assertFalse(body["stream"])
            self.assertEqual(body["options"]["num_ctx"], 32768)
            self.assertEqual(body["keep_alive"], "30m")
            self.assertEqual(body["format"], contracts.RESULT_SCHEMA)

    def test_bad_json_raises(self):
        with fake_ollama(chat_content="not json") as (url, srv):
            with self.assertRaises(OllamaError):
                generate(base_url=url, model="m", system="s", prompt="p",
                         schema=contracts.RESULT_SCHEMA, num_ctx=32768,
                         keep_alive="30m", timeout_s=10)

    def test_health_check(self):
        with fake_ollama(tags_ok=True) as (url, srv):
            self.assertTrue(health_check(url, timeout_s=5))
        with fake_ollama(tags_ok=False) as (url, srv):
            self.assertFalse(health_check(url, timeout_s=5))
