"""Shared data processing for the Door subsystem.

Every function here is used by BOTH train.py and predict.py. There is no second
implementation anywhere - if a feature changes, it changes for training and
inference at the same time, which is the only way the two can be trusted to
agree.

Deterministic throughout: no randomness, no global state, no I/O beyond reading
the file handed in.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Schema, as verified against repo/PS3/02_Datasets/Door/Train.csv
# --------------------------------------------------------------------------

TIME_COL = "Datetime"

REQUIRED_COLUMNS: tuple[str, ...] = (
    "Datetime",
    "Motor current(mA)",
    "Motor Voltage(10mV)",
    "Motor electrodynamic force",
    "Door opening time(.1s)",
    "Door closing time(.1s)",
    "Close command",
    "Open command",
    "DCSR",
    "DCSL",
    "DLSR",
    "DLSL",
    "Door Opened",
    "Door Locked",
    "Door is opening",
    "Door is closing",
    "Door leaf position",
)

CURRENT = "Motor current(mA)"
VOLTAGE = "Motor Voltage(10mV)"
EMF = "Motor electrodynamic force"
POSITION = "Door leaf position"
OPENING = "Door is opening"
CLOSING = "Door is closing"
SWITCHES = ("DCSR", "DCSL", "DLSR", "DLSL")

LABEL_NORMAL = "Normal"
LABEL_ABNORMAL = "Abnormal resistance"
VALID_LABELS: tuple[str, str] = (LABEL_NORMAL, LABEL_ABNORMAL)

#: Fallback gap threshold in seconds. train.py derives this from the data and
#: saves it as an artifact; this value is only used if no artifact is present.
#: The EDA showed within-cycle intervals of exactly 0.020 s and between-cycle
#: gaps of at least 10.2 s, so anything in [0.05, 5.0] recovers the same
#: segments. This is a wide safe band, not a tuned constant.
DEFAULT_GAP_SECONDS = 1.0


@dataclass(frozen=True)
class RawSegment:
    """One detected cycle: a contiguous run of rows with no large time gap."""
    start_idx: int
    end_idx: int          # inclusive
    start_time: pd.Timestamp
    end_time: pd.Timestamp


# --------------------------------------------------------------------------
# Timestamps
# --------------------------------------------------------------------------

def parse_datetime_series(values: pd.Series) -> pd.Series:
    """Parse the dataset's Year-Month-Day-Hour-Minute-Second-Millisecond stamps.

    The fields are NOT zero-padded ('2023-7-5-0-0-3-760'), and the last field is
    milliseconds rather than microseconds, so neither a format string with %f nor
    a generic inferrer is correct. Split on '-' and rebuild explicitly.
    """
    parts = values.astype(str).str.strip().str.split("-", expand=True)
    if parts.shape[1] != 7:
        raise ValueError(
            f"{TIME_COL} must have 7 hyphen-separated fields "
            f"(Y-M-D-H-M-S-ms); found {parts.shape[1]} in some rows"
        )
    try:
        parts = parts.astype(int)
    except ValueError as exc:
        raise ValueError(f"{TIME_COL} contains a non-numeric field: {exc}") from exc
    parts.columns = ["y", "mo", "d", "h", "mi", "s", "ms"]
    base = pd.to_datetime(
        dict(year=parts.y, month=parts.mo, day=parts.d,
             hour=parts.h, minute=parts.mi, second=parts.s)
    )
    return base + pd.to_timedelta(parts.ms, unit="ms")


def format_datetime(ts: pd.Timestamp) -> str:
    """Render back to the dataset's native format, unpadded.

    The Info Kit accepts either this or an ISO timestamp; we emit the native
    form so our output is byte-comparable with 04_Example_Submission.
    """
    return (f"{ts.year}-{ts.month}-{ts.day}-{ts.hour}-{ts.minute}-"
            f"{ts.second}-{ts.microsecond // 1000}")


# --------------------------------------------------------------------------
# Loading and validation
# --------------------------------------------------------------------------

def load_input(uploaded_file: Any) -> pd.DataFrame:
    """Read one uploaded CSV into a DataFrame.

    Accepts a Streamlit UploadedFile, any binary file-like object with a .name,
    or a path. The handle is rewound first so the same object can be read twice.
    """
    name = getattr(uploaded_file, "name", None)
    if name is not None and not str(name).lower().endswith(".csv"):
        raise ValueError(
            f"Door expects a .csv stream; got '{name}'. "
            "Upload Test.csv or a file in the same format."
        )
    if hasattr(uploaded_file, "seek"):
        try:
            uploaded_file.seek(0)
        except (OSError, ValueError):
            pass
    try:
        df = pd.read_csv(uploaded_file)
    except Exception as exc:
        raise ValueError(f"could not read '{name or uploaded_file}' as CSV: {exc}") from exc
    if df.empty:
        raise ValueError(f"'{name or uploaded_file}' contains no data rows")
    return df


def validate_input(df: pd.DataFrame) -> None:
    """Fail loudly and specifically on anything the pipeline cannot handle."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            "input is missing required column(s): "
            + ", ".join(repr(m) for m in missing)
            + f". Expected the 17-column Door schema, found {len(df.columns)} columns."
        )
    numeric = [c for c in REQUIRED_COLUMNS if c != TIME_COL]
    bad = [c for c in numeric if not pd.api.types.is_numeric_dtype(df[c])]
    if bad:
        raise ValueError(f"column(s) must be numeric but are not: {bad}")


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Parse time, sort, drop exact duplicate timestamps.

    Deliberately does NOT drop the constant 'Door Locked' column: keeping the
    full schema means validate_input stays a real check. Feature selection
    happens in extract_features, where it is visible.
    """
    out = df.copy()
    out["_t"] = parse_datetime_series(out[TIME_COL])
    out = out.sort_values("_t", kind="stable")
    out = out.drop_duplicates(subset="_t", keep="first")
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------
# Segmentation
# --------------------------------------------------------------------------

def segment_data(df: pd.DataFrame,
                 gap_seconds: float = DEFAULT_GAP_SECONDS) -> list[RawSegment]:
    """Cut the continuous stream into cycles at large time gaps.

    The controller only writes rows while a door cycle is in progress, so the
    stream is dense inside a cycle (0.020 s) and silent between cycles (>10 s).
    The boundary is therefore the silence itself, not any status flag - which is
    also what the Info Kit hints at when it warns against assuming the
    opening/closing flags are the robust signal.
    """
    if "_t" not in df.columns:
        raise ValueError("clean_data must run before segment_data")
    if df.empty:
        return []

    t = df["_t"]
    gaps = t.diff().dt.total_seconds().to_numpy()
    # A new cycle starts at row 0 and wherever the preceding gap is large.
    starts = np.flatnonzero(np.nan_to_num(gaps, nan=np.inf) > gap_seconds)
    starts = np.concatenate(([0], starts)) if starts.size == 0 or starts[0] != 0 else starts
    ends = np.concatenate((starts[1:] - 1, [len(df) - 1]))

    return [
        RawSegment(int(s), int(e), t.iloc[int(s)], t.iloc[int(e)])
        for s, e in zip(starts, ends)
        if e >= s
    ]


# --------------------------------------------------------------------------
# Feature engineering
# --------------------------------------------------------------------------

#: Fixed column order. Saved as an artifact and asserted at inference time, so a
#: silent column reordering can never produce a confident wrong prediction.
FEATURE_COLUMNS: tuple[str, ...] = (
    "duration_s", "n_rows",
    "cur_mean", "cur_std", "cur_max", "cur_med", "cur_p25", "cur_p75", "cur_p90",
    "cur_mean_mid", "cur_integral", "cur_above_med_frac",
    "volt_mean", "volt_std",
    "emf_mean", "emf_std", "emf_max",
    "cur_per_volt", "cur_per_emf",
    "pos_min", "pos_max", "pos_range", "pos_travel",
    "frac_opening", "frac_closing", "is_closing",
    "switch_transitions",
)


def _segment_features(seg_df: pd.DataFrame, seg: RawSegment) -> dict[str, float]:
    cur = seg_df[CURRENT].to_numpy(dtype=float)
    volt = seg_df[VOLTAGE].to_numpy(dtype=float)
    emf = seg_df[EMF].to_numpy(dtype=float)
    pos = seg_df[POSITION].to_numpy(dtype=float)
    n = len(seg_df)

    duration = (seg.end_time - seg.start_time).total_seconds()

    # Middle 60% of the cycle: excludes motor inrush at the start and the stop
    # ramp at the end, so this is closer to the sustained load the resistance
    # fault actually changes.
    lo, hi = int(n * 0.2), max(int(n * 0.8), int(n * 0.2) + 1)
    cur_mid = cur[lo:hi]

    frac_opening = float(np.mean(seg_df[OPENING].to_numpy(dtype=float)))
    frac_closing = float(np.mean(seg_df[CLOSING].to_numpy(dtype=float)))

    switch_transitions = 0
    for col in SWITCHES:
        v = seg_df[col].to_numpy(dtype=float)
        switch_transitions += int(np.count_nonzero(np.diff(v)))

    eps = 1e-9
    return {
        "duration_s": duration,
        "n_rows": float(n),
        "cur_mean": float(np.mean(cur)),
        "cur_std": float(np.std(cur)),
        "cur_max": float(np.max(cur)),
        "cur_med": float(np.median(cur)),
        "cur_p25": float(np.percentile(cur, 25)),
        "cur_p75": float(np.percentile(cur, 75)),
        "cur_p90": float(np.percentile(cur, 90)),
        "cur_mean_mid": float(np.mean(cur_mid)) if cur_mid.size else float(np.mean(cur)),
        "cur_integral": float(np.sum(cur) * 0.02),   # mA-seconds at 20 ms sampling
        "cur_above_med_frac": float(np.mean(cur > np.median(cur))),
        "volt_mean": float(np.mean(volt)),
        "volt_std": float(np.std(volt)),
        "emf_mean": float(np.mean(emf)),
        "emf_std": float(np.std(emf)),
        "emf_max": float(np.max(emf)),
        # Current drawn per unit voltage and per unit back-EMF. Back-EMF tracks
        # motor speed, so current-per-EMF is a torque-per-speed proxy - which is
        # what mechanical resistance actually raises.
        "cur_per_volt": float(np.mean(cur) / (np.mean(volt) + eps)),
        "cur_per_emf": float(np.mean(cur) / (np.mean(emf) + eps)),
        "pos_min": float(np.min(pos)),
        "pos_max": float(np.max(pos)),
        "pos_range": float(np.max(pos) - np.min(pos)),
        "pos_travel": float(np.sum(np.abs(np.diff(pos)))) if n > 1 else 0.0,
        "frac_opening": frac_opening,
        "frac_closing": frac_closing,
        "is_closing": 1.0 if frac_closing >= frac_opening else 0.0,
        "switch_transitions": float(switch_transitions),
    }


def extract_features(df: pd.DataFrame,
                     segments: Sequence[RawSegment]) -> pd.DataFrame:
    """One feature row per detected cycle, in FEATURE_COLUMNS order."""
    if not segments:
        return pd.DataFrame(columns=list(FEATURE_COLUMNS))
    rows = [
        _segment_features(df.iloc[seg.start_idx: seg.end_idx + 1], seg)
        for seg in segments
    ]
    out = pd.DataFrame(rows)
    missing = [c for c in FEATURE_COLUMNS if c not in out.columns]
    if missing:                                    # pragma: no cover - guard
        raise RuntimeError(f"feature builder did not produce: {missing}")
    return out[list(FEATURE_COLUMNS)]


# --------------------------------------------------------------------------
# Output formatting
# --------------------------------------------------------------------------

def format_predictions(segments: Sequence[RawSegment],
                       labels: Sequence[str]) -> pd.DataFrame:
    """Build the submission DataFrame: start_time, end_time, prediction.

    No file_id column - Door's test set is one continuous stream, so there is no
    per-file structure to key on (Info Kit Section 3).
    """
    if len(segments) != len(labels):
        raise ValueError(
            f"got {len(segments)} segments but {len(labels)} labels"
        )
    bad = sorted(set(labels) - set(VALID_LABELS))
    if bad:
        raise ValueError(f"invalid label(s) {bad}; allowed: {list(VALID_LABELS)}")
    return pd.DataFrame({
        "start_time": [format_datetime(s.start_time) for s in segments],
        "end_time": [format_datetime(s.end_time) for s in segments],
        "prediction": list(labels),
    })


def make_uploaded_file(path) -> io.BytesIO:
    """Build a Streamlit-like upload object from a path. Used by tests."""
    from pathlib import Path as _Path
    p = _Path(path)
    buf = io.BytesIO(p.read_bytes())
    buf.name = p.name
    return buf
