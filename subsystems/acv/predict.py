"""Public inference interface for the ACV (air conditioning) subsystem.

    from subsystems.acv.predict import predict
    predict([uploaded_xlsx, ...])  ->  DataFrame(file_id, ranked_cars)

Ranking rule and parser ported unchanged from the teammate's
final_streamlit_app build: during valid cooling, each car's cabin temperature
minus the contemporaneous median of the other cars, averaged over time. The
bundled artifact stores model=None (the fixed rule) plus its feature contract.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import pandas as pd

from .features import ALIASES, extract_features, load, rank_scores

MODULE_DIR = Path(__file__).resolve().parent
MODEL_PATH = MODULE_DIR / "artifacts" / "model.joblib"
CONFIG_PATH = MODULE_DIR / "artifacts" / "config.json"
OUTPUT_COLUMNS: tuple[str, ...] = ("file_id", "ranked_cars")


@lru_cache(maxsize=1)
def load_saved_model() -> tuple[dict, dict]:
    for p in (MODEL_PATH, CONFIG_PATH):
        if not p.exists():
            raise FileNotFoundError(f"artifact not found: {p}")
    artifact = joblib.load(MODEL_PATH)
    if not artifact.get("feature_names"):
        raise RuntimeError("acv artifact has no feature contract; restore artifacts/")
    return artifact, json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _file_id(f: Any) -> str:
    return str(getattr(f, "name", "")).replace("\\", "/").split("/")[-1]


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
    if any(not n.lower().endswith(".xlsx") for n in names):
        raise ValueError("ACV cases are .xlsx workbooks, one case per file")
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(f"duplicate file names would collide as file_id: {dupes}")
    return files


def _cooling_temperatures(frame: pd.DataFrame, cars: list[str]):
    """The same masking extract_features applies, kept for the timeline display."""
    indoor, target = {}, {}
    for car in cars:
        cols = {k: next((f"Car {car} - {s}" for s in al if f"Car {car} - {s}" in frame), None)
                for k, al in ALIASES.items()}
        t = pd.to_numeric(frame[cols["indoor"]], errors="coerce")
        goal = pd.to_numeric(frame[cols["target"]], errors="coerce")
        mask = frame[cols["mode"]].astype(str).str.contains("cool", case=False)
        if cols["valid"]:
            mask &= frame[cols["valid"]].astype(str).str.lower().eq("valid")
        mask &= t.between(-20, 70) & goal.between(5, 45)
        if mask.sum() < 20:
            mask[:] = False
        indoor[car], target[car] = t.where(mask), goal.where(mask)
    return pd.DataFrame(indoor), pd.DataFrame(target)


def _process(f: Any, artifact: dict, evidence: bool) -> dict:
    name = _file_id(f)
    try:
        frame, cars = load(f)
        feats = extract_features(frame, cars)
        x = feats.loc[:, artifact["feature_names"]].copy()
        x.attrs["unobserved"] = feats.attrs.get("unobserved", [])
        scores = rank_scores(x, artifact.get("model"))
    except ValueError as exc:
        raise ValueError(f"{name}: {exc}") from exc
    order = np.argsort(-scores, kind="stable")
    ranked = [cars[i] for i in order]
    out = {"file_id": name, "ranked_cars": "|".join(ranked), "ranking": ranked,
           "scores": {cars[i]: (None if not np.isfinite(scores[i]) else float(scores[i]))
                      for i in range(len(cars))},
           "unobserved": list(x.attrs["unobserved"])}
    if evidence:
        temps, targets = _cooling_temperatures(frame, cars)
        times = pd.to_datetime(frame["Time"], errors="coerce")
        step = max(1, len(frame) // 800)
        peers = pd.DataFrame({c: temps.drop(columns=c).median(axis=1) for c in cars})
        out.update({
            "n_readings": int(len(frame)),
            "cooling_readings": {c: int(temps[c].notna().sum()) for c in cars},
            "timeline": pd.DataFrame({"time": times}).join(temps)
                          .iloc[::step].reset_index(drop=True),
            "excess_timeline": pd.DataFrame({"time": times}).join(temps - peers)
                                 .iloc[::step].reset_index(drop=True),
            "target_mean": {c: (None if targets[c].isna().all() else float(targets[c].mean()))
                            for c in cars},
        })
    return out


def analyze(uploaded_files, progress=None) -> dict:
    files = validate_uploaded_files(uploaded_files)
    artifact, config = load_saved_model()
    results = []
    for i, f in enumerate(files, 1):
        results.append(_process(f, artifact, evidence=True))
        if progress is not None:
            progress(i, len(files), results[-1]["file_id"])
    predictions = pd.DataFrame([(r["file_id"], r["ranked_cars"]) for r in results],
                               columns=list(OUTPUT_COLUMNS))
    return {"predictions": predictions, "files": results, "config": config}


def predict(uploaded_files) -> pd.DataFrame:
    """Submission-ready DataFrame: file_id, ranked_cars ('03|01|...', every car)."""
    files = validate_uploaded_files(uploaded_files)
    artifact, _ = load_saved_model()
    rows = [_process(f, artifact, evidence=False) for f in files]
    return pd.DataFrame([(r["file_id"], r["ranked_cars"]) for r in rows],
                        columns=list(OUTPUT_COLUMNS))
