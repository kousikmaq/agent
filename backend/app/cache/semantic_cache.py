from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from functools import lru_cache

from app.config import CACHE_DB, DATA_DIR

_WS = re.compile(r"\s+")


def _normalize(query: str) -> str:
    return _WS.sub(" ", (query or "").strip().lower())


@lru_cache(maxsize=1)
def _data_version() -> str:
    """Hash of the dataset's file modification times; changes when data is regenerated."""
    parts = []
    for fname in sorted(os.listdir(DATA_DIR)):
        if fname.endswith(".csv"):
            parts.append(f"{fname}:{os.path.getmtime(os.path.join(DATA_DIR, fname)):.0f}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


class SemanticCache:
    def __init__(self, db_path: str = CACHE_DB) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key         TEXT PRIMARY KEY,
                    namespace   TEXT NOT NULL,
                    query       TEXT NOT NULL,
                    response    TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    created_at  REAL NOT NULL,
                    hits        INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def _key(self, query: str, namespace: str) -> str:
        raw = f"{namespace}::{_data_version()}::{_normalize(query)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, query: str, namespace: str = "default") -> dict | None:
        key = self._key(query, namespace)
        with self._connect() as conn:
            row = conn.execute("SELECT response FROM cache WHERE key = ?", (key,)).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE cache SET hits = hits + 1 WHERE key = ?", (key,))
        try:
            return json.loads(row["response"])
        except json.JSONDecodeError:
            return None

    def set(self, query: str, response: dict, namespace: str = "default") -> None:
        key = self._key(query, namespace)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cache (key, namespace, query, response, data_version, created_at, hits)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(key) DO UPDATE SET response = excluded.response,
                    created_at = excluded.created_at
                """,
                (key, namespace, query, json.dumps(response), _data_version(), time.time()),
            )

    def stats(self) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(hits), 0) AS hits FROM cache"
            ).fetchone()
        return {"entries": row["n"], "total_hits": row["hits"], "data_version": _data_version()}

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM cache")


@lru_cache(maxsize=1)
def get_cache() -> SemanticCache:
    return SemanticCache()
