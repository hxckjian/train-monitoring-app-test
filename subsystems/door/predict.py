"""Public inference interface for the Door subsystem.

    from subsystems.door.predict import predict
    result = predict([uploaded_file])

Importing this module loads nothing and trains nothing. Artifacts are resolved
relative to this module, so the folder can be copied into another project and
still work.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import pandas as pd

from .features import (
    CURRENT,
    DEFAULT_GAP_SECONDS,
    EMF,
    FEATURE_COLUMNS,
    LABEL_ABNORMAL,
    POSITION,
    VALID_LABELS,
    VOLTAGE,
    clean_data,
    extract_features,
    format_predictions,
    load_input,
    segment_data,
    validate_input,
)

MODULE_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = MODULE_DIR / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "model.joblib"
CONFIG_PATH = ARTIFACT_DIR / "config.json"

OUTPUT_COLUMNS: tuple[str, ...] = ("start_time", "end_time", "prediction")


@lru_cache(maxsize=1)
def load_saved_model() -> tuple[Any, dict]:
    """Load the trained model and its config. Cached per process."""
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"model artifact not found at {MODEL_PATH}. "
            "Train it first:  python -m subsystems.door.train"
        )
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"config artifact not found at {CONFIG_PATH}. "
            "Train it first:  python -m subsystems.door.train"
        )
    model = joblib.load(MODEL_PATH)
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    saved_cols = config.get("feature_columns")
    if saved_cols is not None and list(saved_cols) != list(FEATURE_COLUMNS):
        raise RuntimeError(
            "feature columns in features.py no longer match the saved model. "
            "Retrain:  python -m subsystems.door.train"
        )
    return model, config


def validate_uploaded_files(uploaded_files: Sequence[Any]) -> list[Any]:
    """Accept a list of file-like objects, or tolerate a single one."""
    if uploaded_files is None:
        raise ValueError("no files provided; expected a list of uploaded files")
    if hasattr(uploaded_files, "read") or isinstance(uploaded_files, (str, Path)):
        uploaded_files = [uploaded_files]          # tolerate a bare handle
    files = list(uploaded_files)
    if not files:
        raise ValueError("no files provided; expected at least one uploaded file")
    return files


def _run_file(uploaded_file: Any, model: Any, gap_seconds: float):
    """The single inference path. predict() and analyze() both go through it."""
    raw = load_input(uploaded_file)
    validate_input(raw)
    df = clean_data(raw)

    segments = segment_data(df, gap_seconds)
    if not segments:
        return df, segments, pd.DataFrame(columns=list(FEATURE_COLUMNS)), [], []

    features = extract_features(df, segments)
    labels = [str(x) for x in model.predict(features)]
    bad = sorted(set(labels) - set(VALID_LABELS))
    if bad:                                        # pragma: no cover - guard
        raise RuntimeError(f"model produced labels outside the allowed set: {bad}")

    classes = [str(c) for c in model.classes_]
    p_abn = model.predict_proba(features)[:, classes.index(LABEL_ABNORMAL)]
    return df, segments, features, labels, list(map(float, p_abn))


def _predict_one(uploaded_file: Any, model: Any, gap_seconds: float) -> pd.DataFrame:
    _, segments, _, labels, _ = _run_file(uploaded_file, model, gap_seconds)
    if not segments:
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS))
    return format_predictions(segments, labels)


def analyze(uploaded_files) -> dict:
    """predict() plus the evidence the app displays: per-cycle probabilities and
    features, and the raw signal traces. Same inference path as predict()."""
    files = validate_uploaded_files(uploaded_files)
    model, config = load_saved_model()
    gap_seconds = float(config.get("gap_seconds", DEFAULT_GAP_SECONDS))

    runs = [_run_file(f, model, gap_seconds) for f in files]
    origin = min((r[0]["_t"].iloc[0] for r in runs if len(r[0])), default=None)

    cycles, traces, preds = [], [], []
    for file_idx, (df, segments, features, labels, p_abn) in enumerate(runs):
        if not segments:
            continue
        preds.append(format_predictions(segments, labels))
        t_s = (df["_t"] - origin).dt.total_seconds().to_numpy()
        cycle_id = np.full(len(df), -1)
        for k, seg in enumerate(segments):
            n = len(cycles) + 1
            cycle_id[seg.start_idx: seg.end_idx + 1] = n
            cycles.append({
                "cycle": n,
                "file": getattr(files[file_idx], "name", f"file{file_idx + 1}"),
                "start_time": format_predictions([seg], [labels[k]]).iloc[0]["start_time"],
                "end_time": format_predictions([seg], [labels[k]]).iloc[0]["end_time"],
                "start_s": float(t_s[seg.start_idx]),
                "end_s": float(t_s[seg.end_idx]),
                "prediction": labels[k],
                "p_abnormal": p_abn[k],
                "operation": "Close" if features.iloc[k]["is_closing"] >= 0.5 else "Open",
                "duration_s": float(features.iloc[k]["duration_s"]),
                "cur_mean_mid": float(features.iloc[k]["cur_mean_mid"]),
                "cur_per_emf": float(features.iloc[k]["cur_per_emf"]),
            })
        traces.append(pd.DataFrame({
            "t_s": t_s,
            "cycle": cycle_id,
            "current_mA": df[CURRENT].to_numpy(dtype=float),
            "voltage": df[VOLTAGE].to_numpy(dtype=float),
            "emf": df[EMF].to_numpy(dtype=float),
            "position": df[POSITION].to_numpy(dtype=float),
        }))

    predictions = (pd.concat(preds, ignore_index=True) if preds
                   else pd.DataFrame(columns=list(OUTPUT_COLUMNS)))
    return {
        "predictions": predictions[list(OUTPUT_COLUMNS)],
        "cycles": pd.DataFrame(cycles),
        "trace": pd.concat(traces, ignore_index=True) if traces else pd.DataFrame(),
        "config": config,
    }


def predict(uploaded_files) -> pd.DataFrame:
    """Accept a list of uploaded file-like objects and return a
    submission-ready prediction DataFrame.

    Each uploaded file is an independent continuous stream and is segmented on
    its own; results are concatenated and sorted by start time. Door's
    submission schema has no file_id column (the held-out test set is a single
    stream), so timestamps are what distinguish rows.

    Returns a DataFrame with columns start_time, end_time, prediction - one row
    per detected door cycle - ready for `result.to_csv(path, index=False)`.
    """
    files = validate_uploaded_files(uploaded_files)
    model, config = load_saved_model()
    gap_seconds = float(config.get("gap_seconds", DEFAULT_GAP_SECONDS))

    frames = [_predict_one(f, model, gap_seconds) for f in files]
    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=list(OUTPUT_COLUMNS))

    if not result.empty:
        order = pd.to_datetime(
            result["start_time"].str.replace(
                r"^(\d+)-(\d+)-(\d+)-(\d+)-(\d+)-(\d+)-(\d+)$",
                r"\1-\2-\3 \4:\5:\6.\7", regex=True),
            format="mixed",
        )
        result = (result.assign(_o=order)
                        .sort_values("_o", kind="stable")
                        .drop(columns="_o")
                        .reset_index(drop=True))

    return result[list(OUTPUT_COLUMNS)]
