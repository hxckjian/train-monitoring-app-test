"""Rainflow-count every SHM file once and cache the result.

Counting 80 files of ~581k samples is the expensive part; fitting the two S-N
constants against the cache afterwards is instant. Run:

    python scripts/shm_rainflow_cache.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import rainflow

ROOT = Path(__file__).resolve().parents[1]
SHM = ROOT / "repo" / "PS3" / "02_Datasets" / "SHM"
CACHE = ROOT / "artifacts_cache"
CACHE.mkdir(exist_ok=True)


def load_stress(path: Path) -> np.ndarray:
    """SHM files have NO header and exactly one column of bare stress values."""
    return pd.read_csv(path, header=None).iloc[:, 0].to_numpy(dtype=float)


def count_file(path: Path) -> dict:
    x = load_stress(path)
    cycles = np.array(
        [(rng, mean, cnt) for rng, mean, cnt, _, _ in rainflow.extract_cycles(x)],
        dtype=float,
    )
    return {
        "filename": path.name,
        "n_samples": len(x),
        "stress_min": float(x.min()),
        "stress_max": float(x.max()),
        "stress_std": float(x.std()),
        "n_cycles": len(cycles),
        "rng": cycles[:, 0],
        "mean": cycles[:, 1],
        "cnt": cycles[:, 2],
    }


def process(folder: Path, tag: str) -> None:
    files = sorted(folder.glob("*.csv"))
    print(f"\n{tag}: {len(files)} files")
    store, summary = {}, []
    t0 = time.time()
    for i, p in enumerate(files, 1):
        r = count_file(p)
        store[f"{r['filename']}::rng"] = r["rng"]
        store[f"{r['filename']}::mean"] = r["mean"]
        store[f"{r['filename']}::cnt"] = r["cnt"]
        summary.append({k: r[k] for k in
                        ("filename", "n_samples", "stress_min", "stress_max",
                         "stress_std", "n_cycles")})
        if i % 16 == 0 or i == len(files):
            print(f"  {i:3d}/{len(files)}  {time.time() - t0:6.1f}s  "
                  f"last={r['filename']} cycles={r['n_cycles']}")
    np.savez_compressed(CACHE / f"shm_{tag}_cycles.npz", **store)
    pd.DataFrame(summary).to_csv(CACHE / f"shm_{tag}_summary.csv", index=False)
    print(f"  cached -> artifacts_cache/shm_{tag}_cycles.npz")


def main() -> int:
    for folder, tag in ((SHM / "Train", "train"), (SHM / "Test", "test")):
        if not folder.exists():
            print(f"ERROR: {folder} not found", file=sys.stderr)
            return 2
        process(folder, tag)

    s = pd.read_csv(CACHE / "shm_train_summary.csv")
    labels = pd.read_csv(SHM / "Train_Labels.csv")
    print("\nTRAIN SUMMARY")
    print(f"  samples per file: min={s.n_samples.min()} max={s.n_samples.max()} "
          f"(identical: {s.n_samples.nunique() == 1})")
    print(f"  rainflow cycles per file: min={s.n_cycles.min()} "
          f"med={int(s.n_cycles.median())} max={s.n_cycles.max()}")
    print(f"  stress range across files: [{s.stress_min.min():.2f}, "
          f"{s.stress_max.max():.2f}]")
    print(f"\n  damage label: min={labels.damage.min():.6f} "
          f"max={labels.damage.max():.6f} ratio={labels.damage.max()/labels.damage.min():.1f}x")
    print(f"  damage quartiles: {labels.damage.quantile([.25,.5,.75]).round(5).tolist()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
