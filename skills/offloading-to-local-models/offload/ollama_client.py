import json, time, urllib.request, urllib.error
from dataclasses import dataclass


class OllamaError(Exception):
    pass


@dataclass
class GenerationResult:
    envelope: dict
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


def generate(*, base_url, model, system, prompt, schema,
             num_ctx, keep_alive, timeout_s) -> GenerationResult:
    """POST <base_url>/api/chat with:
      {"model": model,
       "messages": [{"role":"system","content":system},{"role":"user","content":prompt}],
       "stream": False, "format": schema,
       "options": {"num_ctx": num_ctx}, "keep_alive": keep_alive}
    Measure latency around the request. Parse the response JSON; take
    resp["message"]["content"], json.loads it into `envelope`; read
    resp.get("prompt_eval_count",0) and resp.get("eval_count",0) as token counts;
    resp.get("model", model) as model. Wrap ANY failure (urllib.error.URLError,
    socket timeout, HTTPError, KeyError, json.JSONDecodeError) in OllamaError."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": schema,
        "options": {"num_ctx": num_ctx},
        "keep_alive": keep_alive,
    }
    url = f"{base_url}/api/chat"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
        latency_ms = int((time.monotonic() - start) * 1000)
        data = json.loads(raw)
        envelope = json.loads(data["message"]["content"])
        return GenerationResult(
            envelope=envelope,
            model=data.get("model", model),
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            latency_ms=latency_ms,
        )
    except (urllib.error.URLError, urllib.error.HTTPError,
            KeyError, json.JSONDecodeError, OSError) as exc:
        raise OllamaError(str(exc)) from exc


def health_check(base_url, timeout_s=5) -> bool:
    """GET <base_url>/api/tags; return True on HTTP 200, False on ANY error (never raise)."""
    url = f"{base_url}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            return resp.status == 200
    except Exception:
        return False
