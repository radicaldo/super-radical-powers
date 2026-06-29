from pathlib import Path
import json

PENDING, RUNNING, DONE, ERROR = "pending", "running", "done", "error"

DEFAULT_CONFIG: dict = {
    "workhorse_model": "qwen2.5-coder:14b",
    "quality_model": "ornith:35b-q4_K_M",
    "base_url": "http://localhost:11434",
    "concurrency": 1,
    "num_ctx": 32768,
    "keep_alive": "30m",
    "timeout_s": 300,
    "max_attempts": 2,
    "line_threshold": 150,
    "allowed_categories": ["boilerplate", "config", "fixture",
                            "format-conversion", "docstring",
                            "test-scaffold", "utility", "regex"],
    "excluded_categories": ["security", "algorithmic", "concurrency",
                             "architecture", "migration"],
}

RESULT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "files": {"type": "array", "items": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]}},
        "notes": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["files", "confidence"],
}

DB_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  payload TEXT NOT NULL,
  result TEXT,
  verify_passed INTEGER,
  error TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  model TEXT,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  latency_ms INTEGER,
  files_written TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""

def offload_dir(project_dir: Path) -> Path:
    return Path(project_dir) / ".offload"

def load_config(project_dir: Path) -> dict:
    """Return DEFAULT_CONFIG shallow-merged with <project>/.offload/config.json if present."""
    cfg = dict(DEFAULT_CONFIG)
    f = offload_dir(project_dir) / "config.json"
    if f.exists():
        cfg.update(json.loads(f.read_text()))
    return cfg
