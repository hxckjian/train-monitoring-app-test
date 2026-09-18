"""The decision layer: turn verdicts into actions an operator can take in a
second, and into plain-language notes a new engineer can read.

Each rule is written down here with its threshold, so a reviewer can see why
an action was raised. Thresholds come from the Info Kits and the model cards:
Miner's rule fails at D = 1; the console's watch band is 0.5 and alert 0.8;
door abnormal resistance is the model's own label; rail Side I / II is the
model's label; ACV is a ranking, so its action is graded by how far the top
car stands from the runner-up.

Nothing here is a model. It is the playbook, made explicit.
"""
from __future__ import annotations

import pandas as pd

URGENCY_ORDER = {"Now": 0, "Today": 1, "This week": 2, "Routine": 3}
URGENCY_STATE = {"Now": "alert", "Today": "alert", "This week": "watch", "Routine": "ok"}

GLOSSARY = {
    "door": {
        "what": "Each time a saloon door opens or closes, the controller records motor current, voltage, "
                "back-EMF and door position. A door that meets resistance (a jammed seal, debris in the "
                "slide rail, a bent leaf) draws more current for the same travel.",
        "read": "One row per cycle. 'Abnormal resistance' means the motor worked harder than a normal cycle "
                "of the same kind. P(abnormal) is the model's confidence; sustained current in mA is the "
                "physical reason.",
        "act": "One abnormal cycle: inspect at end of service. Several in a short stretch: the door is "
               "likely to jam; isolate it at the next terminal.",
    },
    "shm": {
        "what": "Strain gauges on the carbody or bogie frame record stress over time. Every stress cycle "
                "uses a little fatigue life; big cycles use far more. Damage D adds up and the structure is "
                "at the end of its fatigue life when D reaches 1.",
        "read": "D is the share of fatigue life used in this recording's time window. 0.10 means 10%. "
                "'Segments left' is how many more windows like this one until D = 1 if loading stays the same.",
        "act": "Below 0.5: routine. 0.5 to 0.8: schedule a structural inspection this week. 0.8 and above: "
               "restrict the vehicle and inspect before it re-enters service.",
    },
    "rail": {
        "what": "Corrugation is a ripple worn into the rail head. Wheels rolling over it shake every axle "
                "box on that side of the train at the same pitch. Sensors on all 64 axle boxes record one "
                "second at a time.",
        "read": "Normal, Side I or Side II per recording. Side I is the rail under positions 1, 3, 5, 7; Side "
                "II under 2, 4, 6, 8. Speed is measured from the wheel pulse, so the pitch can be read in cm.",
        "act": "A corrugated recording goes to the track team for grinding. Several on the same section, or "
               "at rising energy, move it up the grinding programme; passengers hear it as a roar.",
    },
    "acv": {
        "what": "Each of the 8 cars has its own air-conditioning unit. A unit that has lost refrigerant cannot "
                "pull its cabin down to the setpoint, so it runs warmer than the other cars on the same "
                "train, in the same weather, with the same crowd.",
        "read": "Cars are ranked from most to least likely to be leaking. The score is how much hotter the "
                "car runs than the others, and how often it runs more than 2 °C hotter. A ranking, not a "
                "probability: the top car is where to look first.",
        "act": "Check refrigerant charge and the condenser on the top car before the afternoon peak. A "
               "narrow margin means check the top two.",
    },
}


def _door_actions(res) -> list[dict]:
    out = []
    if res is None or res["cycles"].empty:
        return out
    c = res["cycles"]
    ab = c[c["prediction"] == "Abnormal resistance"]
    if ab.empty:
        return [{"urgency": "Routine", "subsystem": "Door", "action": "No door action needed",
                 "why": f"All {len(c)} cycles drew normal motor current.", "owner": "Rolling stock",
                 "page": "door"}]
    # cluster: three or more abnormal cycles within any 10-minute window
    t = ab["start_s"].sort_values().to_numpy()
    clustered = any((t[i + 2] - t[i]) <= 600 for i in range(len(t) - 2)) if len(t) >= 3 else False
    share = len(ab) / len(c)
    if clustered or share >= 0.3:
        out.append({"urgency": "Now", "subsystem": "Door",
                    "action": "Isolate this door at the next terminal and inspect the slide rail and seals",
                    "why": f"{len(ab)} of {len(c)} cycles ({share:.0%}) met abnormal resistance"
                           + (", several within ten minutes" if clustered else "")
                           + f"; sustained current {ab['cur_mean_mid'].mean():.0f} mA against "
                             f"{c[c['prediction'] == 'Normal']['cur_mean_mid'].mean():.0f} mA normal. A door that keeps "
                             "meeting resistance is the one that jams.",
                    "owner": "Rolling stock", "page": "door"})
    else:
        out.append({"urgency": "Today", "subsystem": "Door",
                    "action": "Inspect the door at end of service: slide rail, rubber seal, leaf alignment",
                    "why": f"{len(ab)} of {len(c)} cycles met abnormal resistance (highest confidence "
                           f"{ab['p_abnormal'].max():.0%}).",
                    "owner": "Rolling stock", "page": "door"})
    return out


