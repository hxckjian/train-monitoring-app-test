"""Drift watch: how far a new recording's features sit from the training data.

Each subsystem stores robust per-feature statistics of its training set
(median and MAD) in artifacts/feature_stats.json, written by
scripts/feature_stats.py. At inference, every feature of the new file gets a
robust z-score against those statistics; the drift score is the share of
features beyond 3 MAD. High drift does not mean the verdict is wrong, it means
the model is being asked about data unlike what it was validated on, so the
console lowers the confidence it shows and the learning loop takes note.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LEVELS = ((0.05, "low"), (0.15, "moderate"), (1.01, "high"))


def stats_path(key: str) -> Path:
    return ROOT / "subsystems" / key / "artifacts" / "feature_stats.json"


def fit_stats(x: pd.DataFrame) -> dict:
    """Median and MAD per numeric column, plus the training size."""
    num = x.select_dtypes(include=[np.number])
    med = num.median()
    mad = (num - med).abs().median() * 1.4826
    return {"n": int(len(num)),
            "features": {c: {"median": float(med[c]), "mad": float(mad[c]) if mad[c] > 0 else None}
                         for c in num.columns}}


def save_stats(key: str, x: pd.DataFrame) -> Path:
    p = stats_path(key)
    p.write_text(json.dumps(fit_stats(x), indent=1), encoding="utf-8")
    return p


def load_stats(key: str) -> dict | None:
    p = stats_path(key)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def score(key: str, row: pd.Series | dict) -> dict | None:
    """Drift for one feature row. Returns {'score', 'level', 'n_features', 'worst': [(feature, z), ...]}."""
    st = load_stats(key)
    if not st:
        return None
    zs = []
    for f, s in st["features"].items():
        if f not in row or s["mad"] is None:
            continue
        v = row[f]
        try:
            z = abs(float(v) - s["median"]) / s["mad"]
        except (TypeError, ValueError):
            continue
        if np.isfinite(z):
            zs.append((f, float(z)))
    if not zs:
        return None
    share = sum(1 for _, z in zs if z > 3) / len(zs)
    if len(zs) >= 10:
        level = next(name for cut, name in LEVELS if share < cut)
    else:  # a handful of features: one outlier is not "high"; judge by how far the worst one sits
        worst_z = max(z for _, z in zs)
        level = "high" if worst_z > 8 else "moderate" if worst_z > 3 else "low"
    worst = sorted(zs, key=lambda t: -t[1])[:5]
    return {"score": float(share), "level": level, "n_features": len(zs), "worst": worst}


def summarise(scores: list[dict | None]) -> dict | None:
    """Batch summary: worst level and mean share across files."""
    got = [s for s in scores if s]
    if not got:
        return None
    mean = float(np.mean([s["score"] for s in got]))
    level = next(name for cut, name in LEVELS if mean < cut)
    return {"score": mean, "level": level, "n_files": len(got),
            "high_files": sum(1 for s in got if s["level"] == "high")}
