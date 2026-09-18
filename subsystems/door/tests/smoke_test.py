"""One-command smoke test for the Door subsystem.

From the project root:

    python -m subsystems.door.tests.smoke_test

Verifies the whole handoff contract: artifacts load, a Streamlit-like upload is
accepted, predict() returns a correctly shaped DataFrame, and that DataFrame
survives a CSV round trip.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd

MODULE_DIR = Path(__file__).resolve().parent
SUBSYSTEM_DIR = MODULE_DIR.parent
PROJECT_ROOT = SUBSYSTEM_DIR.parents[1]

#: Prefer a local fixture; fall back to the repository sample rather than
#: duplicating a raw dataset into the package.
LOCAL_FIXTURE = MODULE_DIR / "sample_input.csv"
REPO_SAMPLE = PROJECT_ROOT / "repo" / "PS3" / "02_Datasets" / "Door" / "Test.csv"

EXPECTED_COLUMNS = ["start_time", "end_time", "prediction"]
VALID_LABELS = {"Normal", "Abnormal resistance"}

_passes = 0


def ok(message: str) -> None:
    global _passes
    _passes += 1
    print(f"PASS: {message}")


def resolve_sample() -> Path:
    for candidate in (LOCAL_FIXTURE, REPO_SAMPLE):
        if candidate.exists():
            return candidate
    raise AssertionError(
        f"no sample input found. Looked for {LOCAL_FIXTURE} and {REPO_SAMPLE}."
    )


def main() -> int:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    # 1-2. import must succeed and must not trigger training
    import subsystems.door.predict as predict_module
    from subsystems.door.features import make_uploaded_file
    ok("prediction module imported")

    assert not (SUBSYSTEM_DIR / "artifacts" / ".training_ran").exists(), \
        "importing the module appears to have started training"
    ok("importing the module did not trigger training")

    # 3. sample input
    sample_path = resolve_sample()
    ok(f"sample input found ({sample_path.name}, "
       f"{sample_path.stat().st_size / 1024:.0f} KB)")

    # 4-5. artifacts exist and load
    for artifact in ("model.joblib", "config.json"):
        p = SUBSYSTEM_DIR / "artifacts" / artifact
        assert p.exists(), f"missing artifact: {p}"
    ok("saved artifacts exist")

    model, config = predict_module.load_saved_model()
    assert model is not None, "model failed to load"
    assert config.get("feature_columns"), "config has no feature_columns"
    ok(f"model artifact loaded (version {config.get('model_version')}, "
       f"gap {config.get('gap_seconds'):.3f}s)")

    # 6. Streamlit-like upload object
    uploaded_file = make_uploaded_file(sample_path)
    assert hasattr(uploaded_file, "read") and hasattr(uploaded_file, "name"), \
        "upload wrapper is not file-like"
    ok("Streamlit-like upload accepted")

    # 7-8. predict returns a DataFrame
    result = predict_module.predict([uploaded_file])
    assert isinstance(result, pd.DataFrame), \
        f"predict() returned {type(result).__name__}, expected DataFrame"
    ok("predict([uploaded_file]) returned a DataFrame")

    # 9. not empty
    assert len(result) > 0, "predict() returned an empty DataFrame"
    ok(f"result is not empty ({len(result)} predicted segments)")

    # 10. exact columns, exact order
    assert list(result.columns) == EXPECTED_COLUMNS, (
        f"wrong columns: got {list(result.columns)}, expected {EXPECTED_COLUMNS}")
    ok("output schema is correct (start_time, end_time, prediction)")

    # 11. required values present
    for col in EXPECTED_COLUMNS:
        assert result[col].notna().all(), f"column '{col}' contains missing values"
    ok("no missing values in any required column")

    # 12. labels in the allowed set
    seen = set(result["prediction"].unique())
    unexpected = seen - VALID_LABELS
    assert not unexpected, f"unexpected label(s): {sorted(unexpected)}"
    ok(f"labels are valid ({', '.join(f'{k}={int(v)}' for k, v in result['prediction'].value_counts().items())})")

    # 13. timestamps parse in the dataset's native format
    for col in ("start_time", "end_time"):
        parts = result[col].astype(str).str.split("-", expand=True)
        assert parts.shape[1] == 7, \
            f"'{col}' is not the 7-field Y-M-D-H-M-S-ms format"
    ok("timestamps use the dataset's native 7-field format")

    # 14. start strictly before end on every row
    assert (result["start_time"] != result["end_time"]).all(), \
        "some segments have identical start and end times"
    ok("every segment has a non-zero duration")

    # 15-17. CSV round trip preserves row count and schema
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "door_predictions.csv"
        result.to_csv(out, index=False)
        ok("result saved with to_csv(index=False)")

        reloaded = pd.read_csv(out, dtype=str)
        assert list(reloaded.columns) == EXPECTED_COLUMNS, \
            f"columns changed on reload: {list(reloaded.columns)}"
        assert len(reloaded) == len(result), (
            f"row count changed on round trip: {len(result)} -> {len(reloaded)}")
        ok(f"prediction CSV round trip succeeded ({len(reloaded)} rows preserved)")

    print(f"\n{_passes} checks passed. Door subsystem is ready for integration.")
    print("\nValidation (from config.json):")
    v = config.get("validation", {})
    print(f"  metric : {v.get('metric')}")
    print(f"  split  : {v.get('split')}")
    print(f"  score  : {v.get('mean_iou_weighted_f1'):.4f} "
          f"+/- {v.get('std_iou_weighted_f1'):.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
