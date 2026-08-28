from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from pathlib import Path

from .errors import StorageConflictError
from .model import ObservationToken, ReasoningNode


class SQLiteStore:
    def __init__(self, path: str | Path = ".freshctx/freshctx.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS objects (id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL)")
        self.db.commit()

    def put_observation(self, token: ObservationToken) -> None:
        self._put(token.id, "observation", asdict(token))

    def put_reasoning(self, node: ReasoningNode) -> None:
        payload = asdict(node); payload["dependencies"] = list(node.dependencies)
        self._put(node.id, "reasoning", payload)

    def _put(self, object_id: str, kind: str, payload: dict) -> None:
        encoded = json.dumps(payload, sort_keys=True)
        with self._lock:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                existing = self.db.execute("SELECT kind, payload FROM objects WHERE id = ?", (object_id,)).fetchone()
                if existing is None:
                    self.db.execute("INSERT INTO objects VALUES (?, ?, ?)", (object_id, kind, encoded))
                elif existing != (kind, encoded):
                    raise StorageConflictError(f"immutable FreshCtx object ID conflict: {object_id}")
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

    def get(self, object_id: str) -> ObservationToken | ReasoningNode | None:
        with self._lock:
            row = self.db.execute("SELECT kind, payload FROM objects WHERE id = ?", (object_id,)).fetchone()
        if row is None: return None
        kind, raw = row; value = json.loads(raw)
        if kind == "observation": return ObservationToken(**value)
        value["dependencies"] = tuple(value["dependencies"])
        return ReasoningNode(**value)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            self.db.close()


class MemoryStore:
    def __init__(self) -> None: self.objects: dict[str, object] = {}; self._lock = threading.RLock()
    def _put(self, value: object) -> None:
        with self._lock:
            existing = self.objects.get(value.id)
            if existing is not None and existing != value:
                raise StorageConflictError(f"immutable FreshCtx object ID conflict: {value.id}")
            self.objects[value.id] = value
    def put_observation(self, token: ObservationToken) -> None: self._put(token)
    def put_reasoning(self, node: ReasoningNode) -> None: self._put(node)
    def get(self, object_id: str):
        with self._lock: return self.objects.get(object_id)
