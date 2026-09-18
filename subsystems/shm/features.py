"""Shared data processing for the SHM subsystem.

Used by BOTH train.py and predict.py, so training and inference cannot drift.

The model is the one the Info Kit says generated the labels:

    D = sum_i n_i / N_i,   N_i = C / sigma_i^m   =>   D = (1/C) * sum_i n_i * sigma_i^m

Rainflow counting turns a stress history into (range, count) pairs; everything
after that is two scalars, m and C. Ranges are used directly rather than
amplitudes: (range/2)^m = range^m / 2^m, and the 2^m folds into C, so the
convention changes the reported C but never the prediction.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
import pandas as pd
import rainflow
from scipy.special import logsumexp

MIN_SAMPLES = 1_000


@dataclass(frozen=True)
class Cycles:
    """Rainflow output for one file: full and half cycles, counts 1.0 or 0.5."""
    rng: np.ndarray
    cnt: np.ndarray

    @property
    def n_cycles(self) -> float:
        return float(self.cnt.sum())


# --------------------------------------------------------------------------
# Loading and validation
# --------------------------------------------------------------------------

def load_input(uploaded_file: Any) -> np.ndarray:
    """Read one SHM file: NO header, exactly one column of stress values."""
    name = getattr(uploaded_file, "name", None)
    if name is not None and not str(name).lower().endswith(".csv"):
        raise ValueError(f"SHM expects .csv stress files; got '{name}'.")
    if hasattr(uploaded_file, "seek"):
        try:
            uploaded_file.seek(0)
        except (OSError, ValueError):
            pass
    try:
        df = pd.read_csv(uploaded_file, header=None)
    except Exception as exc:
        raise ValueError(f"could not read '{name}' as CSV: {exc}") from exc

    if df.shape[1] != 1:
        raise ValueError(
            f"'{name}' has {df.shape[1]} columns. SHM files hold exactly one "
            "column of stress values with no header."
        )
    values = pd.to_numeric(df.iloc[:, 0], errors="coerce")
    bad = int(values.isna().sum())
    if bad:
        first = int(np.flatnonzero(values.isna().to_numpy())[0])
        hint = " It looks like the file has a header row; SHM files have none." \
            if first == 0 and bad == 1 else ""
        raise ValueError(f"'{name}' has {bad} non-numeric value(s), first at row {first + 1}.{hint}")
    return values.to_numpy(dtype=float)


def validate_input(x: np.ndarray, name: str = "file") -> None:
    if x.size < MIN_SAMPLES:
        raise ValueError(
            f"'{name}' has only {x.size} samples; a damage estimate needs at "
            f"least {MIN_SAMPLES:,} (training files have 581,120)."
        )
    if not np.all(np.isfinite(x)):
        raise ValueError(f"'{name}' contains infinite values.")
    if np.ptp(x) == 0:
        raise ValueError(f"'{name}' is constant: no stress cycles to count.")


# --------------------------------------------------------------------------
# Rainflow and damage
# --------------------------------------------------------------------------

def rainflow_cycles(x: np.ndarray) -> Cycles:
    """ASTM E1049 rainflow counting on the FULL series.

    Never decimate first: halving the sampling drops ~50% of cycles and biases
    the damage sums by a file-dependent 5-16%, measured on this dataset.
    """
    out = np.fromiter(
        (v for rng, _mean, cnt, _i, _j in rainflow.extract_cycles(x) for v in (rng, cnt)),
        dtype=float,
    ).reshape(-1, 2)
    keep = out[:, 0] > 0
    return Cycles(rng=out[keep, 0], cnt=out[keep, 1])


def log_damage_sum(c: Cycles, m: float, log_ref: float) -> float:
    """log sum_i n_i * (rng_i / ref)^m, computed stably."""
    return float(logsumexp(np.log(c.cnt) + m * (np.log(c.rng) - log_ref)))


def log_damage_sums_grid(c: Cycles, m_grid: np.ndarray, log_ref: float,
                         chunk: int = 32) -> np.ndarray:
    """log damage sum at every m in a grid, chunked to bound memory."""
    lc = np.log(c.cnt)[:, None]
    lr = (np.log(c.rng) - log_ref)[:, None]
    out = np.empty(len(m_grid))
    for s in range(0, len(m_grid), chunk):
        m = m_grid[s:s + chunk][None, :]
        out[s:s + chunk] = logsumexp(lc + lr * m, axis=0)
    return out


def predict_damage(c: Cycles, m: float, log_c: float, log_ref: float) -> float:
    return float(np.exp(log_damage_sum(c, m, log_ref) - log_c))


# --------------------------------------------------------------------------
# Evidence for the interface
# --------------------------------------------------------------------------

def amplitude_profile(c: Cycles, m: float, n_bins: int = 36) -> pd.DataFrame:
    """Cycles and share of damage by stress range, for the explanation charts."""
    edges = np.linspace(0.0, float(c.rng.max()), n_bins + 1)
    idx = np.clip(np.digitize(c.rng, edges) - 1, 0, n_bins - 1)
    w = c.cnt * (c.rng / c.rng.max()) ** m
    cycles = np.bincount(idx, weights=c.cnt, minlength=n_bins)
    damage = np.bincount(idx, weights=w, minlength=n_bins)
    return pd.DataFrame({
        "range_lo": edges[:-1],
        "range_hi": edges[1:],
        "range_mid": (edges[:-1] + edges[1:]) / 2,
        "cycles": cycles,
        "damage_share": damage / damage.sum(),
    })


def damage_concentration(c: Cycles, m: float, top_fraction: float = 0.01) -> float:
    """Share of total damage caused by the largest `top_fraction` of cycles."""
    order = np.argsort(c.rng)[::-1]
    w = (c.cnt * (c.rng / c.rng.max()) ** m)[order]
    cum_cycles = np.cumsum(c.cnt[order]) / c.cnt.sum()
    k = int(np.searchsorted(cum_cycles, top_fraction)) + 1
    return float(w[:k].sum() / w.sum())


def stress_envelope(x: np.ndarray, n_buckets: int = 1200) -> pd.DataFrame:
    """Min/max per bucket, so peaks survive downsampling for display."""
    n_buckets = min(n_buckets, x.size)
    bounds = np.linspace(0, x.size, n_buckets + 1).astype(int)
    lo = np.minimum.reduceat(x, bounds[:-1])
    hi = np.maximum.reduceat(x, bounds[:-1])
    return pd.DataFrame({"sample": bounds[:-1], "min": lo, "max": hi})


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def format_predictions(file_ids: Sequence[str], damage: Sequence[float]) -> pd.DataFrame:
    """file_id (with extension), prediction (numeric cumulative damage)."""
    if len(file_ids) != len(damage):
        raise ValueError("file_ids and damage differ in length")
    return pd.DataFrame({"file_id": list(file_ids),
                         "prediction": np.asarray(damage, dtype=float)})


def make_uploaded_file(path) -> io.BytesIO:
    from pathlib import Path as _Path
    p = _Path(path)
    buf = io.BytesIO(p.read_bytes())
    buf.name = p.name
    return buf
