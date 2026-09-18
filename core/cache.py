"""Persisted analysis results for the provided test data, so the dashboard has
something to show the moment it opens instead of after a one-minute run.

Written by scripts/build_predictions.py (which already runs every model over
the competition test inputs) and read by the app on first visit. The cache is
derived data: deleting it costs one rebuild and nothing else. It is gitignored
because it holds per-file evidence (traces, spectra) of a few megabytes.
"""
from __future__ import annotations

import pickle
from pathlib import Path

CACHE_PATH = Path(__file__).resolve().parents[1] / "predictions" / "analysis_cache.pkl"


def save(results: dict) -> Path:
    CACHE_PATH.parent.mkdir(exist_ok=True)
    with open(CACHE_PATH, "wb") as f:
        pickle.dump(results, f, protocol=pickle.HIGHEST_PROTOCOL)
    return CACHE_PATH


def load() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        with open(CACHE_PATH, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None
