"""Header-driven ACV parsing and peer-relative cooling features."""

import re
from zipfile import ZipFile
from openpyxl import load_workbook
import numpy as np
import pandas as pd

ALIASES = {
    "indoor": [
        "Indoor Average Temperature",
        "Passenger Cabin Temperature Detected Value",
    ],
    "target": ["ACV Control Temperature (Cooling)", "Target Temperature Value"],
    "mode": ["ACV Running Mode"],
    "valid": ["ACV Information Valid"],
}
PATTERN = re.compile(r"^Car (\d+) - (.+)$")


def load(source):
    source.seek(0)
    try:
        with ZipFile(source) as archive:
            if sum(x.file_size for x in archive.infolist()) > 400 * 1024 * 1024:
                raise ValueError(
                    "Expanded workbook exceeds 400 MiB. Export a smaller complete case."
                )
        source.seek(0)
        book = load_workbook(source, read_only=True, data_only=True)
        try:
            if len(book.sheetnames) != 1:
                raise ValueError("Use a workbook with one telemetry worksheet.")
            sheet = book.worksheets[0]
            if (sheet.max_row or 0) > 100001 or (sheet.max_column or 0) > 1024:
                raise ValueError(
                    "Workbook exceeds 100,000 readings or 1,024 columns. Use a smaller complete case."
                )
            # Do not trust worksheet dimensions supplied by an uploaded workbook.
            sheet.reset_dimensions()
            iterator = sheet.iter_rows(values_only=True)
            headers = list(next(iterator))
            if len(headers) > 1024:
                raise ValueError("Workbook exceeds 1,024 columns.")
            if len(set(headers)) != len(headers):
                raise ValueError(
                    "Workbook headers must be unique. Re-export the original telemetry."
                )
            indices = []
            for i, header in enumerate(headers):
                match = PATTERN.fullmatch(str(header))
                if header == "Time" or (
                    match and any(match[2] in names for names in ALIASES.values())
                ):
                    indices.append(i)
            # Retain only useful cells while streaming; never materialize all 483 columns.
            records = []
            for count, row in enumerate(iterator, start=1):
                if count > 100000 or len(row) > 1024:
                    raise ValueError("Workbook exceeds 100,000 readings or 1,024 columns.")
                records.append([row[i] if i < len(row) else None for i in indices])
            frame = pd.DataFrame(records, columns=[headers[i] for i in indices])
        finally:
            book.close()
        cars = sorted({m[1] for h in headers if (m := PATTERN.fullmatch(str(h)))})
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            "Cannot read this Excel workbook. Upload the original .xlsx telemetry export."
        ) from exc
    if len(cars) != 8 or "Time" not in frame or len(frame) < 20:
        raise ValueError(
            "ACV requires a Time column, eight car identifiers in Car NN - parameter headers, and at least 20 readings."
        )
    times = pd.to_datetime(frame.Time, errors="coerce")
    if (
        times.isna().any()
        or times.duplicated().any()
        or not times.is_monotonic_increasing
    ):
        raise ValueError("ACV Time values must be valid, increasing and unique.")
    return frame, cars


def extract_features(frame, cars):
    indoor, target = {}, {}
    for car in cars:
        cols = {}
        for kind, aliases in ALIASES.items():
            cols[kind] = next(
                (f"Car {car} - {s}" for s in aliases if f"Car {car} - {s}" in frame),
                None,
            )
        if any(cols[k] is None for k in ["indoor", "target", "mode"]):
            raise ValueError(
                f"Car {car} is missing cabin temperature, cooling target or running-mode telemetry."
            )
        t = pd.to_numeric(frame[cols["indoor"]], errors="coerce")
        goal = pd.to_numeric(frame[cols["target"]], errors="coerce")
        mask = frame[cols["mode"]].astype(str).str.contains("cool", case=False)
        if cols["valid"]:
            mask &= frame[cols["valid"]].astype(str).str.lower().eq("valid")
        mask &= t.between(-20, 70) & goal.between(5, 45)
        if mask.sum() < 20:
            mask[:] = False
        indoor[car] = t.where(mask)
        target[car] = goal.where(mask)
    temperatures = pd.DataFrame(indoor)
    excess = temperatures - pd.DataFrame(target)
    if (temperatures.notna().sum() >= 20).sum() < 2:
        raise ValueError(
            "At least two cars need 20 valid cooling readings for a meaningful comparison."
        )
    rows = []
    unobserved = []
    for car in cars:
        peers = temperatures.drop(columns=car)
        delta = (temperatures[car] - peers.median(axis=1)).dropna()
        residual = (excess[car] - excess.drop(columns=car).median(axis=1)).dropna()
        if len(delta) < 20 or len(residual) < 20:
            unobserved.append(car)
            rows.append(
                dict.fromkeys(
                    [
                        "peer_mean",
                        "peer_q90",
                        "peer_hot_fraction",
                        "excess_mean",
                        "excess_q90",
                        "excess_peer_mean",
                        "excess_peer_q90",
                    ],
                    0.0,
                )
            )
            continue
        e = excess[car].dropna()
        rows.append(
            {
                "peer_mean": delta.mean(),
                "peer_q90": delta.quantile(0.9),
                "peer_hot_fraction": (delta > 2).mean(),
                "excess_mean": e.mean(),
                "excess_q90": e.quantile(0.9),
                "excess_peer_mean": residual.mean(),
                "excess_peer_q90": residual.quantile(0.9),
            }
        )
    if len(cars) - len(unobserved) < 2:
        raise ValueError(
            "At least two cars need simultaneous valid cooling readings. Include a longer complete case."
        )
    result = pd.DataFrame(rows, index=cars).astype(float)
    result.attrs["unobserved"] = unobserved
    return result


def rank_scores(x, model):
    scores = (
        x.peer_mean.to_numpy().copy() if model is None else model.predict_proba(x)[:, 1]
    )
    scores[x.index.isin(x.attrs.get("unobserved", []))] = -np.inf
    return scores
