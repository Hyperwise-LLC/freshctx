from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from pathlib import Path

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
        with self._lock:
            self.db.execute("INSERT OR REPLACE INTO objects VALUES (?, ?, ?)", (object_id, kind, json.dumps(payload, sort_keys=True)))
            self.db.commit()

    def get(self, object_id: str) -> ObservationToken | ReasoningNode | None:
        with self._lock:
            row = self.db.execute("SELECT kind, payload FROM objects WHERE id = ?", (object_id,)).fetchone()
        if row is None: return None
        kind, raw = row; value = json.loads(raw)
        if kind == "observation": return ObservationToken(**value)
        value["dependencies"] = tuple(value["dependencies"])
        return ReasoningNode(**value)


class MemoryStore:
    def __init__(self) -> None: self.objects: dict[str, object] = {}; self._lock = threading.RLock()
    def put_observation(self, token: ObservationToken) -> None:
        with self._lock: self.objects[token.id] = token
    def put_reasoning(self, node: ReasoningNode) -> None:
        with self._lock: self.objects[node.id] = node
    def get(self, object_id: str):
        with self._lock: return self.objects.get(object_id)
