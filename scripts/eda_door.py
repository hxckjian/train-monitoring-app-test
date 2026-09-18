"""Concise EDA for the Door subsystem.

Purpose: decide how cycle boundaries are actually detectable, and confirm the
schema facts recorded in PROJECT-STATE.md. Run:

    python scripts/eda_door.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DOOR = ROOT / "repo" / "PS3" / "02_Datasets" / "Door"

TS_FMT = "%Y-%m-%d-%H-%M-%S-%f"


def parse_ts(s: pd.Series) -> pd.Series:
    """Parse the dataset's unpadded Y-M-D-H-M-S-ms stamps.

    The milliseconds field is not zero-padded either ('...-3-760' and '...-0-0'),
    so %f cannot be used directly -- %f wants microseconds. Split and rebuild.
    """
    parts = s.str.split("-", expand=True).astype(int)
    parts.columns = ["y", "mo", "d", "h", "mi", "sec", "ms"]
    return pd.to_datetime(
        dict(year=parts.y, month=parts.mo, day=parts.d,
             hour=parts.h, minute=parts.mi, second=parts.sec)
    ) + pd.to_timedelta(parts.ms, unit="ms")


def main() -> None:
    train = pd.read_csv(DOOR / "Train.csv")
    test = pd.read_csv(DOOR / "Test.csv")
    ans = pd.read_csv(DOOR / "Train_Segments_Answer.csv")

    print("=" * 72)
    print("SHAPES")
    print(f"  Train.csv {train.shape}   Test.csv {test.shape}   answer {ans.shape}")
    print(f"  columns ({len(train.columns)}): {list(train.columns)}")
    print(f"  test columns identical to train: {list(test.columns) == list(train.columns)}")

    print("\nDTYPES / MISSING / CONSTANT")
    for c in train.columns:
        nun = train[c].nunique(dropna=False)
        print(f"  {c:38s} {str(train[c].dtype):8s} "
              f"missing={train[c].isna().sum():5d} nunique={nun:6d}"
              f"{'   <-- CONSTANT' if nun <= 1 else ''}")

    print("\nTARGET")
    print(ans["status"].value_counts().to_string())
    print(f"  operation: {ans['operation'].value_counts().to_dict()}")
    print(f"  n_rows: min={ans.n_rows.min()} med={ans.n_rows.median()} max={ans.n_rows.max()} "
          f"sum={ans.n_rows.sum()}  (Train.csv rows={len(train)})")

    # ---- timing ---------------------------------------------------------
    t = parse_ts(train["Datetime"])
    dt = t.diff().dt.total_seconds()
    print("\nSAMPLING")
    print(f"  monotonic increasing: {t.is_monotonic_increasing}")
    print(f"  duplicated stamps: {t.duplicated().sum()}")
    print("  gap percentiles (s):")
    for q in [0.5, 0.9, 0.95, 0.98, 0.99, 0.995, 1.0]:
        print(f"    p{q*100:6.2f} = {dt.quantile(q):.4f}")
    modal = dt.round(4).value_counts().head(5)
    print(f"  most common intervals (s):\n{modal.to_string()}")

    big = dt[dt > dt.quantile(0.99)]
    print(f"  gaps above p99: n={len(big)}  min={big.min():.3f}  max={big.max():.3f}")

    # Does a pure time-gap rule recover the right number of segments?
    print("\nGAP-THRESHOLD SWEEP  (how many segments does a gap rule produce?)")
    print(f"  target from answer file: {len(ans)} segments")
    for thr in [0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 5.0]:
        n_seg = int((dt > thr).sum()) + 1
        print(f"    gap > {thr:5.2f}s  -> {n_seg:4d} segments")

    # ---- do rows exist only during cycles? ------------------------------
    span = (t.max() - t.min()).total_seconds()
    covered = ans.n_rows.sum()
    print("\nCOVERAGE")
    print(f"  stream span {span:.1f}s; rows {len(train)}; answer rows {covered} "
          f"({covered/len(train)*100:.1f}% of rows lie inside a labelled segment)")

    # ---- signal behaviour by class --------------------------------------
    ans_t0 = parse_ts(ans["start_time"])
    ans_t1 = parse_ts(ans["end_time"])
    seg_id = np.full(len(train), -1, dtype=int)
    for i, (a, b) in enumerate(zip(ans_t0, ans_t1)):
        seg_id[(t >= a).values & (t <= b).values] = i
    train = train.assign(_seg=seg_id)
    labelled = train[train._seg >= 0].copy()
    labelled["_status"] = ans["status"].to_numpy()[labelled._seg]

    print(f"\n  rows assigned to a segment: {len(labelled)} / {len(train)}")
    num_cols = [c for c in train.columns if c not in ("Datetime", "_seg")]
    stats = labelled.groupby("_status")[num_cols].mean().T
    print("\nMEAN BY CLASS (labelled rows only)")
    print(stats.to_string(float_format=lambda v: f"{v:10.2f}"))

    # per-segment aggregate separation
    agg = labelled.groupby("_seg").agg(
        cur_max=("Motor current(mA)", "max"),
        cur_mean=("Motor current(mA)", "mean"),
        emf_mean=("Motor electrodynamic force", "mean"),
        pos_min=("Door leaf position", "min"),
        pos_max=("Door leaf position", "max"),
        n=("Motor current(mA)", "size"),
    )
    agg["status"] = ans["status"].to_numpy()[agg.index]
    print("\nPER-SEGMENT AGGREGATES BY CLASS")
    print(agg.groupby("status").agg(["mean", "std"]).T.to_string(
        float_format=lambda v: f"{v:10.2f}"))

    # ---- test stream ----------------------------------------------------
    tt = parse_ts(test["Datetime"])
    dtt = tt.diff().dt.total_seconds()
    print("\nTEST STREAM")
    print(f"  rows={len(test)} span={(tt.max()-tt.min()).total_seconds():.1f}s "
          f"monotonic={tt.is_monotonic_increasing}")
    for thr in [0.1, 0.2, 0.3, 0.5, 1.0]:
        print(f"    gap > {thr:4.2f}s -> {int((dtt > thr).sum()) + 1:4d} segments")


if __name__ == "__main__":
    sys.exit(main())
