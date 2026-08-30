from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from pathlib import Path

from .errors import StorageConflictError, StorageCorruptionError, StorageMigrationError
from .model import ObservationToken, ReasoningNode


SCHEMA_VERSION = 1


class SQLiteStore:
    def __init__(self, path: str | Path = ".freshctx/freshctx.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
            self._verify_integrity()
            self._migrate()
        except (StorageCorruptionError, StorageMigrationError):
            self.db.close()
            raise
        except sqlite3.DatabaseError as exc:
            self.db.close()
            raise StorageCorruptionError(f"invalid FreshCtx SQLite store: {self.path}") from exc

    def _verify_integrity(self) -> None:
        result = self.db.execute("PRAGMA quick_check").fetchone()
        if result is None or result[0] != "ok":
            raise StorageCorruptionError(f"FreshCtx SQLite integrity check failed: {result}")

    def _migrate(self) -> None:
        """Apply forward-only, transactional schema migrations."""
        try:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS freshctx_schema "
                "(singleton INTEGER PRIMARY KEY CHECK (singleton = 1), version INTEGER NOT NULL)"
            )
            row = self.db.execute(
                "SELECT version FROM freshctx_schema WHERE singleton = 1"
            ).fetchone()
            version = 0 if row is None else int(row[0])
            if version > SCHEMA_VERSION:
                raise StorageMigrationError(
                    f"store schema {version} is newer than supported schema {SCHEMA_VERSION}"
                )
            if version < 1:
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS objects "
                    "(id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL)"
                )
                self.db.execute(
                    "INSERT OR REPLACE INTO freshctx_schema(singleton, version) VALUES (1, 1)"
                )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    @property
    def schema_version(self) -> int:
        with self._lock:
            row = self.db.execute(
                "SELECT version FROM freshctx_schema WHERE singleton = 1"
            ).fetchone()
        return int(row[0]) if row else 0

    def integrity_check(self) -> bool:
        with self._lock:
            self._verify_integrity()
        return True

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
    def __init__(self) -> None: self.objects: dict[str, ObservationToken | ReasoningNode] = {}; self._lock = threading.RLock()
    def _put(self, value: ObservationToken | ReasoningNode) -> None:
        with self._lock:
            existing = self.objects.get(value.id)
            if existing is not None and existing != value:
                raise StorageConflictError(f"immutable FreshCtx object ID conflict: {value.id}")
            self.objects[value.id] = value
    def put_observation(self, token: ObservationToken) -> None: self._put(token)
    def put_reasoning(self, node: ReasoningNode) -> None: self._put(node)
    def get(self, object_id: str):
        with self._lock: return self.objects.get(object_id)
