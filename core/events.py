"""The fleet event log: every verdict the models produce, with when it was
recorded and which train and place it belongs to, kept across sessions.

The competition files carry no fleet metadata, so context is attached when a
file is analysed: the train set (from a per-line roster) and the station it was
recorded at, both chosen by the user, or left unknown. Door and ACV files carry
their own timestamps, which become the event time; Rail and SHM files do not, so
the analysis time is used. The Fleet view filters this log by time range, line,
subsystem and state, and puts the events on the map.

Storage is a JSON-lines file under data/. On a stateless host (Cloud Run) it
lives for the life of the instance; swap `EVENTS_PATH` for a bucket or Firestore
to make it durable.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

EVENTS_PATH = Path(os.environ.get("NEBULA_EVENTS_PATH") or (Path(__file__).resolve().parents[1] / "data" / "events.jsonl"))
SGT = timezone(timedelta(hours=8))
LINE_CODES = ("NSL", "EWL", "NEL", "CCL", "DTL", "TEL")
SUBSYSTEM_NAME = {"door": "Door", "shm": "Structural health", "rail": "Rail corrugation", "acv": "Air conditioning"}


def txt(v, default: str = "—") -> str:
    """A display string for a value that may be None or NaN."""
    try:
        if v is None or (isinstance(v, float) and v != v):
            return default
    except Exception:
        return default
    return str(v) if str(v) not in ("", "nan", "None") else default


def fmt_time(t, pattern: str = "%d %b %H:%M") -> str:
    """Never let a missing timestamp break a page."""
    try:
        ts = pd.Timestamp(t)
        return "—" if pd.isna(ts) else ts.strftime(pattern)
    except (ValueError, TypeError):
        return "—"


def roster(line: str, n: int = 8) -> list[str]:
    """Train sets on a line. A roster is operator data; this one is a placeholder
    naming scheme (line code + set number) until a real fleet list is loaded."""
    return [f"{line}-{i:02d}" for i in range(1, n + 1)]


def now() -> datetime:
    return datetime.now(SGT)


def _door_ts(s: str) -> datetime | None:
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})-(\d{1,2})-(\d{1,2})-(\d{1,2})-(\d{1,3})$", str(s))
    if not m:
        return None
    y, mo, d, h, mi, se, ms = (int(x) for x in m.groups())
    return datetime(y, mo, d, h, mi, se, ms * 1000, tzinfo=SGT)


def events_from_result(key: str, res: dict, context: dict | None = None,
                       recorded_at: datetime | None = None) -> list[dict]:
    """Turn one subsystem result (analyze() output) into event rows.
    Includes normal outcomes, so the log shows what was checked, not only faults."""
    ctx = {"train": None, "line": None, "station": None, "source": "upload", **(context or {})}
    at = recorded_at or now()
    ctx.setdefault("dataset", None)
    rows: list[dict] = []

    def row(state, title, detail, severity, when, file_id, extra=None):
        rows.append({"time": when.isoformat(), "analysed_at": now().isoformat(), "subsystem": key,
                     "subsystem_name": SUBSYSTEM_NAME[key], "state": state, "severity": float(severity),
                     "title": title, "detail": detail, "file_id": file_id, **ctx, **(extra or {})})

    if key == "door" and res is not None and not res["cycles"].empty:
        c = res["cycles"]
        for r in c.itertuples():
            when = _door_ts(r.start_time) or at
            ab = r.prediction == "Abnormal resistance"
            row("alert" if ab else "ok",
                f"Door cycle {r.cycle} ({r.operation}) {'abnormal resistance' if ab else 'normal'}",
                f"{r.cur_mean_mid:.0f} mA sustained · P(abnormal) {r.p_abnormal:.0%}",
                0.55 + 0.4 * float(r.p_abnormal) if ab else 0.1 * float(r.p_abnormal),
                when, str(r.file), {"cycle": int(r.cycle)})
    elif key == "shm" and res:
        for f in res["files"]:
            d = float(f["damage"])
            state = "alert" if d >= 0.8 else "watch" if d >= 0.5 else "ok"
            row(state, f"{f['file_id']}: fatigue damage {d:.2f}",
                f"{d:.0%} of fatigue life · {(1 - d) / d:.1f} segments of this length left at this rate",
                min(1.0, 0.5 + 0.5 * d) if state != "ok" else 0.3 * d, at, f["file_id"], {"damage": d})
    elif key == "rail" and res:
        for f in res["files"]:
            p = f["proba"][f["prediction"]]
            bad = f["prediction"] != "Normal"
            row("alert" if bad else "ok",
                f"{f['file_id']}: {f['prediction']}" + (" rail corrugated" if bad else " track"),
                f"P {p:.0%} · {f['speed']['speed_km_h']:.0f} km/h",
                0.6 + 0.4 * p if bad else 0.2 * (1 - p), at, f["file_id"], {"prediction": f["prediction"]})
    elif key == "acv" and res:
        for f in res["files"]:
            top, second = f["ranking"][0], f["ranking"][1]
            pm = f.get("peer_mean", f["scores"])
            s1, s2 = pm.get(top), pm.get(second)
            gap = (s1 - s2) if (s1 is not None and s2 is not None) else 0.0
            hot = f.get("hot_fraction", {}).get(top, 0.0)
            when = at
            tl = f.get("timeline")
            if tl is not None and "time" in tl and tl["time"].notna().any():
                last = pd.Timestamp(tl["time"].dropna().iloc[-1])
                when = (last.tz_localize(SGT) if last.tzinfo is None else last.tz_convert(SGT)).to_pydatetime()
            row("alert" if (gap >= 0.03 or hot >= 0.01) else "watch",
                f"Car {top} most likely refrigerant leak ({f['file_id']})",
                f"{s1:+.2f} °C over the other cars · hot {hot:.1%} of cooling time · runner-up Car {second}",
                0.45 + min(0.4, 4 * max(gap, 0.0)) + min(0.15, hot), when, f["file_id"], {"car": top})
    return rows


def append_unique(rows: list[dict]) -> tuple[int, int]:
    """Append only events whose identity (subsystem, file, title, train) is not in the
    log yet, so analysing the same file twice does not double its events.
    Returns (added, skipped)."""
    if not rows:
        return 0, 0
    existing = set(load()["id"]) if EVENTS_PATH.exists() else set()
    fresh, skipped = [], 0
    for r in rows:
        eid = event_id(r)
        if eid in existing:
            skipped += 1
            continue
        existing.add(eid)
        fresh.append({**r, "id": eid})
    return append(fresh), skipped


def append(rows: list[dict]) -> int:
    if not rows:
        return 0
    EVENTS_PATH.parent.mkdir(exist_ok=True)
    with open(EVENTS_PATH, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    return len(rows)


def load() -> pd.DataFrame:
    cols = ["time", "analysed_at", "subsystem", "subsystem_name", "state", "severity", "title", "detail",
            "file_id", "train", "line", "station", "source", "id", "dataset"]
    if not EVENTS_PATH.exists():
        return pd.DataFrame(columns=cols)
    rows = []
    with open(EVENTS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df:
            df[c] = None
    # ISO8601 explicitly: pandas otherwise infers the format from the first row and
    # coerces every row with a different precision or offset to NaT.
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce", format="ISO8601").dt.tz_convert(SGT)
    df["analysed_at"] = pd.to_datetime(df["analysed_at"], utc=True, errors="coerce", format="ISO8601").dt.tz_convert(SGT)
    df["time"] = df["time"].fillna(df["analysed_at"]).fillna(pd.Timestamp.now(tz=SGT))
    # missing context is None, never NaN, so page code can rely on `or`
    for c in ("train", "line", "station", "source", "file_id", "detail", "title"):
        df[c] = df[c].astype(object).where(df[c].notna(), None)
    if "id" not in df or df["id"].isna().any():
        df["id"] = [event_id(r) for _, r in df.iterrows()]
    if "dataset" not in df:
        df["dataset"] = None
    df["dataset"] = df["dataset"].astype(object).where(df["dataset"].notna(), None)
    df["dataset"] = [d or default_dataset(src, at) for d, src, at in zip(df["dataset"], df["source"], df["analysed_at"])]
    # one row per event identity: logs written before de-duplication may hold repeats
    df = df.sort_values("analysed_at").drop_duplicates("id", keep="last")
    return df.sort_values("time", ascending=False).reset_index(drop=True)


def default_dataset(source, analysed_at) -> str:
    """Name for rows logged before datasets existed."""
    if source == "demo":
        return "Demo fleet (seeded)"
    try:
        return f"Upload {pd.Timestamp(analysed_at).strftime('%d %b %H:%M')}"
    except Exception:
        return "Upload"


def datasets(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per dataset: name, source, events, faults, first/last time, analysed_at."""
    df = load() if df is None else df
    if df.empty:
        return pd.DataFrame(columns=["dataset", "source", "events", "faults", "first", "last", "analysed_at"])
    g = df.groupby("dataset").agg(source=("source", "first"), events=("id", "size"),
                                  faults=("state", lambda s: int((s == "alert").sum())),
                                  first=("time", "min"), last=("time", "max"),
                                  analysed_at=("analysed_at", "max")).reset_index()
    return g.sort_values("analysed_at", ascending=False).reset_index(drop=True)


