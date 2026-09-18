"""Shared validation, cleaning, and feature extraction for rail corrugation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO

import numpy as np
import pandas as pd

SAMPLE_RATE_HZ = 10_000.0
MIN_SAMPLES = 10_000
LABELS = ("Normal", "Side I", "Side II")

_SENSOR_RE = re.compile(
    r"^(Vibration|Shock) of bearing in position ([1-8]) of car ([1-8])$"
)


def expected_columns() -> list[str]:
    columns = ["Rotating speed"]
    for car in range(1, 9):
        for position in range(1, 9):
            columns.extend(
                [
                    f"Vibration of bearing in position {position} of car {car}",
                    f"Shock of bearing in position {position} of car {car}",
                ]
            )
    return columns


def load_input(source: str | Path | BinaryIO) -> pd.DataFrame:
    """Read a CSV path or binary file-like upload without mutating it."""
    try:
        return pd.read_csv(source)
    except Exception as exc:
        raise ValueError(f"Could not read input as CSV: {exc}") from exc


def validate_input(frame: pd.DataFrame) -> None:
    expected = expected_columns()
    if frame.columns.tolist() != expected:
        missing = [c for c in expected if c not in frame.columns]
        extra = [c for c in frame.columns if c not in expected]
        order_problem = not missing and not extra
        detail = (
            "columns are not in the documented order"
            if order_problem
            else f"missing={missing[:3]}, unexpected={extra[:3]}"
        )
        raise ValueError(f"Invalid rail-corrugation schema: {detail}.")
    if len(frame) != MIN_SAMPLES:
        raise ValueError(
            f"Input has {len(frame)} samples; exactly {MIN_SAMPLES} are required."
        )
    if frame.columns.duplicated().any():
        raise ValueError("Input contains duplicate column names.")


def clean_data(frame: pd.DataFrame) -> np.ndarray:
    """Convert to finite float data, rejecting missing or invalid readings."""
    numeric = frame.apply(pd.to_numeric, errors="coerce")
    values = numeric.to_numpy(dtype=np.float32, copy=True)
    if not np.isfinite(values).all():
        raise ValueError(
            "Sensor readings must be numeric with no missing or infinite values. Re-export the complete recording."
        )
    if not np.isin(values[:, 0], [0, 1]).all():
        raise ValueError("Rotating speed must contain binary 0/1 pulses.")
    return values


def _summarize(values: np.ndarray, prefix: str, output: dict[str, float]) -> None:
    flat = np.asarray(values, dtype=np.float64).ravel()
    output[f"{prefix}_mean"] = float(np.mean(flat))
    output[f"{prefix}_std"] = float(np.std(flat))
    output[f"{prefix}_median"] = float(np.median(flat))
    output[f"{prefix}_q90"] = float(np.quantile(flat, 0.90))
    output[f"{prefix}_max"] = float(np.max(flat))


def extract_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Extract one row of side-aware time and frequency-domain features."""
    validate_input(frame)
    data = clean_data(frame)
    result: dict[str, float] = {}

    speed = data[:, 0]
    transitions = np.count_nonzero(np.diff(speed) != 0)
    result["speed_duty_cycle"] = float(np.mean(speed))
    result["speed_transitions"] = float(transitions)
    result["speed_transition_rate"] = float(transitions / max(1, len(speed) - 1))

    groups: dict[tuple[str, str], list[int]] = {
        (side, kind): []
        for side in ("side_i", "side_ii")
        for kind in ("vibration", "shock")
    }
    for index, column in enumerate(frame.columns[1:], start=1):
        match = _SENSOR_RE.match(column)
        if match is None:  # guarded by validate_input; retained as an invariant check
            raise ValueError(f"Unrecognised sensor column: {column}")
        kind, position, _car = match.groups()
        side = "side_i" if int(position) % 2 else "side_ii"
        groups[(side, kind.lower())].append(index)

    bands = ((0, 100), (100, 300), (300, 700), (700, 1500), (1500, 3000), (3000, 5000))
    for (side, kind), indices in groups.items():
        signal = data[:, indices].astype(np.float64)
        centered = signal - np.mean(signal, axis=0, keepdims=True)
        std = np.std(centered, axis=0)
        rms = np.sqrt(np.mean(signal * signal, axis=0))
        abs_peak = np.max(np.abs(centered), axis=0)
        ptp = np.ptp(signal, axis=0)
        fourth = np.mean(centered**4, axis=0)
        kurtosis = fourth / np.maximum(std**4, 1e-12)
        crest = abs_peak / np.maximum(rms, 1e-8)
        prefix = f"{side}_{kind}"
        for metric_name, metric in (
            ("std", std),
            ("rms", rms),
            ("abs_peak", abs_peak),
            ("ptp", ptp),
            ("kurtosis", kurtosis),
            ("crest", crest),
        ):
            _summarize(metric, f"{prefix}_{metric_name}", result)

        spectrum = np.abs(np.fft.rfft(centered, axis=0)) ** 2
        frequencies = np.fft.rfftfreq(len(centered), d=1.0 / SAMPLE_RATE_HZ)
        total_power = np.maximum(np.sum(spectrum[1:], axis=0), 1e-12)
        dominant = frequencies[1:][np.argmax(spectrum[1:], axis=0)]
        _summarize(dominant, f"{prefix}_dominant_hz", result)
        for low, high in bands:
            include = (frequencies >= low) & (frequencies < high)
            if low == 0:
                include[0] = False
            relative = np.sum(spectrum[include], axis=0) / total_power
            _summarize(relative, f"{prefix}_relpow_{low}_{high}", result)

    # Explicit signed contrasts make fault localisation easier for a small,
    # imbalanced dataset than asking every tree to rediscover paired sides.
    for kind in ("vibration", "shock"):
        prefix_i = f"side_i_{kind}_"
        for key_i in [key for key in result if key.startswith(prefix_i)]:
            suffix = key_i[len(prefix_i) :]
            key_ii = f"side_ii_{kind}_{suffix}"
            if key_ii in result:
                result[f"side_contrast_{kind}_{suffix}"] = (
                    result[key_i] - result[key_ii]
                )

    return pd.DataFrame([result], dtype=np.float64)


def extract_file_features(path: str | Path) -> pd.DataFrame:
    return extract_features(load_input(path))
