"""Submission schemas, validation, and predictions.zip packaging.

Schemas are transcribed from specification Section 4.1 and the four Info Kits.
The app refuses to write a predictions.zip that fails validation: a malformed
file is not scored at all (spec Section 5.1), so a loud error here is always
better than a quiet bad submission.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

_DOOR_TS = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}-\d{1,2}-\d{1,2}-\d{1,2}-\d{1,3}$")
_CAR_ID = re.compile(r"^\d{2}$")


@dataclass(frozen=True)
class SubmissionSchema:
    key: str
    filename: str
    columns: tuple[str, ...]
    labels: frozenset[str] = field(default_factory=frozenset)


SCHEMAS: dict[str, SubmissionSchema] = {
    "door": SubmissionSchema("door", "door_predictions.csv",
                             ("start_time", "end_time", "prediction"),
                             frozenset({"Normal", "Abnormal resistance"})),
    "shm": SubmissionSchema("shm", "shm_predictions.csv", ("file_id", "prediction")),
    "rail": SubmissionSchema("rail", "rail_predictions.csv", ("file_id", "prediction"),
                             frozenset({"Normal", "Side I", "Side II"})),
    "acv": SubmissionSchema("acv", "acv_predictions.csv", ("file_id", "ranked_cars")),
}


def _door_seconds(ts: str) -> float:
    y, mo, d, h, mi, s, ms = (int(p) for p in ts.split("-"))
    return pd.Timestamp(y, mo, d, h, mi, s).timestamp() + ms / 1000.0


def validate_submission(key: str, df: pd.DataFrame,
                        expected_ids: Iterable[str] | None = None) -> list[str]:
    """Return a list of human-readable problems. Empty list = valid."""
    if key not in SCHEMAS:
        return [f"unknown subsystem '{key}'"]
    schema = SCHEMAS[key]
    errors: list[str] = []

    if list(df.columns) != list(schema.columns):
        return [f"columns must be exactly {list(schema.columns)} in that order; "
                f"got {list(df.columns)}"]
    if df.empty:
        return ["no rows"]
    for c in schema.columns:
        if df[c].isna().any():
            errors.append(f"column '{c}' has {int(df[c].isna().sum())} missing value(s)")

    if schema.labels:
        bad = sorted(set(df["prediction"].astype(str)) - schema.labels)
        if bad:
            errors.append(f"invalid label(s) {bad}; allowed {sorted(schema.labels)}")

    if key == "door":
        for c in ("start_time", "end_time"):
            bad = [v for v in df[c].astype(str) if not _DOOR_TS.match(v)]
            if bad:
                errors.append(f"'{c}' not in Y-M-D-H-M-S-ms format, e.g. {bad[0]!r}")
        if not errors:
            dur = [(_door_seconds(e) - _door_seconds(s))
                   for s, e in zip(df["start_time"], df["end_time"])]
            if any(d <= 0 for d in dur):
                errors.append("some segments end at or before they start")

    if key == "shm":
        v = pd.to_numeric(df["prediction"], errors="coerce").to_numpy()
        if np.isnan(v).any():
            errors.append("prediction must be numeric")
        elif not np.all(np.isfinite(v)) or np.any(v <= 0):
            errors.append("prediction must be positive and finite (MAPE divides by it)")

    if key == "acv":
        for fid, ranked in zip(df["file_id"], df["ranked_cars"].astype(str)):
            cars = ranked.split("|")
            if not all(_CAR_ID.match(c) for c in cars):
                errors.append(f"{fid}: car ids must be two digits as in the file "
                              f"headers, e.g. '03'; got {ranked!r}")
            if len(set(cars)) != len(cars):
                errors.append(f"{fid}: a car is ranked twice")

    if key != "door":
        ids = df["file_id"].astype(str)
        if ids.duplicated().any():
            errors.append(f"duplicate file_id(s): {sorted(ids[ids.duplicated()])[:3]}")
        if not ids.str.contains(r"\.[A-Za-z0-9]+$").all():
            errors.append("file_id must include the file extension, e.g. 'test03.csv'")
        if expected_ids is not None:
            exp = set(expected_ids)
            missing, extra = sorted(exp - set(ids)), sorted(set(ids) - exp)
            if missing:
                errors.append(f"missing {len(missing)} expected file(s), e.g. {missing[:3]}")
            if extra:
                errors.append(f"{len(extra)} unexpected file(s), e.g. {extra[:3]}")
    return errors


def build_predictions_zip(frames: Mapping[str, pd.DataFrame]) -> bytes:
    """Validate every frame, then write each CSV at the zip's TOP LEVEL.

    Raises ValueError listing every problem if anything is invalid; never
    writes a partial zip.
    """
    if not frames:
        raise ValueError("nothing to package")
    problems = []
    for key, df in frames.items():
        problems += [f"{key}: {e}" for e in validate_submission(key, df)]
    if problems:
        raise ValueError("refusing to build predictions.zip:\n  " + "\n  ".join(problems))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for key, df in frames.items():
            zf.writestr(SCHEMAS[key].filename, df.to_csv(index=False))
    return buf.getvalue()
