"""Live network map and live service feeds for the Fleet page.

Stations come from the hackathon's PS2 GeoJSON (Master Plan 2014 rail station
polygons). Live status comes from two optional sources, both read-only:

- LTA DataMall `TrainServiceAlerts` - needs the user's own AccountKey, which is
  kept in the browser session only and never written to disk.
- The public SGMRT Telegram channel preview (https://t.me/s/sgmrt) - no key.

Every fetch is time-limited, cached briefly and degrades to a clear "unavailable"
state instead of an exception, so the page always renders.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GEOJSON_CANDIDATES = [
    PROJECT_ROOT / "data" / "stations" / "AmendmenttoMP2014RailStation.geojson",
    PROJECT_ROOT / "repo" / "PS2" / "data" / "AmendmenttoMP2014RailStation.geojson",
    Path.home() / "Documents" / "Nebula" / "NebulaX-Hackathon-ProblemStatement" / "PS2"
    / "data" / "AmendmenttoMP2014RailStation.geojson",
]
LTA_ALERTS_URL = "https://datamall2.mytransport.sg/ltaodataservice/TrainServiceAlerts"
SGMRT_URL = "https://t.me/s/sgmrt"

from network import LINE_HEX, SEGMENTS, codes_to_names, stations_of  # noqa: E402

# Line -> (official colour, station names in running order). Derived from the
# station-code table in network.py so DataMall codes and GeoJSON names agree.
LINES: dict[str, tuple[str, list[str]]] = {code: (LINE_HEX[code], stations_of(code)) for code in SEGMENTS}
# Drawable paths per line (branches separate, so a path never jumps across the island).
BRANCHES: dict[str, list[list[str]]] = {code: [[name for _, name in seg] for seg in segs] for code, segs in SEGMENTS.items()}
TYPE_COLOR = {"MRT": [110, 120, 135], "LRT": [160, 168, 180], "CCL": [110, 120, 135]}
WEATHER_API = "https://api-open.data.gov.sg/v2/real-time/api"
STATE_RGB = {"ok": [31, 143, 92], "watch": [214, 138, 0], "alert": [214, 40, 40],
             "unknown": [110, 120, 135]}

_STRIP = re.compile(r"\s+(MRT STATION|RAIL STATION|LRT STATION|STATION|INTERCHANGE)\s*$", re.I)


def clean_name(raw) -> str | None:
    if raw is None or str(raw).strip().lower() in ("none", ""):
        return None
    s = _STRIP.sub("", str(raw).strip()).strip().upper()
    s = s.replace("KING ABERT PARK", "KING ALBERT PARK")
    return s or None


@st.cache_data(show_spinner=False)
def stations() -> pd.DataFrame:
    """One row per station polygon centroid: name, type, level, lon, lat, lines."""
    path = next((p for p in GEOJSON_CANDIDATES if p.exists()), None)
    if path is None:
        return pd.DataFrame(columns=["name", "type", "level", "lon", "lat", "lines"])
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for f in data["features"]:
        name = clean_name(f["properties"].get("NAME"))
        if not name:
            continue
        geom = f["geometry"]
        rings = geom["coordinates"] if geom["type"] == "Polygon" else [r for p in geom["coordinates"] for r in p]
        pts = np.array([pt for ring in rings for pt in ring], dtype=float)
        rows.append({"name": name.title(), "key": name,
                     "type": f["properties"].get("TYPE", "MRT"),
                     "level": str(f["properties"].get("GRND_LEVEL", "")).title(),
                     "lon": float(pts[:, 0].mean()), "lat": float(pts[:, 1].mean())})
    df = pd.DataFrame(rows).drop_duplicates(["key", "type"]).reset_index(drop=True)
    df["lines"] = [", ".join(code for code, (_, names) in LINES.items() if k in names) or "—"
                   for k in df["key"]]
    return df


def deck(df: pd.DataFrame, line: str | None, state: str, train_label: str) -> pdk.Deck:
    """All stations in neutral grey; the chosen line in its official colour, with the
    fleet verdict colour on a halo so the map reads at a glance."""
    base = df.copy()
    base["color"] = [TYPE_COLOR.get(t, TYPE_COLOR["MRT"]) for t in base["type"]]
    base["radius"] = 110
    layers = [pdk.Layer("ScatterplotLayer", data=base, get_position="[lon, lat]",
                        get_fill_color="color", get_radius="radius", pickable=True,
                        opacity=0.7, stroked=False)]
    view = pdk.ViewState(latitude=1.352, longitude=103.82, zoom=10.6, pitch=0)
    if line and line in LINES:
        hexcol, names = LINES[line]
        rgb = [int(hexcol[i:i + 2], 16) for i in (1, 3, 5)]
        sel = df[df["key"].isin(names)].copy()
        if not sel.empty:
            sel["halo"] = [STATE_RGB.get(state, STATE_RGB["unknown"])] * len(sel)
            sel["color"] = [rgb] * len(sel)
            sel["label"] = f"{line} · {train_label}"
            layers.append(pdk.Layer("ScatterplotLayer", data=sel, get_position="[lon, lat]",
                                    get_fill_color="halo", get_radius=420, opacity=0.35,
                                    stroked=False))
            layers.append(pdk.Layer("ScatterplotLayer", data=sel, get_position="[lon, lat]",
                                    get_fill_color="color", get_radius=190, pickable=True,
                                    stroked=True, get_line_color=[255, 255, 255],
                                    line_width_min_pixels=1))
            view = pdk.ViewState(latitude=float(sel["lat"].mean()),
                                 longitude=float(sel["lon"].mean()), zoom=11, pitch=0)
    tooltip = {"html": "<b>{name}</b><br/>{type} · {level}<br/>lines: {lines}",
               "style": {"backgroundColor": "#10151c", "color": "#f7f8fa", "fontSize": "12px"}}
    return pdk.Deck(layers=layers, initial_view_state=view, tooltip=tooltip,
                    map_provider="carto", map_style="dark")


@st.cache_data(ttl=60, show_spinner=False)
def fetch_train_alerts(account_key: str) -> dict:
    """LTA DataMall TrainServiceAlerts. Returns {'ok': bool, ...}; never raises."""
    if not account_key:
        return {"ok": False, "reason": "no AccountKey entered"}
    try:
        import requests
        r = requests.get(LTA_ALERTS_URL, headers={"AccountKey": account_key,
                                                  "accept": "application/json"}, timeout=8)
        if r.status_code != 200:
            return {"ok": False, "reason": f"DataMall answered HTTP {r.status_code}"}
        v = r.json().get("value", {}) or {}
        status = int(v.get("Status", 1) or 1)
        segs = v.get("AffectedSegments", []) or []
        msgs = [m.get("Content", "") for m in (v.get("Message", []) or []) if isinstance(m, dict)]
        for seg in segs:
            seg["StationNames"] = codes_to_names(str(seg.get("Stations", "")))
        return {"ok": True, "status": status, "segments": segs, "messages": msgs,
                "fetched_at": pd.Timestamp.now(tz="Asia/Singapore").strftime("%d %b %H:%M")}
    except Exception as exc:  # network, JSON, timeout - all become one line of text
        return {"ok": False, "reason": f"could not reach DataMall ({type(exc).__name__})"}


CROWD_URL = "https://datamall2.mytransport.sg/ltaodataservice/PCDRealTime"
CROWD_LINE_PARAM = {"NSL": ["NSL"], "EWL": ["EWL", "CGL"], "NEL": ["NEL"], "CCL": ["CCL", "CEL"], "DTL": ["DTL"], "TEL": ["TEL"]}
CROWD_RGB = {"l": [22, 169, 122], "m": [184, 136, 15], "h": [224, 67, 79]}
CROWD_WORD = {"l": "low", "m": "moderate", "h": "high"}


@st.cache_data(ttl=600, show_spinner=False)
def fetch_crowd(account_key: str, line: str) -> dict:
    """Real-time platform crowd density per station (DataMall PCDRealTime, 10-minute
    refresh). Returns {'ok', 'rows': DataFrame(code, name, level)}; never raises."""
    if not account_key:
        return {"ok": False, "reason": "no AccountKey entered", "rows": pd.DataFrame()}
    try:
        import requests
        rows = []
        for param in CROWD_LINE_PARAM.get(line, [line]):
            r = requests.get(CROWD_URL, params={"TrainLine": param},
                             headers={"AccountKey": account_key, "accept": "application/json"}, timeout=8)
            if r.status_code != 200:
                return {"ok": False, "reason": f"DataMall answered HTTP {r.status_code}", "rows": pd.DataFrame()}
            for v in r.json().get("value", []) or []:
                code = str(v.get("Station", "")).strip()
                rows.append({"code": code, "name": codes_to_names([code])[0] if codes_to_names([code]) else code,
                             "level": str(v.get("CrowdLevel", "")).lower()[:1],
                             "start": v.get("StartTime"), "end": v.get("EndTime")})
        return {"ok": True, "rows": pd.DataFrame(rows),
                "fetched_at": pd.Timestamp.now(tz="Asia/Singapore").strftime("%d %b %H:%M")}
    except Exception as exc:
        return {"ok": False, "reason": f"could not reach DataMall ({type(exc).__name__})", "rows": pd.DataFrame()}


_MSG = re.compile(r'tgme_widget_message_text[^>]*>(.*?)</div>', re.S)
_TIME = re.compile(r'<time datetime="([^"]+)"')


@st.cache_data(ttl=120, show_spinner=False)
def fetch_sgmrt(limit: int = 8) -> dict:
    """Latest posts from the public SGMRT Telegram preview page; no key needed."""
    try:
        import requests
        r = requests.get(SGMRT_URL, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return {"ok": False, "reason": f"t.me answered HTTP {r.status_code}", "posts": []}
        blocks = r.text.split('class="tgme_widget_message_wrap')
        posts = []
        for b in blocks[1:]:
            m, t = _MSG.search(b), _TIME.search(b)
            if not m:
                continue
            text = html.unescape(re.sub(r"<br\s*/?>", "\n", m.group(1)))
            text = re.sub(r"<[^>]+>", "", text).strip()
            when = pd.to_datetime(t.group(1), utc=True, errors="coerce") if t else pd.NaT
            if text:
                posts.append({"time": when, "text": text})
        posts = posts[-limit:][::-1]
        return {"ok": True, "posts": posts, "fetched_at": pd.Timestamp.now(tz="Asia/Singapore").strftime("%d %b %H:%M")}
    except Exception as exc:
        return {"ok": False, "reason": f"could not reach t.me ({type(exc).__name__})", "posts": []}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_weather() -> dict:
    """Live NEA readings from data.gov.sg (no key): air temperature, rainfall and
    the 2-hour area forecast. Returns {'ok', 'stations': DataFrame, 'forecast': DataFrame}."""
    try:
        import requests
        out = {"ok": True, "reason": ""}
        rows = {}
        for kind, key in (("air-temperature", "temp_c"), ("rainfall", "rain_mm")):
            r = requests.get(f"{WEATHER_API}/{kind}", timeout=8)
            if r.status_code != 200:
                return {"ok": False, "reason": f"data.gov.sg answered HTTP {r.status_code}"}
            d = r.json().get("data", {})
            meta = {s["id"]: s for s in d.get("stations", [])}
            readings = (d.get("readings") or [{}])[0]
            out[f"{kind}_time"] = readings.get("timestamp")
            for item in readings.get("data", []):
                s = meta.get(item["stationId"])
                if not s:
                    continue
                row = rows.setdefault(s["id"], {"station": s.get("name", s["id"]),
                                                "lat": s["location"]["latitude"], "lon": s["location"]["longitude"]})
                row[key] = float(item["value"])
        stations = pd.DataFrame(list(rows.values()))
        r = requests.get(f"{WEATHER_API}/two-hr-forecast", timeout=8)
        fc = pd.DataFrame()
        if r.status_code == 200:
            d = r.json().get("data", {})
            areas = {a["name"]: a["label_location"] for a in d.get("area_metadata", [])}
            items = d.get("items") or [{}]
            fc = pd.DataFrame([{"area": f["area"], "forecast": f["forecast"],
                                "lat": areas.get(f["area"], {}).get("latitude"),
                                "lon": areas.get(f["area"], {}).get("longitude")}
                               for f in items[0].get("forecasts", [])])
            out["forecast_valid"] = items[0].get("valid_period", {})
        out["stations"], out["forecast"] = stations, fc
        out["fetched_at"] = pd.Timestamp.now(tz="Asia/Singapore").strftime("%d %b %H:%M")
        t = out.get("air-temperature_time")
        out["reading_time"] = pd.Timestamp(t).tz_convert("Asia/Singapore").strftime("%d %b %H:%M") if t else "—"
        return out
    except Exception as exc:
        return {"ok": False, "reason": f"could not reach data.gov.sg ({type(exc).__name__})",
                "stations": pd.DataFrame(), "forecast": pd.DataFrame()}


def weather_emoji(forecast: str | None, rain_mm: float | None = None) -> str:
    """NEA forecast wording -> one glyph; rain in the last 5 minutes overrides."""
    f = (forecast or "").lower()
    if rain_mm and rain_mm > 0:
        return "🌧️"
    if "thunder" in f:
        return "⛈️"
    if "shower" in f or "rain" in f:
        return "🌦️" if "light" in f or "passing" in f else "🌧️"
    if "haz" in f or "mist" in f or "fog" in f:
        return "🌫️"
    if "windy" in f:
        return "💨"
    if "partly" in f:
        return "🌙" if "night" in f else "⛅"
    if "cloudy" in f:
        return "☁️"
    if "fair" in f or "sunny" in f:
        return "🌙" if "night" in f else "☀️"
    return "🌤️"


def weather_near(weather: dict, lat: float, lon: float) -> dict:
    """Nearest temperature / rain station and forecast area to a point."""
    out = {}
    st_ = weather.get("stations")
    if st_ is not None and not st_.empty:
        d2 = (st_["lat"] - lat) ** 2 + (st_["lon"] - lon) ** 2
        near = st_.loc[d2.idxmin()]
        out.update({"station": near["station"], "temp_c": near.get("temp_c"), "rain_mm": near.get("rain_mm")})
        if "temp_c" in st_ and st_["temp_c"].notna().any():
            t = st_.dropna(subset=["temp_c"])
            out["temp_c"] = float(t.loc[((t["lat"] - lat) ** 2 + (t["lon"] - lon) ** 2).idxmin(), "temp_c"])
        if "rain_mm" in st_ and st_["rain_mm"].notna().any():
            rr = st_.dropna(subset=["rain_mm"])
            out["rain_mm"] = float(rr.loc[((rr["lat"] - lat) ** 2 + (rr["lon"] - lon) ** 2).idxmin(), "rain_mm"])
    fc = weather.get("forecast")
    if fc is not None and not fc.empty and fc["lat"].notna().any():
        f = fc.dropna(subset=["lat"])
        near = f.loc[((f["lat"] - lat) ** 2 + (f["lon"] - lon) ** 2).idxmin()]
        out.update({"area": near["area"], "forecast": near["forecast"]})
    return out


def line_mentioned(text: str, line: str | None) -> bool:
    """Does a free-text alert plausibly concern the chosen line?"""
    if not line:
        return False
    words = {"NSL": ("NSL", "NORTH-SOUTH", "NORTH SOUTH"), "EWL": ("EWL", "EAST-WEST", "EAST WEST"),
             "NEL": ("NEL", "NORTH-EAST", "NORTH EAST"), "CCL": ("CCL", "CIRCLE LINE"),
             "DTL": ("DTL", "DOWNTOWN"), "TEL": ("TEL", "THOMSON")}
    up = text.upper()
    return any(w in up for w in words.get(line, (line,)))
