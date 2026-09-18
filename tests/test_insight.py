"""Dashboard insight and generic monitor logic, without Streamlit."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "app"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import insight  # noqa: E402
from subsystems.generic import monitor  # noqa: E402


def test_zone_rules_cover_known_stations():
    assert insight.zone_of(103.7066, 1.3400) == "West"        # Jurong East
    assert insight.zone_of(103.7866, 1.4370) == "North"       # Woodlands
    assert insight.zone_of(103.9020, 1.4050) == "North-East"  # Punggol
    assert insight.zone_of(103.9450, 1.3530) == "East"        # Tampines
    assert insight.zone_of(103.8520, 1.2830) == "Central"     # Raffles Place


def test_events_rank_by_severity_and_cover_every_subsystem():
    cycles = pd.DataFrame({"cycle": [1, 2], "operation": ["Open", "Close"],
                           "prediction": ["Normal", "Abnormal resistance"], "p_abnormal": [0.1, 0.9],
                           "cur_mean_mid": [500, 720], "start_time": ["a", "b"], "start_s": [0, 400]})
    results = {
        "door": {"cycles": cycles},
        "shm": {"files": [{"file_id": "t1.csv", "damage": 0.9, "n_cycles": 10, "top_share": 0.99,
                           "max_range": 50}]},
        "rail": {"files": [{"file_id": "T1.csv", "prediction": "Side I",
                            "proba": {"Normal": .1, "Side I": .8, "Side II": .1},
                            "speed": {"speed_km_h": 40}, "side_i_rms": 1, "side_ii_rms": .5}],
                 "predictions": pd.DataFrame({"file_id": ["T1.csv"], "prediction": ["Side I"]})},
        "acv": {"files": [{"file_id": "c.xlsx", "ranking": ["03", "01"],
                           "scores": {"03": 0.2, "01": 0.05},
                           "excess_timeline": pd.DataFrame({"time": pd.to_datetime(["2021-06-24", "2021-06-25"]),
                                                            "03": [0.2, 0.3]})}]},
    }
    ev = insight.events(results)
    assert {e["subsystem"] for e in ev} == {"Door", "Structural health", "Rail corrugation",
                                           "Air conditioning"}
    assert all(0 <= e["severity"] <= 1 for e in ev)
    assert ev == sorted(ev, key=lambda e: -e["severity"])
    assert insight.fleet_state(results) == {"door": "alert", "shm": "alert", "rail": "alert",
                                            "acv": "alert"}
    assert set(insight.trends(results)) == {"door", "shm", "rail", "acv"}
    top = insight.top_events(ev + [dict(ev[0], severity=0.99)], 3)
    assert len({e["subsystem"] for e in top}) == 3


def test_generic_peer_ranking_finds_the_hot_unit():
    rng = np.random.default_rng(0)
    n = 200
    df = pd.DataFrame({f"u{i}": rng.normal(0, 0.2, n) for i in range(6)})
    df["u3"] += 1.5
    rank = monitor.peer_ranking(df, list(df.columns))
    assert rank.iloc[0]["unit"] == "u3" and rank["rank"].tolist() == list(range(1, 7))
    state, title, _ = monitor.verdict_for_ranking(rank, "Unit")
    assert state == "alert" and "Unit u3 " in title
    assert monitor.short_names(["Car 01 - T", "Car 02 - T"]) == {"Car 01 - T": "01", "Car 02 - T": "02"}


def test_quickdrop_routes_every_competition_format():
    from core import quickdrop
    assert quickdrop.detect("case.xlsx", b"PK")[0] == "acv"
    assert quickdrop.detect("Test.csv", b"Datetime,Motor current(mA),x\n2023-7-5-0-0-0-0,1,2\n")[0] == "door"
    assert quickdrop.detect("Test1.csv", b"Rotating speed,Vibration of bearing in position 1 of car 1\n0,0.1\n")[0] == "rail"
    assert quickdrop.detect("test01.csv", b"0.5203\n0.51\n")[0] == "shm"
    assert quickdrop.detect("other.csv", b"a,b\n1,2\n")[0] == "generic"
