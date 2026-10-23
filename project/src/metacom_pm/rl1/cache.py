"""SQLite attempt claims. Interrupted work is UNKNOWN, never a free cache hit.

No automatic resend of a RUNNING/FAILED attempt. A retry needs a new attempt
identity; a new independent draw also needs a distinct request identity.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

from .schema import digest


class AttemptCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS attempts (request_id TEXT PRIMARY KEY, "
                       "payload TEXT NOT NULL, status TEXT NOT NULL, result TEXT)")

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def claim(self, request: dict) -> dict | None:
        payload = {k: v for k, v in request.items() if k != "request_id"}
        key = request["request_id"]
        if key != digest(payload):
            raise ValueError("cache key does not match the complete request")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self._transaction() as db:
            row = db.execute("SELECT payload,status,result FROM attempts WHERE request_id=?", (key,)).fetchone()
            if row:
                if row[0] != encoded:
                    raise ValueError("cache payload mismatch")
                if row[1] == "COMPLETED":
                    return json.loads(row[2])
                raise RuntimeError("unresolved/failed prior attempt; do not silently regenerate")
            db.execute("INSERT INTO attempts VALUES (?,?,'RUNNING',NULL)", (key, encoded))
        return None

    def finish(self, request_id: str, result: dict) -> None:
        if result.get("request_id") != request_id:
            raise ValueError("result request mismatch")
        completed = result.get("finish_reason") == "natural_stop" and bool(result.get("text", "").strip())
        with self._transaction() as db:
            row = db.execute("SELECT payload,status FROM attempts WHERE request_id=?", (request_id,)).fetchone()
            if not row or row[1] != "RUNNING":
                raise ValueError("no live attempt to settle")
            if result.get("runtime_identity") != json.loads(row[0])["executor_identity"]:
                raise ValueError("result runtime mismatch")
            db.execute("UPDATE attempts SET status=?,result=? WHERE request_id=?",
                ("COMPLETED" if completed else "FAILED", json.dumps(result, ensure_ascii=False), request_id))