def _shm_actions(res) -> list[dict]:
    if not res:
        return []
    files = pd.DataFrame([{"file_id": f["file_id"], "damage": f["damage"]} for f in res["files"]])
    worst = files.loc[files["damage"].idxmax()]
    hi = files[files["damage"] >= 0.8]
    mid = files[(files["damage"] >= 0.5) & (files["damage"] < 0.8)]
    out = []
    if len(hi):
        left = (1 - worst["damage"]) / worst["damage"]
        out.append({"urgency": "Now", "subsystem": "Structural health",
                    "action": f"Restrict the vehicle and carry out a structural inspection at "
                              f"{', '.join(hi['file_id'].head(3))}{' and more' if len(hi) > 3 else ''} before it re-enters service",
                    "why": f"Fatigue damage {worst['damage']:.2f} at {worst['file_id']}: {worst['damage']:.0%} of fatigue life "
                           f"used, about {left:.1f} more windows like this one before D = 1.",
                    "owner": "Depot engineering", "page": "shm"})
    if len(mid):
        out.append({"urgency": "This week", "subsystem": "Structural health",
                    "action": f"Schedule a structural inspection for {len(mid)} measurement point(s) past the watch band",
                    "why": f"Damage between 0.5 and 0.8 at {', '.join(mid['file_id'].head(4))}"
                           f"{' and more' if len(mid) > 4 else ''}.",
                    "owner": "Depot engineering", "page": "shm"})
    if not out:
        out.append({"urgency": "Routine", "subsystem": "Structural health", "action": "No structural action needed",
                    "why": f"Highest damage {worst['damage']:.2f} at {worst['file_id']}, below the watch band of 0.5.",
                    "owner": "Depot engineering", "page": "shm"})
    return out


def _rail_actions(res) -> list[dict]:
    if not res:
        return []
    files = res["files"]
    bad = [f for f in files if f["prediction"] != "Normal"]
    if not bad:
        return [{"urgency": "Routine", "subsystem": "Rail corrugation", "action": "No track action needed",
                 "why": f"All {len(files)} recordings read as normal track.", "owner": "Track", "page": "rail"}]
    sides = {"Side I": [f for f in bad if f["prediction"] == "Side I"],
             "Side II": [f for f in bad if f["prediction"] == "Side II"]}
    out = []
    for side, lst in sides.items():
        if not lst:
            continue
        strong = [f for f in lst if f["proba"][side] >= 0.7]
        speed = sum(f["speed"]["speed_km_h"] for f in lst) / len(lst)
        urgency = "This week" if len(lst) >= 3 or strong else "Routine"
        out.append({"urgency": urgency, "subsystem": "Rail corrugation",
                    "action": f"Send the {side} rail to the grinding programme"
                              + (": locate the section from the train's position log" if len(lst) >= 3 else " watch list"),
                    "why": f"{len(lst)} recording(s) show {side} corrugation ({len(strong)} with confidence ≥ 70%), "
                           f"at about {speed:.0f} km/h: " + ", ".join(f["file_id"] for f in lst[:4])
                           + (" and more" if len(lst) > 4 else "") + ".",
                    "owner": "Track", "page": "rail"})
    return out


def _acv_actions(res) -> list[dict]:
    if not res:
        return []
    out = []
    for f in res["files"]:
        top, second = f["ranking"][0], f["ranking"][1]
        pm = f.get("peer_mean", f["scores"])
        hot = f.get("hot_fraction", {})
        gap = (pm.get(top) or 0) - (pm.get(second) or 0)
        h = hot.get(top, 0.0) or 0.0
        if h >= 0.01 or gap >= 0.03:
            out.append({"urgency": "Today", "subsystem": "Air conditioning",
                        "action": f"Check refrigerant charge and the condenser on Car {top} before the afternoon peak",
                        "why": f"Car {top} ran {pm.get(top, 0):+.2f} °C hotter than the other cars during cooling"
                               + (f" and more than 2 °C hotter for {h:.1%} of the time" if h else "")
                               + f". Runner-up Car {second} at {pm.get(second, 0):+.2f} °C.",
                        "owner": "Rolling stock", "page": "acv"})
        else:
            out.append({"urgency": "This week", "subsystem": "Air conditioning",
                        "action": f"Check Car {top}, then Car {second}: the margin between them is narrow",
                        "why": f"Car {top} ranks first at {pm.get(top, 0):+.2f} °C over the others but only "
                               f"{gap:.2f} °C ahead of Car {second}; no sustained hot episodes.",
                        "owner": "Rolling stock", "page": "acv"})
    return out


