"""predict.py is the Info Kit CLI; it must use the app's inference path and validator."""
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "repo" / "PS3" / "02_Datasets"


@pytest.mark.skipif(not (DATA / "ACV" / "Test").exists(), reason="dataset absent")
def test_cli_acv_writes_official_csv(tmp_path):
    out = tmp_path / "acv_predictions.csv"
    r = subprocess.run([sys.executable, str(ROOT / "predict.py"), "--subsystem", "acv",
                        "--input", str(DATA / "ACV" / "Test" / "acv_test_case.xlsx"),
                        "--output", str(out)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr[-800:]
    df = pd.read_csv(out)
    assert list(df.columns) == ["file_id", "ranked_cars"]
    assert sorted(df.ranked_cars.iloc[0].split("|")) == [f"{i:02d}" for i in range(1, 9)]


def test_cli_rejects_unknown_subsystem():
    r = subprocess.run([sys.executable, str(ROOT / "predict.py"), "--subsystem", "nope",
                        "--output", "x.csv"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode != 0
