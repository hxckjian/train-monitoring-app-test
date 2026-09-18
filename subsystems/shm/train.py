"""Fit the SHM S-N constants (m, C) and save every artifact inference needs.

From the project root:

    python -m subsystems.shm.train

Importing this module trains nothing.

Rainflow counting 64 files takes ~80 s. If `artifacts_cache/shm_train_cycles.npz`
exists (written by scripts/shm_rainflow_cache.py with the same counting call),
it is reused; pass --recount to ignore it.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

MODULE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODULE_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scoring.metrics import shm_score  # noqa: E402
from subsystems.shm.features import (  # noqa: E402
    Cycles,
    load_input,
    log_damage_sums_grid,
    rainflow_cycles,
)

SEED = 20260918
N_FOLDS = 5
M_GRID = np.round(np.arange(3.0, 7.0 + 1e-9, 0.005), 3)

ARTIFACT_DIR = MODULE_DIR / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "model.joblib"
CONFIG_PATH = ARTIFACT_DIR / "config.json"
DEFAULT_DATA_DIR = PROJECT_ROOT / "repo" / "PS3" / "02_Datasets" / "SHM"
SHARED_CACHE = PROJECT_ROOT / "artifacts_cache" / "shm_train_cycles.npz"


def count_all(data_dir: Path, names: list[str], recount: bool) -> dict[str, Cycles]:
    if SHARED_CACHE.exists() and not recount:
        z = np.load(SHARED_CACHE)
        if all(f"{n}::rng" in z.files for n in names):
            print(f"  reusing rainflow cache {SHARED_CACHE.relative_to(PROJECT_ROOT)}")
            out = {}
            for n in names:
                rng, cnt = z[f"{n}::rng"], z[f"{n}::cnt"]
                keep = rng > 0
                out[n] = Cycles(rng=rng[keep], cnt=cnt[keep])
            return out

    out, t0 = {}, time.time()
    for i, n in enumerate(names, 1):
        with open(data_dir / "Train" / n, "rb") as fh:
            out[n] = rainflow_cycles(load_input(fh))
        if i % 16 == 0 or i == len(names):
            print(f"  counted {i:3d}/{len(names)}  {time.time() - t0:5.1f}s")
    return out


def fit(L: np.ndarray, y: np.ndarray) -> tuple[int, float, float]:
    """Pick m on the grid; log C in closed form (mean log residual).

    Fitting log C as the mean log residual minimises squared LOG error, which
    tracks the RELATIVE error the official MAPE metric measures. Least squares
    on raw damage would chase the large files and wreck the small ones.
    """
    log_c = np.mean(L - np.log(y)[:, None], axis=0)             # per grid m
    pred = np.exp(L - log_c[None, :])
    mape = np.mean(np.abs(y[:, None] - pred) / y[:, None], axis=0)
    j = int(np.argmin(mape))
    return j, float(log_c[j]), float(mape[j])


def main() -> int:
    ap = argparse.ArgumentParser(description="Fit the SHM S-N constants.")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--recount", action="store_true",
                    help="ignore the shared rainflow cache")
    args = ap.parse_args()

    labels_path = args.data_dir / "Train_Labels.csv"
    if not labels_path.exists():
        print(f"ERROR: {labels_path} not found", file=sys.stderr)
        return 2
    labels = pd.read_csv(labels_path)
    names = list(labels["filename"])
    y = labels["damage"].to_numpy(dtype=float)
    if np.any(y <= 0):
        print("ERROR: non-positive damage label; MAPE is undefined", file=sys.stderr)
        return 2

    print(f"SHM subsystem - training\n  {len(names)} files, damage "
          f"{y.min():.4f}-{y.max():.4f} ({y.max() / y.min():.1f}x spread)")
    cycles = count_all(args.data_dir, names, args.recount)

    log_ref = float(np.log(max(c.rng.max() for c in cycles.values())))
    t0 = time.time()
    L = np.vstack([log_damage_sums_grid(cycles[n], M_GRID, log_ref) for n in names])
    print(f"  damage sums over {len(M_GRID)} values of m in {time.time() - t0:.1f}s")

    # ---- leakage-safe CV: (m, C) fitted INSIDE each fold ----------------
    print(f"\nCROSS-VALIDATION ({N_FOLDS}-fold, m and C fitted inside each fold)")
    folds = np.array_split(np.random.default_rng(SEED).permutation(len(names)), N_FOLDS)
    scores, ms, fold_rows = [], [], []
    fixed5 = []
    j5 = int(np.argmin(np.abs(M_GRID - 5.0)))
    for i, va in enumerate(folds, 1):
        tr = np.setdiff1d(np.arange(len(names)), va)
        j, log_c, _ = fit(L[tr], y[tr])
        pred = np.exp(L[va, j] - log_c)
        s = shm_score(y[va], pred)
        scores.append(s)
        ms.append(float(M_GRID[j]))
        # the same fold with m pinned to exactly 5.0 - the textbook exponent
        log_c5 = float(np.mean(L[tr, j5] - np.log(y[tr])))
        fixed5.append(shm_score(y[va], np.exp(L[va, j5] - log_c5)))
        fold_rows.append({"fold": i, "n_files": int(len(va)), "m": float(M_GRID[j]),
                          "score": s})
        print(f"  fold {i}: n={len(va):2d}  m={M_GRID[j]:.3f}  score={s:.4f}  "
              f"(MAPE {(1 - s) * 100:.2f}%)")

    print(f"\n  official metric  max(0, 1-MAPE) = {np.mean(scores):.4f} +/- {np.std(scores):.4f}")
    print(f"  m across folds: {min(ms):.3f} to {max(ms):.3f}")
    print(f"  with m fixed at 5.000:            {np.mean(fixed5):.4f} +/- {np.std(fixed5):.4f}")
    print(f"  constant (train median) baseline: "
          f"{shm_score(y, np.full_like(y, np.median(y))):.4f}")

    # ---- final fit on all training files --------------------------------
    j, log_c, mape_in = fit(L, y)
    m = float(M_GRID[j])
    if j in (0, len(M_GRID) - 1):
        print(f"WARNING: best m={m} is on the grid edge; widen M_GRID", file=sys.stderr)
    C_amp = float(np.exp(log_c + m * log_ref - m * np.log(2.0)))   # for amplitude units
    print(f"\nFINAL FIT (all {len(names)} files)\n  m = {m:.3f}   log C = {log_c:.4f}   "
          f"in-sample MAPE {mape_in * 100:.2f}% (diagnostic only)")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"m": m, "log_c": log_c, "log_ref": log_ref}, MODEL_PATH)
    config = {
        "model_version": "shm-v1",
        "method": "rainflow counting (ASTM E1049) + Miner linear cumulative damage, "
                  "S-N constants fitted to the training labels",
        "m": m,
        "log_c": log_c,
        "log_ref": log_ref,
        "C_in_stress_amplitude_units": C_amp,
        "n_training_files": len(names),
        "damage_range_train": [float(y.min()), float(y.max())],
        "validation": {
            "split": f"{N_FOLDS}-fold over files, seed {SEED}; m and C fitted inside "
                     "each fold only",
            "metric": "max(0, 1 - MAPE) (SHM_Info_Kit.md Section 4)",
            "mean_score": float(np.mean(scores)),
            "std_score": float(np.std(scores)),
            "fixed_m5_mean_score": float(np.mean(fixed5)),
            "m_range_across_folds": [min(ms), max(ms)],
            "folds": fold_rows,
        },
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"\n  saved {MODEL_PATH.relative_to(PROJECT_ROOT)}")
    print(f"  saved {CONFIG_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
