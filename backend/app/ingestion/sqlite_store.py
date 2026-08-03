"""SQLite persistence for daily factory snapshots (input layer).

A single global database (``datasets/factory.db``) stores every dated
:class:`FactoryState` keyed by ``business_date``. It mirrors the CSV snapshot
layout one-to-one - one table per :data:`CSV_REGISTRY` collection plus the
``routings`` / ``operations`` tables - and reuses the **exact same** flat-cell
codec (:mod:`app.ingestion.csv_codec`). A state loaded from SQLite is therefore
identical to the same state loaded from CSV.

The store is purely additive: CSV snapshots under ``datasets/<date>/`` are still
written, and :class:`SqliteDataSource` falls back to CSV whenever a date is not
(yet) present in the database. This guarantees the existing flow is never
disrupted while SQLite becomes the primary read source. Set
``PPO_SQLITE_ENABLED=false`` to bypass SQLite entirely (pure CSV behaviour).
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from app.config import get_settings
from app.domain.models.change_log import ChangeLog
from app.domain.models.factory_state import FactoryState
from app.domain.models.routing import Operation, Routing
from app.ingestion.base import DataSource
from app.ingestion.csv_codec import field_names, model_to_row, row_to_model
from app.ingestion.csv_schema import CSV_REGISTRY, ROUTING_HEADER_FIELDS
from app.ingestion.csv_source import CsvDataSource

_SNAPSHOTS_TABLE = "_snapshots"
_ROUTINGS_TABLE = "routings"
_OPERATIONS_TABLE = "operations"
_CHANGE_LOG_TABLE = "change_log"
_CHANGE_LOG_COLUMNS = [
    "previous_date",
    "event_id",
    "event_type",
    "entity_type",
    "entity_id",
    "description",
    "before",
    "after",
]
_DATE_COL = "business_date"
_DB_FILENAME = "factory.db"


def _quote(identifier: str) -> str:
    """Safely quote a SQL identifier (table/column name)."""
    return '"' + identifier.replace('"', '""') + '"'


class FactorySqliteStore:
    """Reads/writes dated :class:`FactoryState` snapshots in one SQLite file."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    # -- Connection ---------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _snapshot_tables(self):
        """Yield ``(table_name, model_columns)`` for every snapshot table."""
        for _filename, attribute, model_cls in CSV_REGISTRY:
            yield attribute, field_names(model_cls)
        yield _ROUTINGS_TABLE, list(ROUTING_HEADER_FIELDS)
        yield _OPERATIONS_TABLE, field_names(Operation)

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {_quote(_SNAPSHOTS_TABLE)} "
                f"({_quote(_DATE_COL)} TEXT PRIMARY KEY, created_at TEXT)"
            )
            for table, columns in self._snapshot_tables():
                col_defs = ", ".join(
                    f"{_quote(c)} TEXT" for c in [_DATE_COL, *columns]
                )
                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {_quote(table)} ({col_defs})"
                )
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS {_quote('ix_' + table + '_date')} "
                    f"ON {_quote(table)} ({_quote(_DATE_COL)})"
                )
            change_defs = ", ".join(
                f"{_quote(c)} TEXT" for c in [_DATE_COL, *_CHANGE_LOG_COLUMNS]
            )
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {_quote(_CHANGE_LOG_TABLE)} ({change_defs})"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {_quote('ix_' + _CHANGE_LOG_TABLE + '_date')} "
                f"ON {_quote(_CHANGE_LOG_TABLE)} ({_quote(_DATE_COL)})"
            )

    # -- Write side ---------------------------------------------------------
    def save_state(self, state: FactoryState) -> None:
        """Persist (replace) all rows for ``state.business_date``."""
        business_date = state.business_date
        with closing(self._connect()) as conn, conn:
            conn.execute(
                f"INSERT OR REPLACE INTO {_quote(_SNAPSHOTS_TABLE)} "
                f"({_quote(_DATE_COL)}, created_at) VALUES (?, datetime('now'))",
                (business_date,),
            )
            for _filename, attribute, model_cls in CSV_REGISTRY:
                rows = [model_to_row(item) for item in getattr(state, attribute)]
                self._replace_rows(
                    conn, attribute, field_names(model_cls), business_date, rows
                )
            self._save_routings(conn, business_date, state.routings)

    def _save_routings(
        self, conn: sqlite3.Connection, business_date: str, routings: list[Routing]
    ) -> None:
        header_rows: list[dict[str, str]] = []
        operation_rows: list[dict[str, str]] = []
        for routing in routings:
            header_rows.append(
                {
                    "routing_id": routing.routing_id,
                    "product_id": routing.product_id,
                    "version": routing.version,
                }
            )
            for operation in routing.operations:
                operation_rows.append(model_to_row(operation))
        self._replace_rows(
            conn, _ROUTINGS_TABLE, list(ROUTING_HEADER_FIELDS), business_date, header_rows
        )
        self._replace_rows(
            conn, _OPERATIONS_TABLE, field_names(Operation), business_date, operation_rows
        )

    def save_change_log(self, change_log: ChangeLog) -> None:
        """Persist (replace) the daily change log for its business date."""
        business_date = change_log.business_date
        previous_date = change_log.previous_date or ""
        rows: list[dict[str, str]] = []
        for event in change_log.events:
            row = model_to_row(event)
            row["previous_date"] = previous_date
            rows.append(row)
        with closing(self._connect()) as conn, conn:
            self._replace_rows(
                conn, _CHANGE_LOG_TABLE, _CHANGE_LOG_COLUMNS, business_date, rows
            )

    @staticmethod
    def _replace_rows(
        conn: sqlite3.Connection,
        table: str,
        columns: list[str],
        business_date: str,
        rows: list[dict[str, str]],
    ) -> None:
        conn.execute(
            f"DELETE FROM {_quote(table)} WHERE {_quote(_DATE_COL)} = ?",
            (business_date,),
        )
        if not rows:
            return
        all_cols = [_DATE_COL, *columns]
        col_sql = ", ".join(_quote(c) for c in all_cols)
        placeholders = ", ".join("?" for _ in all_cols)
        conn.executemany(
            f"INSERT INTO {_quote(table)} ({col_sql}) VALUES ({placeholders})",
            [
                (business_date, *[row.get(c, "") for c in columns])
                for row in rows
            ],
        )

    # -- Read side ----------------------------------------------------------
    def has(self, business_date: str) -> bool:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                f"SELECT 1 FROM {_quote(_SNAPSHOTS_TABLE)} "
                f"WHERE {_quote(_DATE_COL)} = ?",
                (business_date,),
            )
            return cur.fetchone() is not None

    def available_dates(self) -> list[str]:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                f"SELECT {_quote(_DATE_COL)} FROM {_quote(_SNAPSHOTS_TABLE)} "
                f"ORDER BY {_quote(_DATE_COL)}"
            )
            return [row[0] for row in cur.fetchall()]

    def load_state(self, business_date: str) -> FactoryState | None:
        """Return the snapshot for ``business_date`` or ``None`` if absent."""
        if not self.has(business_date):
            return None
        with closing(self._connect()) as conn:
            collections: dict[str, list[BaseModel]] = {}
            for _filename, attribute, model_cls in CSV_REGISTRY:
                collections[attribute] = [
                    row_to_model(row, model_cls)
                    for row in self._read_rows(
                        conn, attribute, field_names(model_cls), business_date
                    )
                ]
            routings = self._read_routings(conn, business_date)
        return FactoryState(
            business_date=business_date, routings=routings, **collections
        )

    @staticmethod
    def _read_rows(
        conn: sqlite3.Connection,
        table: str,
        columns: list[str],
        business_date: str,
    ) -> list[dict[str, str]]:
        col_sql = ", ".join(_quote(c) for c in columns)
        cur = conn.execute(
            f"SELECT {col_sql} FROM {_quote(table)} WHERE {_quote(_DATE_COL)} = ?",
            (business_date,),
        )
        return [
            {c: ("" if value is None else value) for c, value in zip(columns, row)}
            for row in cur.fetchall()
        ]

    def _read_routings(
        self, conn: sqlite3.Connection, business_date: str
    ) -> list[Routing]:
        operations_by_routing: dict[str, list[Operation]] = {}
        for row in self._read_rows(
            conn, _OPERATIONS_TABLE, field_names(Operation), business_date
        ):
            operation = row_to_model(row, Operation)
            operations_by_routing.setdefault(operation.routing_id, []).append(operation)

        routings: list[Routing] = []
        for row in self._read_rows(
            conn, _ROUTINGS_TABLE, list(ROUTING_HEADER_FIELDS), business_date
        ):
            routing_id = row["routing_id"]
            routings.append(
                Routing(
                    routing_id=routing_id,
                    product_id=row["product_id"],
                    version=row.get("version") or "1",
                    operations=operations_by_routing.get(routing_id, []),
                )
            )
        return routings