def remove_dataset(name: str) -> int:
    """Delete every event of one dataset from the log. Returns rows removed."""
    df = load()
    keep = df[df["dataset"] != name]
    removed = len(df) - len(keep)
    if EVENTS_PATH.exists():
        EVENTS_PATH.unlink()
    if len(keep):
        rows = keep.copy()
        rows["time"] = rows["time"].map(lambda t: t.isoformat())
        rows["analysed_at"] = rows["analysed_at"].map(lambda t: t.isoformat())
        append(rows.to_dict("records"))
    return removed


def clear(source: str | None = None) -> None:
    if not EVENTS_PATH.exists():
        return
    if source is None:
        EVENTS_PATH.unlink()
        return
    df = load()
    keep = df[df["source"] != source]
    EVENTS_PATH.unlink()
    if len(keep):
        rows = keep.copy()
        rows["time"] = rows["time"].map(lambda t: t.isoformat())
        rows["analysed_at"] = rows["analysed_at"].map(lambda t: t.isoformat())
        append(rows.to_dict("records"))


def seed_demo(results: dict, stations_by_line: dict[str, list[str]], days: int = 7) -> int:
    """Turn the cached competition-data run into a demo fleet: each subsystem result is
    assigned to a train set and a station on a line, and the events are spread over the
    past `days` days so the time filters have something to show. Clearly tagged
    source='demo' so it can be wiped, and never mixed up with an upload."""
    clear("demo")
    rows: list[dict] = []
    lines = list(stations_by_line)
    order = 0
    for key, res in results.items():
        if not res:
            continue
        ev = events_from_result(key, res, {"source": "demo", "dataset": "Demo fleet (seeded)"})
        for e in ev:
            line = lines[order % len(lines)]
            sts = stations_by_line[line]
            e["line"], e["train"] = line, roster(line)[order % 8]
            e["station"] = sts[(order * 7) % len(sts)] if sts else None
            # replay: keep the file's own time-of-day, place it within the past `days`
            t = pd.Timestamp(e["time"])
            shifted = now() - timedelta(days=(order * 3) % days, hours=(order * 5) % 23)
            e["time"] = shifted.replace(hour=t.hour, minute=t.minute, second=t.second).isoformat()
            e["replayed_from"] = t.isoformat()
            order += 1
        rows += ev
    return append(rows)


