"""Cross-subsystem insight for the summary dashboard: zones, line paths, ranked
events and trends. Pure functions over session results, no Streamlit calls, so
tests/test_insight.py can exercise them directly.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pydeck as pdk

from livemap import BRANCHES, LINES, STATE_RGB, TYPE_COLOR

# Singapore planning regions, approximated from station centroids. Good enough to
# say "north" or "east"; not a URA boundary file.
ZONES = {
    "Central":    {"rgb": [98, 84, 214],  "hint": "CBD, Orchard, Toa Payoh, Bishan"},
    "North":      {"rgb": [31, 143, 92],  "hint": "Woodlands, Yishun, Sembawang"},
    "North-East": {"rgb": [214, 138, 0],  "hint": "Serangoon, Hougang, Sengkang, Punggol"},
    "East":       {"rgb": [0, 149, 236],  "hint": "Bedok, Tampines, Pasir Ris, Changi"},
    "West":       {"rgb": [214, 40, 40],  "hint": "Jurong, Clementi, Bukit Batok, Tuas"},
}


def zone_of(lon: float, lat: float) -> str:
    if lon < 103.76:
        return "West"
    if lon > 103.93 or (lon > 103.90 and lat < 1.37):
        return "East"
    if lat > 1.405:
        return "North"
    if lon > 103.86 and lat > 1.33:
        return "North-East"
    if lon >= 103.76 and lon <= 103.79 and lat < 1.36:
        return "West"
    return "Central"


def with_zones(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["zone"] = [zone_of(a, b) for a, b in zip(out["lon"], out["lat"])]
    return out


def zone_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for z in ZONES:
        d = df[df["zone"] == z]
        lines = sorted({code for s in d["lines"] for code in s.split(", ") if code != "—"})
        rows.append({"zone": z, "stations": int(len(d)), "underground": int((d["level"] == "Underground").sum()),
                     "lines": ", ".join(lines) or "—", "hint": ZONES[z]["hint"]})
    return pd.DataFrame(rows)


def zones_for_line(df: pd.DataFrame, line: str | None) -> list[str]:
    if not line or line not in LINES:
        return []
    sel = df[df["key"].isin(LINES[line][1])]
    return [z for z in ZONES if z in set(sel["zone"])]


def line_paths(df: pd.DataFrame) -> list[dict]:
    """Ordered station centroids per line, for a PathLayer. Missing stations are skipped."""
    lookup = df.drop_duplicates("key").set_index("key")
    paths = []
    for code, (hexcol, names) in LINES.items():
        rgb = [int(hexcol[i:i + 2], 16) for i in (1, 3, 5)]
        for seq in BRANCHES.get(code, [names]):
            pts = [[float(lookup.loc[n, "lon"]), float(lookup.loc[n, "lat"])] for n in seq if n in lookup.index]
            if len(pts) >= 2:
                paths.append({"line": code, "color": rgb, "path": pts, "n": len(pts)})
    return paths


def weather_layers(weather: dict | None) -> list:
    """Rain gauges as blue discs sized by the last 5-minute rainfall, temperature as text."""
    if not weather or not weather.get("ok") or weather.get("stations") is None or weather["stations"].empty:
        return []
    w = weather["stations"].copy()
    layers = []
    if "rain_mm" in w:
        r = w.dropna(subset=["rain_mm"]).copy()
        r["radius"] = 250 + 400 * r["rain_mm"].clip(0, 10)
        r["color"] = [[0, 120, 220, 140] if v > 0 else [0, 120, 220, 40] for v in r["rain_mm"]]
        r["label"] = [f"{s} · rain {v:.1f} mm" for s, v in zip(r["station"], r["rain_mm"])]
        layers.append(pdk.Layer("ScatterplotLayer", data=r, get_position="[lon, lat]", get_fill_color="color",
                                get_radius="radius", pickable=True, stroked=False))
    if "temp_c" in w:
        t = w.dropna(subset=["temp_c"]).copy()
        t["text"] = [f"{v:.1f}°" for v in t["temp_c"]]
        layers.append(pdk.Layer("TextLayer", data=t, get_position="[lon, lat]", get_text="text",
                                get_size=13, get_color=[40, 60, 90], get_text_anchor='"start"',
                                get_alignment_baseline='"bottom"', get_pixel_offset=[6, -6]))
    return layers


def network_deck(df: pd.DataFrame, line: str | None, state: str, mode: str = "lines",
                 weather: dict | None = None) -> pdk.Deck:
    """Detailed map: line paths in official colours, stations coloured by zone or type,
    the chosen line lifted with a halo in the verdict colour."""
    d = df.copy()
    if mode == "zones":
        d["color"] = [ZONES[z]["rgb"] for z in d["zone"]]
    else:
        d["color"] = [TYPE_COLOR.get(t, TYPE_COLOR["MRT"]) for t in d["type"]]
    layers = []
    paths = line_paths(d)
    if paths:
        layers.append(pdk.Layer("PathLayer", data=paths, get_path="path", get_color="color",
                                width_min_pixels=3, get_width=60, opacity=0.9 if mode == "lines" else 0.35,
                                pickable=True))
    layers.append(pdk.Layer("ScatterplotLayer", data=d, get_position="[lon, lat]", get_fill_color="color",
                            get_radius=130, pickable=True, stroked=True, get_line_color=[255, 255, 255],
                            line_width_min_pixels=1, opacity=0.95))
    view = pdk.ViewState(latitude=1.352, longitude=103.82, zoom=10.7, pitch=0)
    if line in LINES:
        sel = d[d["key"].isin(LINES[line][1])].copy()
        if not sel.empty:
            sel["halo"] = [STATE_RGB.get(state, STATE_RGB["unknown"])] * len(sel)
            layers.insert(0, pdk.Layer("ScatterplotLayer", data=sel, get_position="[lon, lat]",
                                       get_fill_color="halo", get_radius=520, opacity=0.3, stroked=False))
    layers = weather_layers(weather) + layers
    tooltip = {"html": "<b>{name}{label}</b><br/>{zone} {type} {level}<br/>{lines}",
               "style": {"backgroundColor": "#10151c", "color": "#f7f8fa", "fontSize": "12px"}}
    return pdk.Deck(layers=layers, initial_view_state=view, tooltip=tooltip,
                    map_provider="carto", map_style="dark")


# ------------------------------------------------------------------ events

SHM_WATCH, SHM_ALERT = 0.5, 0.8


def events(results: dict) -> list[dict]:
    """Every noteworthy finding across subsystems, ranked by severity in [0, 1]."""
    ev: list[dict] = []
    door = results.get("door")
    if door is not None and not door["cycles"].empty:
        c = door["cycles"]
        ab = c[c["prediction"] == "Abnormal resistance"]
        for r in ab.itertuples():
            ev.append({"severity": 0.55 + 0.4 * float(r.p_abnormal), "state": "alert", "subsystem": "Door",
                       "title": f"Door cycle {r.cycle} ({r.operation}) against abnormal resistance",
                       "detail": f"{r.cur_mean_mid:.0f} mA sustained · P {r.p_abnormal:.0%} · {r.start_time}",
                       "page": "door"})
    shm = results.get("shm")
    if shm:
        for f in shm["files"]:
            d = float(f["damage"])
            if d >= SHM_WATCH:
                ev.append({"severity": min(1.0, 0.5 + 0.5 * d), "state": "alert" if d >= SHM_ALERT else "watch",
                           "subsystem": "Structural health",
                           "title": f"{f['file_id']} has used {d:.0%} of its fatigue life",
                           "detail": f"D = {d:.3f} · {f['n_cycles']:,} cycles · top 0.1% of cycles do {f['top_share']:.0%} of the damage",
                           "page": "shm"})
    rail = results.get("rail")
    if rail:
        for f in rail["files"]:
            if f["prediction"] != "Normal":
                p = f["proba"][f["prediction"]]
                ev.append({"severity": 0.6 + 0.4 * p, "state": "alert", "subsystem": "Rail corrugation",
                           "title": f"{f['file_id']}: {f['prediction']} rail corrugated",
                           "detail": f"P {p:.0%} · {f['speed']['speed_km_h']:.0f} km/h · side RMS I {f['side_i_rms']:.2f} / II {f['side_ii_rms']:.2f}",
                           "page": "rail"})
    acv = results.get("acv")
    if acv:
        for f in acv["files"]:
            top, second = f["ranking"][0], f["ranking"][1]
            pm = f.get("peer_mean", f["scores"])
            s1, s2 = pm.get(top), pm.get(second)
            gap = (s1 - s2) if (s1 is not None and s2 is not None) else 0.0
            ev.append({"severity": 0.45 + min(0.4, 4 * max(gap, 0.0)), "state": "alert" if gap >= 0.03 else "watch",
                       "subsystem": "Air conditioning",
                       "title": f"Car {top} most likely refrigerant leak in {f['file_id']}",
                       "detail": f"{s1:+.2f} °C over the other cars · margin {gap:.2f} °C to Car {second}",
                       "page": "acv"})
    return sorted(ev, key=lambda e: -e["severity"])


def top_events(ev: list[dict], n: int = 3) -> list[dict]:
    """The headline list: the worst event of each subsystem first, so three door
    cycles cannot crowd out a cracked structure; then the remaining by severity."""
    seen, first, rest = set(), [], []
    for e in ev:
        (rest if e["subsystem"] in seen else first).append(e)
        seen.add(e["subsystem"])
    return (first + rest)[:n]


# ------------------------------------------------------------------ trends

def trends(results: dict) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    door = results.get("door")
    if door is not None and not door["cycles"].empty:
        c = door["cycles"].copy()
        c["window_min"] = (c["start_s"] // 300 * 5).astype(int)
        g = c.groupby("window_min").agg(cycles=("cycle", "size"),
                                        abnormal=("prediction", lambda s: int((s == "Abnormal resistance").sum())),
                                        mean_current=("cur_mean_mid", "mean")).reset_index()
        g["abnormal_rate"] = g["abnormal"] / g["cycles"]
        out["door"] = g
    shm = results.get("shm")
    if shm:
        d = pd.DataFrame([{"file_id": f["file_id"], "damage": f["damage"], "n_cycles": f["n_cycles"],
                           "max_range": f["max_range"]} for f in shm["files"]])
        out["shm"] = d.sort_values("damage", ascending=False).reset_index(drop=True)
    rail = results.get("rail")
    if rail:
        rows = []
        for f in rail["files"]:
            num = "".join(ch for ch in f["file_id"] if ch.isdigit())
            rows.append({"file_id": f["file_id"], "order": int(num) if num else 0,
                         "p_corrugated": 1 - f["proba"]["Normal"], "prediction": f["prediction"],
                         "speed_km_h": f["speed"]["speed_km_h"]})
        out["rail"] = pd.DataFrame(rows).sort_values("order").reset_index(drop=True)
    acv = results.get("acv")
    if acv:
        f = acv["files"][0]
        ex = f["excess_timeline"].copy()
        top = f["ranking"][0]
        if top in ex.columns and ex["time"].notna().any():
            ex["day"] = ex["time"].dt.floor("D")
            daily = ex.groupby("day")[top].mean().reset_index().rename(columns={top: "excess"})
            daily["car"] = top
            out["acv"] = daily
    return out


def fleet_state(results: dict) -> dict[str, str]:
    """Worst state per subsystem key, 'unknown' when not run."""
    st = {k: "unknown" for k in ("door", "shm", "rail", "acv")}
    door = results.get("door")
    if door is not None and not door["cycles"].empty:
        st["door"] = "alert" if (door["cycles"]["prediction"] == "Abnormal resistance").any() else "ok"
    if results.get("shm"):
        worst = max(f["damage"] for f in results["shm"]["files"])
        st["shm"] = "alert" if worst >= SHM_ALERT else "watch" if worst >= SHM_WATCH else "ok"
    if results.get("rail"):
        st["rail"] = "alert" if (results["rail"]["predictions"]["prediction"] != "Normal").any() else "ok"
    if results.get("acv"):
        st["acv"] = "watch"
        for e in events({"acv": results["acv"]}):
            if e["state"] == "alert":
                st["acv"] = "alert"
    return st