# ---------------------------------------------------------------------------
# Module-level helpers (store cache + backend selection)
# ---------------------------------------------------------------------------
def _db_path_for(datasets_dir: Path) -> Path:
    return Path(datasets_dir) / _DB_FILENAME


@lru_cache(maxsize=None)
def _store_for(db_path: str) -> FactorySqliteStore:
    return FactorySqliteStore(Path(db_path))


def get_factory_store(datasets_dir: Path) -> FactorySqliteStore:
    """Return the shared :class:`FactorySqliteStore` for ``datasets_dir``."""
    return _store_for(str(_db_path_for(datasets_dir)))


def maybe_get_store(datasets_dir: Path) -> FactorySqliteStore | None:
    """Return the store when SQLite is enabled, else ``None`` (pure CSV mode)."""
    if not get_settings().sqlite_enabled:
        return None
    return get_factory_store(datasets_dir)


class SqliteDataSource(DataSource):
    """DataSource backed by ``factory.db`` with automatic CSV fallback."""

    def __init__(self, datasets_dir: Path) -> None:
        self._datasets_dir = Path(datasets_dir)
        self._store = get_factory_store(self._datasets_dir)
        self._csv = CsvDataSource(datasets_dir)

    def load(self, business_date: str) -> FactoryState:
        state = self._store.load_state(business_date)
        if state is not None:
            return state
        return self._csv.load(business_date)

    def available_dates(self) -> list[str]:
        dates = set(self._store.available_dates()) | set(self._csv.available_dates())
        return sorted(dates)


def build_data_source(datasets_dir: Path) -> DataSource:
    """Return the active :class:`DataSource` (SQLite-first, else CSV)."""
    if get_settings().sqlite_enabled:
        return SqliteDataSource(datasets_dir)
    return CsvDataSource(datasets_dir)
