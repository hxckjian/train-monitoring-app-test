"""Write each subsystem's training feature statistics for the drift watch.

    .venv/Scripts/python -m scripts.feature_stats

Door: per-cycle features of the 110 training cycles. Rail: the cached training
feature table (built by the experiments; rebuilt here if absent). SHM: per-file
summary statistics. ACV: per-car peer features over the six cases.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import drift  # noqa: E402
from core.registry import DATA_ROOT  # noqa: E402


def door() -> None:
    from subsystems.door import train as dt
    from subsystems.door.features import clean_data, extract_features, segment_data
    df = clean_data(pd.read_csv(DATA_ROOT / "Door" / "Train.csv"))
    gap, _ = dt.derive_gap_seconds(df)
    segs = segment_data(df, gap)
    print("door:", drift.save_stats("door", extract_features(df, segs)))


def rail() -> None:
    cache = ROOT / "artifacts_cache" / "rail_train_features.pkl"
    if cache.exists():
        x = pd.read_pickle(cache)
    else:
        from subsystems.rail.features import extract_features, load_input
        labels = pd.read_csv(DATA_ROOT / "Rail_Corrugation" / "Train_Labels.csv")
        x = pd.concat([extract_features(load_input(DATA_ROOT / "Rail_Corrugation" / "Train" / n)) for n in labels.filename],
                      ignore_index=True)
    x = x[[c for c in x.columns if "_wl_" not in c]]
    print("rail:", drift.save_stats("rail", x))


def shm() -> None:
    rows = []
    for p in sorted((DATA_ROOT / "SHM" / "Train").glob("train*.csv")):
        v = pd.read_csv(p, header=None).iloc[:, 0].to_numpy(dtype=float)
        rows.append({"stress_std": float(v.std()), "stress_max": float(v.max()), "stress_min": float(v.min()),
                     "stress_p99_range": float(np.percentile(v, 99.9) - np.percentile(v, 0.1)), "n_samples": len(v)})
    print("shm:", drift.save_stats("shm", pd.DataFrame(rows)))


def acv() -> None:
    from subsystems.acv.features import extract_features, load
    rows = []
    for p in sorted((DATA_ROOT / "ACV" / "Train").glob("*.xlsx")):
        with open(p, "rb") as f:
            frame, cars = load(f)
        rows.append(extract_features(frame, cars))
    print("acv:", drift.save_stats("acv", pd.concat(rows, ignore_index=True)))


if __name__ == "__main__":
    for fn in (door, rail, shm, acv):
        try:
            fn()
        except Exception as exc:  # one subsystem's failure must not block the others
            print(f"{fn.__name__}: skipped ({exc})")