# ------------------------------------------------------------------ alarm workflow

ACTIONS_PATH = EVENTS_PATH.with_name(EVENTS_PATH.stem + "_actions.jsonl")
STATUS = ("open", "acknowledged", "closed")


def event_id(row) -> str:
    """Stable id from what the event is, so an action survives a re-seed of the same run."""
    import hashlib
    key = f"{row['subsystem']}|{row['file_id']}|{row['title']}|{row.get('train')}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def set_status(eid: str, status: str, note: str = "", by: str = "operator") -> None:
    if status not in STATUS:
        raise ValueError(status)
    ACTIONS_PATH.parent.mkdir(exist_ok=True)
    with open(ACTIONS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": eid, "status": status, "note": note, "by": by, "at": now().isoformat()}) + "\n")


def statuses() -> dict[str, dict]:
    """Latest action per event id."""
    out: dict[str, dict] = {}
    if not ACTIONS_PATH.exists():
        return out
    with open(ACTIONS_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                a = json.loads(line)
                out[a["id"]] = a
            except (json.JSONDecodeError, KeyError):
                continue
    return out


def with_status(df: pd.DataFrame) -> pd.DataFrame:
    """Add id, status, note, status_at columns; faults default to 'open', the rest to '—'."""
    if df.empty:
        return df.assign(id=[], status=[], note=[], status_at=[])
    acts = statuses()
    out = df.copy()
    if "id" not in out or out["id"].isna().any():
        out["id"] = [event_id(r) for _, r in out.iterrows()]
    out["status"] = [acts.get(i, {}).get("status", "open" if s in ("alert", "watch") else "—")
                     for i, s in zip(out["id"], out["state"])]
    out["note"] = [acts.get(i, {}).get("note", "") for i in out["id"]]
    out["status_at"] = [acts.get(i, {}).get("at") for i in out["id"]]
    return out
