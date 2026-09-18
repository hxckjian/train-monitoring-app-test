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
import pandas as pd

from .features import (
    DEFAULT_GAP_SECONDS,
    FEATURE_COLUMNS,
    VALID_LABELS,
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


def _predict_one(uploaded_file: Any, model: Any, gap_seconds: float) -> pd.DataFrame:
    raw = load_input(uploaded_file)
    validate_input(raw)
    df = clean_data(raw)

    segments = segment_data(df, gap_seconds)
    if not segments:
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS))

    features = extract_features(df, segments)
    labels = model.predict(features)

    bad = sorted(set(map(str, labels)) - set(VALID_LABELS))
    if bad:                                        # pragma: no cover - guard
        raise RuntimeError(f"model produced labels outside the allowed set: {bad}")

    return format_predictions(segments, [str(x) for x in labels])


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
