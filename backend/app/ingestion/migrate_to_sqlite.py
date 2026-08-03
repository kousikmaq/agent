"""One-off backfill: import existing CSV snapshots into ``datasets/factory.db``.

Reads every dated snapshot under the datasets directory via the CSV adapter and
writes it into the global SQLite database. Idempotent - re-running replaces each
date's rows, so it is safe to run repeatedly. The CSV snapshots are left
untouched.

Run (from ``backend/``):

    python -m app.ingestion.migrate_to_sqlite
"""

from __future__ import annotations

from app.config import get_settings
from app.ingestion.csv_source import CsvDataSource
from app.ingestion.sqlite_store import get_factory_store


def main() -> None:
    settings = get_settings()
    datasets_dir = settings.datasets_dir
    csv_source = CsvDataSource(datasets_dir)
    store = get_factory_store(datasets_dir)

    dates = csv_source.available_dates()
    if not dates:
        print(f"No CSV snapshots found under {datasets_dir}. Nothing to migrate.")
        return

    print(f"Migrating {len(dates)} snapshot(s) into {settings.factory_db_path} ...")
    for business_date in dates:
        state = csv_source.load(business_date)
        store.save_state(state)
        print(f"  migrated {business_date}")
    print(f"Done. Database has {len(store.available_dates())} snapshot(s).")


if __name__ == "__main__":
    main()
