"""Public inference interface for the SHM subsystem.

    from subsystems.shm.predict import predict
    result = predict([uploaded_file, ...])

One row per uploaded file. Importing this module loads nothing and trains
nothing; artifacts resolve relative to this module.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

import joblib
from core import drift as _drift
import numpy as np
import pandas as pd

from .features import (
    amplitude_profile,
    damage_concentration,
    format_predictions,
    load_input,
    predict_damage,
    rainflow_cycles,
    stress_envelope,
    validate_input,
)

MODULE_DIR = Path(__file__).resolve().parent
MODEL_PATH = MODULE_DIR / "artifacts" / "model.joblib"
CONFIG_PATH = MODULE_DIR / "artifacts" / "config.json"
OUTPUT_COLUMNS: tuple[str, ...] = ("file_id", "prediction")


@lru_cache(maxsize=1)
def load_saved_model() -> tuple[dict, dict]:
    for p in (MODEL_PATH, CONFIG_PATH):
        if not p.exists():
            raise FileNotFoundError(
                f"artifact not found: {p}. Train first:  python -m subsystems.shm.train")
    params = joblib.load(MODEL_PATH)
    for key in ("m", "log_c", "log_ref"):
        if key not in params:
            raise RuntimeError(f"model artifact is missing '{key}'; retrain")
    return params, json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def validate_uploaded_files(uploaded_files: Sequence[Any]) -> list[Any]:
    if uploaded_files is None:
        raise ValueError("no files provided; expected a list of uploaded files")
    if hasattr(uploaded_files, "read") or isinstance(uploaded_files, (str, Path)):
        uploaded_files = [uploaded_files]
    files = list(uploaded_files)
    if not files:
        raise ValueError("no files provided; expected at least one uploaded file")
    names = [getattr(f, "name", None) for f in files]
    if any(n is None for n in names):
        raise ValueError("every uploaded file needs a .name - it becomes the file_id")
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(f"duplicate file names would collide as file_id: {dupes}")
    return files


def _process(uploaded_file: Any, params: dict, evidence: bool) -> dict:
    name = str(uploaded_file.name)
    x = load_input(uploaded_file)
    validate_input(x, name)
    cycles = rainflow_cycles(x)
    damage = predict_damage(cycles, params["m"], params["log_c"], params["log_ref"])
    out = {"file_id": name, "damage": damage}
    if evidence:
        out.update({
            "n_samples": int(x.size),
            "n_cycles": cycles.n_cycles,
            "stress_min": float(x.min()),
            "stress_max": float(x.max()),
            "stress_std": float(x.std()),
            "max_range": float(cycles.rng.max()),
            "top_share": damage_concentration(cycles, params["m"], 0.001),
            "profile": amplitude_profile(cycles, params["m"]),
            "envelope": stress_envelope(x),
            "drift": _drift.score("shm", {"stress_std": float(x.std()), "stress_max": float(x.max()),
                                          "stress_min": float(x.min()),
                                          "stress_p99_range": float(np.percentile(x, 99.9) - np.percentile(x, 0.1)),
                                          "n_samples": int(x.size)}),
        })
    return out


def analyze(uploaded_files, progress=None) -> dict:
    """predict() plus the evidence the app displays. Same computation path.

    `progress`, if given, is called as progress(i, n, file_id) after each file.
    """
    files = validate_uploaded_files(uploaded_files)
    params, config = load_saved_model()
    results = []
    for i, f in enumerate(files, 1):
        results.append(_process(f, params, evidence=True))
        if progress is not None:
            progress(i, len(files), results[-1]["file_id"])
    predictions = format_predictions([r["file_id"] for r in results],
                                     [r["damage"] for r in results])
    return {"predictions": predictions, "files": results, "config": config}


def predict(uploaded_files) -> pd.DataFrame:
    """Accept a list of uploaded file-like objects and return a
    submission-ready prediction DataFrame: file_id, prediction."""
    files = validate_uploaded_files(uploaded_files)
    params, _ = load_saved_model()
    rows = [_process(f, params, evidence=False) for f in files]
    result = format_predictions([r["file_id"] for r in rows], [r["damage"] for r in rows])
    if not np.all(np.isfinite(result["prediction"])):         # pragma: no cover
        raise RuntimeError("non-finite damage prediction")
    return result[list(OUTPUT_COLUMNS)]
