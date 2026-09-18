"""Rail and ACV were ported from the teammate's final_streamlit_app build.
These tests pin the contract the app relies on, using the competition inputs
when they are present (the dataset is gitignored)."""
import io
from pathlib import Path

import pytest

from core.registry import DATA_ROOT, SUBSYSTEMS
from core.submission import validate_submission


def _as_upload(p: Path) -> io.BytesIO:
    b = io.BytesIO(p.read_bytes())
    b.name = p.name
    return b


def test_all_four_subsystems_are_registered_and_available():
    assert all(SUBSYSTEMS[k].available for k in ("door", "shm", "rail", "acv"))


@pytest.mark.skipif(not (DATA_ROOT / "Rail_Corrugation" / "Test").exists(), reason="dataset absent")
def test_rail_predict_matches_schema_and_analyze_agrees():
    from subsystems.rail.predict import analyze, predict
    files = sorted((DATA_ROOT / "Rail_Corrugation" / "Test").glob("Test*.csv"))[:2]
    df = predict([_as_upload(p) for p in files])
    assert validate_submission("rail", df, expected_ids=[p.name for p in files]) == []
    res = analyze([_as_upload(p) for p in files])
    assert res["predictions"].equals(df)
    f = res["files"][0]
    assert f["grid"].shape[0] == 64 and abs(sum(f["proba"].values()) - 1) < 1e-6
    assert f["speed"]["speed_km_h"] > 0


@pytest.mark.skipif(not (DATA_ROOT / "ACV" / "Test").exists(), reason="dataset absent")
def test_acv_predict_lists_every_car_once():
    from subsystems.acv.predict import predict
    files = sorted((DATA_ROOT / "ACV" / "Test").glob("*.xlsx"))
    df = predict([_as_upload(p) for p in files])
    assert validate_submission("acv", df, expected_ids=[p.name for p in files]) == []
    cars = df["ranked_cars"].iloc[0].split("|")
    assert sorted(cars) == [f"{i:02d}" for i in range(1, 9)]
