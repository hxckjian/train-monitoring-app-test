"""One-command smoke test for the SHM subsystem.

From the project root:

    python -m subsystems.shm.tests.smoke_test
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

MODULE_DIR = Path(__file__).resolve().parent
SUBSYSTEM_DIR = MODULE_DIR.parent
PROJECT_ROOT = SUBSYSTEM_DIR.parents[1]
REPO_SAMPLE = PROJECT_ROOT / "repo" / "PS3" / "02_Datasets" / "SHM" / "Test" / "test01.csv"
LOCAL_FIXTURE = MODULE_DIR / "sample_input.csv"
EXPECTED_COLUMNS = ["file_id", "prediction"]

_passes = 0


def ok(msg: str) -> None:
    global _passes
    _passes += 1
    print(f"PASS: {msg}")


def main() -> int:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    import subsystems.shm.predict as pm
    from subsystems.shm.features import make_uploaded_file
    ok("prediction module imported (no training on import)")

    sample = next((p for p in (LOCAL_FIXTURE, REPO_SAMPLE) if p.exists()), None)
    assert sample is not None, f"no sample input at {LOCAL_FIXTURE} or {REPO_SAMPLE}"
    ok(f"sample input found ({sample.name})")

    for a in ("model.joblib", "config.json"):
        assert (SUBSYSTEM_DIR / "artifacts" / a).exists(), f"missing artifact {a}"
    params, config = pm.load_saved_model()
    ok(f"artifacts loaded (m={params['m']:.3f}, version {config['model_version']})")

    up = make_uploaded_file(sample)
    result = pm.predict([up])
    assert isinstance(result, pd.DataFrame), f"got {type(result).__name__}"
    ok("predict([uploaded_file]) returned a DataFrame")

    assert list(result.columns) == EXPECTED_COLUMNS, f"columns {list(result.columns)}"
    ok("output schema is correct (file_id, prediction)")

    assert len(result) == 1, f"expected 1 row per file, got {len(result)}"
    assert result.loc[0, "file_id"] == sample.name, "file_id must be the uploaded name"
    ok(f"one row, file_id = {sample.name}")

    v = result["prediction"].to_numpy()
    assert np.issubdtype(v.dtype, np.number) and np.all(np.isfinite(v)) and np.all(v > 0), \
        f"prediction must be positive finite numeric, got {v}"
    ok(f"prediction is numeric and positive ({v[0]:.5f})")

    # the same handle, read twice, must give the same answer
    again = pm.predict([up])
    assert np.allclose(again["prediction"], result["prediction"]), "not deterministic"
    ok("deterministic and re-readable from the same handle")

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "shm_predictions.csv"
        result.to_csv(out, index=False)
        back = pd.read_csv(out)
        assert list(back.columns) == EXPECTED_COLUMNS and len(back) == len(result)
        assert np.allclose(back["prediction"], result["prediction"])
    ok("CSV round trip preserved schema, rows and values")

    try:
        pm.predict([])
        raise AssertionError("empty list should raise")
    except ValueError:
        ok("empty upload list is rejected with a clear error")

    v = config["validation"]
    print(f"\n{_passes} checks passed. SHM subsystem is ready for integration.")
    print(f"  metric : {v['metric']}\n  split  : {v['split']}\n"
          f"  score  : {v['mean_score']:.4f} +/- {v['std_score']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
