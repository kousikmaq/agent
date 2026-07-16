"""Idempotent project setup.

Ensures the dataset and all trained models exist. Safe to run repeatedly - it only does work
when something is missing, so a fresh clone becomes runnable with a single command and the
server starts instantly on subsequent boots (models persist on disk).

Usage:
    python -m app.setup            # generate data if missing, train models if missing
    python -m app.setup --force    # regenerate data and retrain everything
"""
from __future__ import annotations

import os
import runpy
import sys

from app.config import BACKEND_DIR, DATA_DIR
from app.ml import registry


def _data_exists() -> bool:
    return os.path.exists(os.path.join(DATA_DIR, "fact_job_operations.csv"))


def ensure_ready(force: bool = False) -> dict:
    """Generate the dataset and train the models if (and only if) they are missing."""
    from app import data_access as da

    ran: list[str] = []
    if force or not _data_exists():
        print("[setup] generating dataset ...")
        runpy.run_path(os.path.join(BACKEND_DIR, "data", "generate_dataset.py"), run_name="__main__")
        da.clear_cache()
        ran.append("dataset")

    if force or not registry.all_models_available():
        print("[setup] training models (one-time, ~2-3 min) ...")
        from app.ml import train
        train.main()
        registry.reload()
        ran.append("models")

    if not ran:
        print("[setup] already ready - nothing to do.")
    return {"ran": ran, "ready": registry.all_models_available()}


if __name__ == "__main__":
    ensure_ready(force="--force" in sys.argv)
