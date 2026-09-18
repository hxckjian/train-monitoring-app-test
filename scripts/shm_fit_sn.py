"""Test the hypothesis that the SHM labels are rainflow + Miner, and fit (m, C).

  D = sum_i n_i / N_i,   N_i = C / sigma_i^m   =>   D = (1/C) * sum_i n_i * sigma_i^m

So for a fixed m, the whole model is ONE scalar: D_pred = S(m) / C where
S(m) = sum_i n_i * sigma_i^m. Fitting is a 1-D search over m with C in closed
form, not a machine-learning problem.

Note on convention: sigma_a = range/2, and (range/2)^m = range^m / 2^m, so the
factor 2^m is absorbed entirely into C. Amplitude vs range therefore does not
change the fit, only the reported value of C.

The official metric is relative (MAPE), so we fit in log space rather than least
squares: minimising absolute error would chase the large-damage files and let
the small-damage files, which dominate MAPE, go badly wrong.

Run:  python scripts/shm_fit_sn.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import logsumexp

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scoring.metrics import shm_score  # noqa: E402

SHM = ROOT / "repo" / "PS3" / "02_Datasets" / "SHM"
CACHE = ROOT / "artifacts_cache"
SEED = 20260918
N_FOLDS = 5


def load_cycles(tag: str) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    z = np.load(CACHE / f"shm_{tag}_cycles.npz")
    names = sorted({k.split("::")[0] for k in z.files})
    return {n: (z[f"{n}::rng"], z[f"{n}::cnt"]) for n in names}


def log_S(cycles: dict, names: list[str], m: float, log_ref: float) -> np.ndarray:
    """log sum_i n_i * (rng_i / ref)^m, computed stably.

    Dividing by a reference range keeps the powers in range for large m; the
    constant ref^m is absorbed into C, so it changes nothing about the fit.
    """
    out = np.empty(len(names))
    for k, n in enumerate(names):
        rng, cnt = cycles[n]
        good = rng > 0
        out[k] = logsumexp(np.log(cnt[good]) + m * (np.log(rng[good]) - log_ref))
    return out


def fit_C(logS: np.ndarray, d_true: np.ndarray) -> float:
    """Closed-form log C that minimises mean squared log relative error."""
    return float(np.mean(logS - np.log(d_true)))


def fit_m(cycles: dict, names: list[str], d_true: np.ndarray,
          log_ref: float, grid: np.ndarray) -> tuple[float, float, float]:
    """1-D search over m; C in closed form at each step."""
    best = (np.inf, None, None)
    for m in grid:
        logS = log_S(cycles, names, m, log_ref)
        logC = fit_C(logS, d_true)
        pred = np.exp(logS - logC)
        mape = float(np.mean(np.abs(d_true - pred) / d_true))
        if mape < best[0]:
            best = (mape, float(m), logC)
    return best[1], best[2], best[0]


def refine(cycles, names, d_true, log_ref, m0, span, steps=41):
    grid = np.linspace(max(m0 - span, 0.1), m0 + span, steps)
    return fit_m(cycles, names, d_true, log_ref, grid)


def main() -> int:
    if not (CACHE / "shm_train_cycles.npz").exists():
        print("ERROR: run scripts/shm_rainflow_cache.py first", file=sys.stderr)
        return 2

    labels = pd.read_csv(SHM / "Train_Labels.csv")
    cycles = load_cycles("train")
    names = list(labels["filename"])
    missing = [n for n in names if n not in cycles]
    if missing:
        print(f"ERROR: no cached cycles for {missing[:3]}", file=sys.stderr)
        return 2

    d_true = labels["damage"].to_numpy(dtype=float)
    all_rng = np.concatenate([cycles[n][0] for n in names])
    log_ref = float(np.log(all_rng.max()))
    print(f"SHM S-N fit\n  files={len(names)}  reference range={np.exp(log_ref):.3f}")
    print(f"  damage: min={d_true.min():.6f} max={d_true.max():.6f} "
          f"({d_true.max()/d_true.min():.1f}x spread)")

    # ---- full-data fit, for the diagnostic only -------------------------
    m_hat, logC_hat, mape_in = fit_m(cycles, names, d_true, log_ref,
                                     np.arange(1.0, 14.01, 0.25))
    m_hat, logC_hat, mape_in = refine(cycles, names, d_true, log_ref, m_hat, 0.25)
    C_hat = float(np.exp(logC_hat + m_hat * log_ref))   # undo the normalisation
    print("\nIN-SAMPLE FIT (diagnostic only, NOT a validation score)")
    print(f"  m = {m_hat:.4f}   C = {C_hat:.6g}")
    print(f"  MAPE = {mape_in*100:.4f}%   score = {max(0.0, 1-mape_in):.6f}")
    if mape_in < 0.02:
        print("  -> residuals collapse: the rainflow + Miner hypothesis HOLDS.")

    # ---- honest CV: constants fitted INSIDE each fold -------------------
    print(f"\nCROSS-VALIDATION ({N_FOLDS}-fold, (m, C) fitted inside each fold)")
    rng_state = np.random.default_rng(SEED)
    order = rng_state.permutation(len(names))
    folds = np.array_split(order, N_FOLDS)

    scores, ms, cs = [], [], []
    for i, val_idx in enumerate(folds, 1):
        tr_idx = np.setdiff1d(np.arange(len(names)), val_idx)
        tr_names = [names[j] for j in tr_idx]
        va_names = [names[j] for j in val_idx]

        m, logC, _ = fit_m(cycles, tr_names, d_true[tr_idx], log_ref,
                           np.arange(1.0, 14.01, 0.25))
        m, logC, _ = refine(cycles, tr_names, d_true[tr_idx], log_ref, m, 0.25)

        pred = np.exp(log_S(cycles, va_names, m, log_ref) - logC)
        s = shm_score(d_true[val_idx], pred)
        scores.append(s); ms.append(m); cs.append(logC)
        print(f"  fold {i}: n={len(val_idx):2d}  m={m:6.3f}  "
              f"score={s:.6f}  (MAPE {(1-s)*100:.3f}%)")

    print(f"\n  official metric  max(0, 1-MAPE) = "
          f"{np.mean(scores):.6f} +/- {np.std(scores):.6f}")
    print(f"  m across folds: {np.min(ms):.3f} to {np.max(ms):.3f} "
          f"(stable => the constant is a real property, not fold noise)")

    # ---- baselines this must beat ---------------------------------------
    print("\nBASELINES")
    const = np.full_like(d_true, float(np.mean(d_true)))
    print(f"  constant (train mean)      score = {shm_score(d_true, const):.6f}")
    med = np.full_like(d_true, float(np.median(d_true)))
    print(f"  constant (train median)    score = {shm_score(d_true, med):.6f}")

    # a generic ML alternative on summary statistics, same folds
    summary = pd.read_csv(CACHE / "shm_train_summary.csv").set_index("filename")
    feats = summary.loc[names, ["stress_std", "stress_max", "stress_min",
                                "n_cycles"]].to_numpy(dtype=float)
    from sklearn.ensemble import RandomForestRegressor
    gen = []
    for val_idx in folds:
        tr_idx = np.setdiff1d(np.arange(len(names)), val_idx)
        rf = RandomForestRegressor(n_estimators=300, random_state=SEED)
        rf.fit(feats[tr_idx], np.log(d_true[tr_idx]))
        gen.append(shm_score(d_true[val_idx], np.exp(rf.predict(feats[val_idx]))))
    print(f"  RandomForest on summary stats, same folds = "
          f"{np.mean(gen):.6f} +/- {np.std(gen):.6f}")
    print("    (this is what a team that skips the fatigue physics would get)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
