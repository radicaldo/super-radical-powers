import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from offload import contracts


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobQueue:
    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, isolation_level=None)  # autocommit; explicit txns
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.executescript(contracts.DB_SCHEMA)

    def journal_mode(self) -> str:
        return self.conn.execute("PRAGMA journal_mode;").fetchone()[0]

    def enqueue(self, payload: dict) -> int:
        now = _now()
        # Extract task_id from payload or use empty string if not present
        task_id = payload.get("task_id", "")
        cur = self.conn.execute(
            "INSERT INTO jobs (task_id, status, payload, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?);",
            (task_id, contracts.PENDING, json.dumps(payload), now, now),
        )
        return cur.lastrowid

    def claim_next(self) -> Optional[dict]:
        cur = self.conn.cursor()
        cur.execute("BEGIN IMMEDIATE;")
        try:
            row = cur.execute(
                "SELECT id FROM jobs WHERE status=? ORDER BY id LIMIT 1;",
                (contracts.PENDING,),
            ).fetchone()
            if row is None:
                cur.execute("COMMIT;")
                return None
            jid = row["id"]
            cur.execute(
                "UPDATE jobs SET status=?, attempts=attempts+1, updated_at=? "
                "WHERE id=? AND status=?;",
                (contracts.RUNNING, _now(), jid, contracts.PENDING),
            )
            cur.execute("COMMIT;")
        except Exception:
            cur.execute("ROLLBACK;")
            raise
        return self.get(jid)

    def complete(
        self,
        job_id: int,
        *,
        result: dict,
        verify_passed: bool,
        files_written: list,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
    ) -> None:
        self.conn.execute(
            "UPDATE jobs SET status=?, result=?, verify_passed=?, files_written=?, "
            "model=?, prompt_tokens=?, completion_tokens=?, latency_ms=?, updated_at=? "
            "WHERE id=?;",
            (
                contracts.DONE,
                json.dumps(result),
                1 if verify_passed else 0,
                json.dumps(files_written),
                model,
                prompt_tokens,
                completion_tokens,
                latency_ms,
                _now(),
                job_id,
            ),
        )

    def fail(self, job_id: int, error: str) -> None:
        self.conn.execute(
            "UPDATE jobs SET status=?, error=?, updated_at=? WHERE id=?;",
            (contracts.ERROR, error, _now(), job_id),
        )

    def requeue(self, job_id: int) -> None:
        self.conn.execute(
            "UPDATE jobs SET status=?, error=NULL, updated_at=? WHERE id=?;",
            (contracts.PENDING, _now(), job_id),
        )

    def _row_to_dict(self, row) -> Optional[dict]:
        if row is None:
            return None
        d = dict(row)
        # Parse JSON fields
        if d.get("payload") is not None:
            d["payload"] = json.loads(d["payload"])
        if d.get("result") is not None:
            d["result"] = json.loads(d["result"])
        else:
            d["result"] = None
        if d.get("files_written") is not None:
            d["files_written"] = json.loads(d["files_written"])
        else:
            d["files_written"] = []
        return d

    def get(self, job_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM jobs WHERE id=?;", (job_id,)
        ).fetchone()
        return self._row_to_dict(row)

    def list(self, status: Optional[str] = None) -> list:
        if status is None:
            rows = self.conn.execute("SELECT * FROM jobs ORDER BY id;").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM jobs WHERE status=? ORDER BY id;", (status,)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count_pending(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status=?;", (contracts.PENDING,)
        ).fetchone()
        return row[0]

    def close(self) -> None:
        self.conn.close()
