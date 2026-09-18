"""Public inference interface for the Rail Corrugation subsystem.

    from subsystems.rail.predict import predict
    predict([uploaded_file, ...])  ->  DataFrame(file_id, prediction)

The model and feature code were ported unchanged from the teammate's
final_streamlit_app build (balanced RandomForest on per-side time and
frequency-domain features). analyze() adds the evidence the console shows -
per-axle-box energy, per-side spectra in the wavelength domain, class
probabilities and the measured speed - computed on the same feature path.
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
    LABELS, SAMPLE_RATE_HZ, _SENSOR_RE, clean_data, extract_features, load_input,
)
from .wavelength import wavelength_features

MODULE_DIR = Path(__file__).resolve().parent
MODEL_PATH = MODULE_DIR / "artifacts" / "model.joblib"
CONFIG_PATH = MODULE_DIR / "artifacts" / "config.json"
OUTPUT_COLUMNS: tuple[str, ...] = ("file_id", "prediction")
TEETH, WHEEL_DIAMETER_M = 90, 0.85


@lru_cache(maxsize=1)
def load_saved_model() -> tuple[dict, dict]:
    for p in (MODEL_PATH, CONFIG_PATH):
        if not p.exists():
            raise FileNotFoundError(f"artifact not found: {p}")
    artifact = joblib.load(MODEL_PATH)
    names, model = artifact.get("feature_names", []), artifact.get("model")
    if not names or model is None or list(getattr(model, "feature_names_in_", [])) != names:
        raise RuntimeError("rail artifact and its saved feature order disagree; restore artifacts/")
    return artifact, json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def validate_uploaded_files(uploaded_files: Sequence[Any]) -> list[Any]:
    if uploaded_files is None:
        raise ValueError("no files provided; expected a list of uploaded files")
    if hasattr(uploaded_files, "read") or isinstance(uploaded_files, (str, Path)):
        uploaded_files = [uploaded_files]
    files = list(uploaded_files)
    if not files:
        raise ValueError("no files provided; expected at least one uploaded file")
    names = [_file_id(f) for f in files]
    if any(not n for n in names):
        raise ValueError("every uploaded file needs a .name - it becomes the file_id")
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(f"duplicate file names would collide as file_id: {dupes}")
    return files


def _file_id(f: Any) -> str:
    return str(getattr(f, "name", "")).replace("\\", "/").split("/")[-1]


def _feature_matrix(x: pd.DataFrame, artifact: dict) -> pd.DataFrame:
    names = artifact["feature_names"]
    if any(n not in x for n in names):
        raise RuntimeError("feature code does not match the bundled model")
    sel = x.loc[:, names]
    if not np.isfinite(sel.to_numpy(dtype=float)).all():
        raise ValueError("sensor values produce non-finite features; check the signal scale")
    return sel


def speed_from_pulses(pulses: np.ndarray) -> dict:
    """90-tooth wheel, 0.85 m diameter: each tooth is one 0->1 and one 1->0."""
    transitions = int(np.count_nonzero(np.diff(pulses) != 0))
    seconds = len(pulses) / SAMPLE_RATE_HZ
    rps = transitions / (2 * TEETH) / seconds
    v = rps * np.pi * WHEEL_DIAMETER_M
    return {"transitions": transitions, "rev_per_s": float(rps),
            "speed_m_s": float(v), "speed_km_h": float(v * 3.6)}


def _evidence(frame: pd.DataFrame, data: np.ndarray) -> dict:
    """Per-axle-box RMS grid and per-side mean vibration spectra."""
    cells, side_cols = [], {"Side I": [], "Side II": []}
    for idx, col in enumerate(frame.columns[1:], start=1):
        m = _SENSOR_RE.match(col)
        kind, pos, car = m.group(1), int(m.group(2)), int(m.group(3))
        if kind != "Vibration":
            continue
        sig = data[:, idx].astype(np.float64)
        sig = sig - sig.mean()
        side = "Side I" if pos % 2 else "Side II"
        cells.append({"car": car, "position": pos, "side": side,
                      "rms": float(np.sqrt(np.mean(sig * sig)))})
        side_cols[side].append(idx)
    grid = pd.DataFrame(cells)
    grid["value"] = grid["rms"] / max(float(grid["rms"].max()), 1e-12)

    freqs = np.fft.rfftfreq(len(data), d=1.0 / SAMPLE_RATE_HZ)
    edges = np.geomspace(10, SAMPLE_RATE_HZ / 2, 61)
    spectra = {}
    for side, idxs in side_cols.items():
        sig = data[:, idxs].astype(np.float64)
        sig = sig - sig.mean(axis=0, keepdims=True)
        p = (np.abs(np.fft.rfft(sig, axis=0)) ** 2).mean(axis=1)
        binned = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            sel = (freqs >= lo) & (freqs < hi)
            binned.append(float(p[sel].mean()) if sel.any() else np.nan)
        spectra[side] = binned
    spec = pd.DataFrame({"f_hz": np.sqrt(edges[:-1] * edges[1:]), **spectra})
    return {"grid": grid, "spectrum": spec}


def _process(f: Any, artifact: dict, evidence: bool) -> dict:
    name = _file_id(f)
    try:
        frame = load_input(f)
        x = extract_features(frame)
        if any("_wl_" in n for n in artifact["feature_names"]):
            x = x.assign(**wavelength_features(frame, clean_data(frame)))
        X = _feature_matrix(x, artifact)
        model = artifact["model"]
        label = str(model.predict(X)[0])
        proba = dict(zip((str(c) for c in model.classes_),
                         map(float, model.predict_proba(X)[0])))
    except ValueError as exc:
        raise ValueError(f"{name}: {exc}") from exc
    out = {"file_id": name, "prediction": label, "proba": proba}
    if evidence:
        data = clean_data(frame)
        speed = speed_from_pulses(data[:, 0])
        ev = _evidence(frame, data)
        if speed["speed_m_s"] > 0:
            ev["spectrum"]["wavelength_cm"] = 100.0 * speed["speed_m_s"] / ev["spectrum"]["f_hz"]
        g = ev["grid"]
        out.update({"speed": speed, "grid": g, "spectrum": ev["spectrum"],
                    "side_i_rms": float(g.loc[g.side == "Side I", "rms"].mean()),
                    "side_ii_rms": float(g.loc[g.side == "Side II", "rms"].mean())})
    return out


def analyze(uploaded_files, progress=None) -> dict:
    files = validate_uploaded_files(uploaded_files)
    artifact, config = load_saved_model()
    results = []
    for i, f in enumerate(files, 1):
        results.append(_process(f, artifact, evidence=True))
        if progress is not None:
            progress(i, len(files), results[-1]["file_id"])
    predictions = pd.DataFrame([(r["file_id"], r["prediction"]) for r in results],
                               columns=list(OUTPUT_COLUMNS))
    return {"predictions": predictions, "files": results, "config": config,
            "labels": list(LABELS)}


def predict(uploaded_files) -> pd.DataFrame:
    """Submission-ready DataFrame: file_id, prediction (Normal / Side I / Side II)."""
    files = validate_uploaded_files(uploaded_files)
    artifact, _ = load_saved_model()
    rows = [_process(f, artifact, evidence=False) for f in files]
    return pd.DataFrame([(r["file_id"], r["prediction"]) for r in rows],
                        columns=list(OUTPUT_COLUMNS))
