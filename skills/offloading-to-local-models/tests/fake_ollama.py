import json, threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

@contextmanager
def fake_ollama(chat_content="{}", *, status=200, tags_ok=True):
    """Yields (base_url, server). /api/chat returns a chat response whose
    message.content is `chat_content`. The server object captures the last
    POST request body on `server.captured['body']`."""
    captured = {}
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            self.send_response(200 if tags_ok else 500)
            self.end_headers(); self.wfile.write(b'{"models":[]}')
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            captured["body"] = json.loads(self.rfile.read(n) or b"{}")
            self.send_response(status)
            self.send_header("Content-Type", "application/json"); self.end_headers()
            body = {"model": captured["body"].get("model", "m"),
                    "message": {"role": "assistant", "content": chat_content},
                    "prompt_eval_count": 11, "eval_count": 22, "done": True}
            self.wfile.write(json.dumps(body).encode())
    srv = HTTPServer(("127.0.0.1", 0), H)
    srv.captured = captured
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}", srv
    finally:
        srv.shutdown()
