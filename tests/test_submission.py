"""The validator must reject every way a submission can be malformed."""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.submission import build_predictions_zip, validate_submission  # noqa: E402


def door(**over):
    d = {"start_time": ["2023-7-5-0-0-0-0"], "end_time": ["2023-7-5-0-0-3-760"],
         "prediction": ["Normal"]}
    d.update(over)
    return pd.DataFrame(d)


def test_valid_door_passes():
    assert validate_submission("door", door()) == []


def test_door_file_id_column_is_rejected():
    df = door()
    df.insert(0, "file_id", ["Test.csv"])
    assert validate_submission("door", df)


def test_door_bad_label_spelling_rejected():
    assert validate_submission("door", door(prediction=["abnormal"]))


def test_door_iso_or_garbage_timestamp_rejected():
    assert validate_submission("door", door(start_time=["yesterday"]))


def test_door_end_before_start_rejected():
    assert validate_submission("door", door(end_time=["2023-7-5-0-0-0-0"]))


def test_shm_valid_and_nonpositive():
    ok = pd.DataFrame({"file_id": ["test01.csv"], "prediction": [0.05]})
    assert validate_submission("shm", ok) == []
    bad = pd.DataFrame({"file_id": ["test01.csv"], "prediction": [0.0]})
    assert validate_submission("shm", bad)


def test_shm_missing_extension_rejected():
    df = pd.DataFrame({"file_id": ["test01"], "prediction": [0.05]})
    assert validate_submission("shm", df)


def test_expected_ids_checked():
    df = pd.DataFrame({"file_id": ["test01.csv"], "prediction": [0.05]})
    errs = validate_submission("shm", df, expected_ids=["test01.csv", "test02.csv"])
    assert any("missing" in e for e in errs)


def test_acv_car_format():
    good = pd.DataFrame({"file_id": ["a.xlsx"], "ranked_cars": ["03|01|02"]})
    assert validate_submission("acv", good) == []
    bad = pd.DataFrame({"file_id": ["a.xlsx"], "ranked_cars": ["Car 3|1"]})
    assert validate_submission("acv", bad)


def test_wrong_column_order_rejected():
    df = pd.DataFrame({"prediction": [0.05], "file_id": ["test01.csv"]})
    assert validate_submission("shm", df)


def test_zip_is_flat_and_refuses_invalid():
    blob = build_predictions_zip({"door": door()})
    names = zipfile.ZipFile(io.BytesIO(blob)).namelist()
    assert names == ["door_predictions.csv"]           # top level, no folders
    with pytest.raises(ValueError, match="refusing"):
        build_predictions_zip({"door": door(prediction=["bad"])})
