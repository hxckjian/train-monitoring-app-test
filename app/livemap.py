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

# Line -> (official colour, stations as they are named in the GeoJSON after cleaning).
# Names that the 2014 amendment file does not carry simply do not highlight.
LINES: dict[str, tuple[str, list[str]]] = {
    "NSL": ("#d42e12", [
        "JURONG EAST", "BUKIT BATOK", "BUKIT GOMBAK", "CHOA CHU KANG", "YEW TEE", "KRANJI",
        "MARSILING", "WOODLANDS", "ADMIRALTY", "SEMBAWANG", "YISHUN", "KHATIB", "YIO CHU KANG",
        "ANG MO KIO", "BISHAN", "BRADDELL", "TOA PAYOH", "NOVENA", "NEWTON", "ORCHARD",
        "SOMERSET", "DHOBY GHAUT", "CITY HALL", "RAFFLES PLACE", "MARINA BAY"]),
    "EWL": ("#009645", [
        "PASIR RIS", "TAMPINES", "SIMEI", "TANAH MERAH", "BEDOK", "KEMBANGAN", "EUNOS",
        "PAYA LEBAR", "ALJUNIED", "KALLANG", "LAVENDER", "BUGIS", "CITY HALL", "RAFFLES PLACE",
        "TANJONG PAGAR", "OUTRAM PARK", "TIONG BAHRU", "REDHILL", "QUEENSTOWN", "COMMONWEALTH",
        "BUONA VISTA", "DOVER", "CLEMENTI", "JURONG EAST", "CHINESE GARDEN", "LAKESIDE",
        "BOON LAY", "PIONEER", "JOO KOON", "GUL CIRCLE", "TUAS CRESCENT", "TUAS WEST ROAD",
        "TUAS LINK", "EXPO", "CHANGI AIRPORT"]),
    "NEL": ("#9900aa", [
        "HARBOURFRONT", "OUTRAM PARK", "CHINATOWN", "CLARKE QUAY", "DHOBY GHAUT", "LITTLE INDIA",
        "FARRER PARK", "BOON KENG", "POTONG PASIR", "WOODLEIGH", "SERANGOON", "KOVAN", "HOUGANG",
        "BUANGKOK", "SENGKANG", "PUNGGOL"]),
    "CCL": ("#fa9e0d", [
        "DHOBY GHAUT", "BRAS BASAH", "ESPLANADE", "PROMENADE", "NICOLL HIGHWAY", "STADIUM",
        "MOUNTBATTEN", "DAKOTA", "PAYA LEBAR", "MACPHERSON", "TAI SENG", "BARTLEY", "SERANGOON",
        "LORONG CHUAN", "BISHAN", "MARYMOUNT", "CALDECOTT", "BOTANIC GARDENS", "FARRER ROAD",
        "HOLLAND VILLAGE", "BUONA VISTA", "ONE NORTH", "KENT RIDGE", "HAW PAR VILLA",
        "PASIR PANJANG", "LABRADOR PARK", "TELOK BLANGAH", "HARBOURFRONT", "BAYFRONT",
        "MARINA BAY"]),
    "DTL": ("#005ec4", [
        "BUKIT PANJANG", "CASHEW", "HILLVIEW", "BEAUTY WORLD", "KING ALBERT PARK", "SIXTH AVENUE",
        "TAN KAH KEE", "BOTANIC GARDENS", "STEVENS", "NEWTON", "LITTLE INDIA", "ROCHOR", "BUGIS",
        "PROMENADE", "BAYFRONT", "DOWNTOWN", "TELOK AYER", "CHINATOWN", "FORT CANNING",
        "BENCOOLEN", "JALAN BESAR", "BENDEMEER", "GEYLANG BAHRU", "MATTAR", "MACPHERSON", "UBI",
        "KAKI BUKIT", "BEDOK NORTH", "BEDOK RESERVOIR", "TAMPINES WEST", "TAMPINES",
        "TAMPINES EAST", "UPPER CHANGI", "EXPO"]),
    "TEL": ("#9d5b25", [
        "WOODLANDS", "SPRINGLEAF", "LENTOR", "MAYFLOWER", "BRIGHT HILL", "UPPER THOMSON",
        "CALDECOTT", "STEVENS", "NAPIER", "ORCHARD", "GREAT WORLD", "HAVELOCK", "OUTRAM PARK",
        "SHENTON WAY", "MARINA BAY"]),
}
# Drawing order. A line with a branch is drawn as separate paths, otherwise the
# path would jump from the end of the main line back to the branch and cut
# straight across the island (the EWL Changi branch and the CCL Marina Bay spur).
BRANCHES: dict[str, list[list[str]]] = {
    "EWL": [[n for n in LINES["EWL"][1] if n not in ("EXPO", "CHANGI AIRPORT")],
            ["TANAH MERAH", "EXPO", "CHANGI AIRPORT"]],
    "CCL": [[n for n in LINES["CCL"][1] if n not in ("BAYFRONT", "MARINA BAY")],
            ["PROMENADE", "BAYFRONT", "MARINA BAY"]],
}
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
        return {"ok": True, "status": status, "segments": segs, "messages": msgs}
    except Exception as exc:  # network, JSON, timeout - all become one line of text
        return {"ok": False, "reason": f"could not reach DataMall ({type(exc).__name__})"}


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
        return {"ok": True, "posts": posts}
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
        return out
    except Exception as exc:
        return {"ok": False, "reason": f"could not reach data.gov.sg ({type(exc).__name__})",
                "stations": pd.DataFrame(), "forecast": pd.DataFrame()}


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
