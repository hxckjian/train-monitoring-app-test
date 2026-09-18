"""Generic parameter monitor: the ACV peer-comparison method and a robust
drift screen, generalised to any tabular sensor export.

This is the "future dataset" path. A new parameter on a new fleet rarely comes
with labels on day one, so the first useful thing is a label-free screen that
uses the same two ideas the validated subsystems rely on:

1. Peer-relative excess (from ACV): units on the same vehicle share weather,
   load and route, so compare each unit to the contemporaneous median of the
   others and rank by the mean excess. No model is fitted, so nothing can
   overfit; the ranking is a diagnostic, not a probability.
2. Robust drift (from Door/SHM thinking): for a single series, compare each
   window to the series' own median with a MAD-scaled score, so a step change
   or a slow drift stands out without assuming a distribution.

When labels arrive, promote the parameter to a full subsystem: see the
Method page, "Adding a subsystem".
"""
from __future__ import annotations

import io
from typing import Any

import numpy as np
import pandas as pd


def load_table(uploaded: Any) -> pd.DataFrame:
    name = str(getattr(uploaded, "name", "")).lower()
    raw = uploaded.getvalue() if hasattr(uploaded, "getvalue") else uploaded.read()
    if name.endswith(".xlsx"):
        return pd.read_excel(io.BytesIO(raw))
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception:
        return pd.read_csv(io.BytesIO(raw), header=None)
    # a header made of numbers means there was no header (e.g. the SHM stress files)
    if len(df.columns) and all(_is_number(c) for c in df.columns):
        df = pd.read_csv(io.BytesIO(raw), header=None)
        df.columns = [f"series_{i + 1}" for i in range(df.shape[1])]
    return df


def _is_number(x) -> bool:
    try:
        float(str(x))
        return True
    except ValueError:
        return False


def guess_time_column(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        if str(c).lower() in ("time", "datetime", "timestamp", "date"):
            return c
    for c in df.columns[:3]:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            return c
        if pd.api.types.is_numeric_dtype(df[c]):
            continue  # numbers are readings, never timestamps, however pandas would parse them
        parsed = pd.to_datetime(df[c].astype(str), errors="coerce", format="mixed")
        if parsed.notna().mean() > 0.9:
            return c
    return None


def numeric_columns(df: pd.DataFrame, exclude: str | None = None, min_fraction: float = 0.6) -> list[str]:
    """Columns that are mostly numeric readings: datetimes, the time column and
    identifiers (near-constant) are not measurements."""
    out = []
    for c in df.columns:
        if c == exclude or pd.api.types.is_datetime64_any_dtype(df[c]):
            continue
        v = pd.to_numeric(df[c], errors="coerce")
        if v.notna().mean() >= min_fraction and v.nunique(dropna=True) > 2:
            out.append(c)
    return out


def short_names(units: list[str]) -> dict[str, str]:
    """'Car 01 - Indoor Average Temperature' -> '01': strip the longest common
    prefix and suffix so labels show only what differs between units."""
    names = [str(u) for u in units]
    if len(names) < 2:
        return {u: str(u) for u in units}
    import os
    pre = os.path.commonprefix(names)
    suf = os.path.commonprefix([n[::-1] for n in names])[::-1]
    # back the cut off to a word boundary so 'Car 01' / 'Car 02' keep their '0'
    while pre and pre[-1] not in " -_:/":
        pre = pre[:-1]
    while suf and suf[0] not in " -_:/":
        suf = suf[1:]
    out = {}
    for u, n in zip(units, names):
        core = n[len(pre):len(n) - len(suf)] if len(n) > len(pre) + len(suf) else n
        out[u] = core.strip(" -_:") or n
    return out


def peer_ranking(df: pd.DataFrame, units: list[str], min_points: int = 20,
                 hot_threshold: float = 2.0) -> pd.DataFrame:
    """Rank units by mean excess over the contemporaneous median of the other units."""
    x = df[units].apply(pd.to_numeric, errors="coerce")
    rows = []
    for u in units:
        peers = x.drop(columns=u).median(axis=1)
        delta = (x[u] - peers).dropna()
        if len(delta) < min_points:
            rows.append({"unit": u, "excess_mean": np.nan, "excess_q90": np.nan,
                         "hot_fraction": np.nan, "points": int(len(delta))})
            continue
        rows.append({"unit": u, "excess_mean": float(delta.mean()), "excess_q90": float(delta.quantile(0.9)),
                     "hot_fraction": float((delta > hot_threshold).mean()), "points": int(len(delta))})
    out = pd.DataFrame(rows)
    out.insert(1, "label", out["unit"].map(short_names(units)))
    out["rank"] = out["excess_mean"].rank(ascending=False, method="first", na_option="bottom").astype(int)
    return out.sort_values("rank").reset_index(drop=True)


def peer_excess_series(df: pd.DataFrame, units: list[str], time_col: str | None) -> pd.DataFrame:
    x = df[units].apply(pd.to_numeric, errors="coerce")
    ex = pd.DataFrame({u: x[u] - x.drop(columns=u).median(axis=1) for u in units})
    ex.insert(0, "time", pd.to_datetime(df[time_col], errors="coerce") if time_col else np.arange(len(df)))
    step = max(1, len(ex) // 800)
    return ex.iloc[::step].reset_index(drop=True)


def drift_screen(series: pd.Series, window: int = 50) -> pd.DataFrame:
    """Rolling-median drift with a MAD-scaled robust score per window."""
    s = pd.to_numeric(series, errors="coerce").dropna().reset_index(drop=True)
    med = float(s.median())
    mad = float((s - med).abs().median()) or 1e-9
    roll = s.rolling(window, min_periods=max(5, window // 5)).median()
    score = (roll - med) / (1.4826 * mad)
    return pd.DataFrame({"index": s.index, "value": s, "rolling_median": roll, "robust_z": score})


def verdict_for_ranking(rank: pd.DataFrame, unit_label: str) -> tuple[str, str, str]:
    r = rank.dropna(subset=["excess_mean"])
    if len(r) < 2:
        return ("unknown", "Not enough units with overlapping data", "At least two units need 20 shared readings.")
    top, second = r.iloc[0], r.iloc[1]
    gap = float(top["excess_mean"] - second["excess_mean"])
    spread = float(r["excess_mean"].std() or 1e-9)
    if gap > spread:
        return ("alert", f"{unit_label} {top['label']} stands apart from its peers",
                f"Mean excess {top['excess_mean']:+.2f} against {unit_label} {second['label']} at {second['excess_mean']:+.2f}; the gap exceeds the spread across units.")
    return ("watch", f"{unit_label} {top['label']} ranks first, but the margin is narrow",
            f"Gap to {unit_label} {second['label']} is {gap:.2f} against a spread of {spread:.2f}. Treat the top two as candidates.")