def recommend(results: dict) -> list[dict]:
    """Prioritised actions from this session's results. Empty when nothing was run."""
    acts = (_door_actions(results.get("door")) + _shm_actions(results.get("shm"))
            + _rail_actions(results.get("rail")) + _acv_actions(results.get("acv")))
    for a in acts:
        a["state"] = URGENCY_STATE[a["urgency"]]
    return sorted(acts, key=lambda a: URGENCY_ORDER[a["urgency"]])


def insights(results: dict) -> list[str]:
    """Short, data-driven observations a new engineer would otherwise have to dig for.
    Each one is computed from the results at hand; none is generic."""
    out = []
    door = results.get("door")
    if door is not None and not door["cycles"].empty:
        c = door["cycles"]
        ab = c[c["prediction"] == "Abnormal resistance"]
        if len(ab):
            by_op = ab["operation"].value_counts()
            out.append(f"Door: abnormal cycles are {'mostly ' + by_op.idxmax().lower() + 's' if by_op.max() > len(ab) / 2 else 'split between opens and closes'} "
                       f"({', '.join(f'{k.lower()} {v}' for k, v in by_op.items())}); "
                       f"they draw {ab['cur_mean_mid'].mean() / max(1e-9, c[c['prediction'] == 'Normal']['cur_mean_mid'].mean()) - 1:+.0%} "
                       "more sustained current than normal cycles.")
            span = float(c["end_s"].max()) or 1.0
            late = (ab["start_s"] > 0.5 * span).mean()
            if late >= 0.7 or late <= 0.3:
                out.append(f"Door: {late:.0%} of the abnormal cycles fall in the second half of the stream, "
                           "so the resistance is " + ("getting worse over the recording." if late >= 0.7 else "easing over the recording."))
    shm = results.get("shm")
    if shm:
        d = pd.DataFrame([{"file_id": f["file_id"], "damage": f["damage"], "top": f["top_share"]} for f in shm["files"]])
        out.append(f"Structural health: damage ranges {d['damage'].min():.2f} to {d['damage'].max():.2f} across {len(d)} points; "
                   f"on average the largest 0.1% of stress cycles cause {d['top'].mean():.0%} of the damage, so a few "
                   "heavy events matter more than everyday vibration.")
    rail = results.get("rail")
    if rail:
        files = rail["files"]
        bad = [f for f in files if f["prediction"] != "Normal"]
        if bad:
            sp_bad = sum(f["speed"]["speed_km_h"] for f in bad) / len(bad)
            sp_all = sum(f["speed"]["speed_km_h"] for f in files) / len(files)
            out.append(f"Rail: corrugated recordings were taken at about {sp_bad:.0f} km/h against {sp_all:.0f} km/h overall"
                       + ("; the speed-normalised spectrum keeps the pitch comparable." if abs(sp_bad - sp_all) > 5 else "."))
        ratio = len(bad) / len(files)
        out.append(f"Rail: {ratio:.0%} of recordings are corrugated, against 14% in the training data"
                   + (" — a heavier-worn stretch than usual." if ratio > 0.2 else "."))
    acv = results.get("acv")
    if acv:
        f = acv["files"][0]
        tl = f.get("excess_timeline")
        top = f["ranking"][0]
        if tl is not None and top in tl and tl["time"].notna().any():
            ex = tl.dropna(subset=[top])
            if len(ex) > 10:
                ex = ex.assign(hour=ex["time"].dt.hour)
                by_hour = ex.groupby("hour")[top].mean()
                if len(by_hour) > 3:
                    out.append(f"Air conditioning: Car {top}'s excess peaks around {int(by_hour.idxmax()):02d}:00 "
                               f"({by_hour.max():+.2f} °C) and is smallest around {int(by_hour.idxmin()):02d}:00; "
                               "a leak shows most when the cooling load is highest.")
    return out
