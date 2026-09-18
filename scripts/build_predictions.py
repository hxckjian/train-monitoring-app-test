"""Build predictions.zip from the command line - the same path the app's
Submission page uses (registry -> predict() -> schema validation -> zip).

    .venv/Scripts/python -m scripts.build_predictions
"""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.registry import SUBSYSTEMS  # noqa: E402
from core.submission import SCHEMAS, build_predictions_zip, validate_submission  # noqa: E402


def main() -> int:
    frames, failed = {}, []
    for spec in SUBSYSTEMS.values():
        if not spec.available:
            print(f"{spec.key}: model pending, skipped")
            continue
        inputs = spec.test_inputs()
        files = []
        for p in inputs:
            b = io.BytesIO(p.read_bytes())
            b.name = p.name
            files.append(b)
        t = time.time()
        df = spec.module.predict(files)
        expected = None if spec.key == "door" else [p.name for p in inputs]
        errs = validate_submission(spec.key, df, expected_ids=expected)
        print(f"{spec.key}: {len(inputs)} input(s) -> {len(df)} rows in {time.time() - t:.0f}s"
              + (f"  INVALID: {errs}" if errs else "  valid"))
        if errs:
            failed.append(spec.key)
        else:
            frames[spec.key] = df
    out = ROOT / "predictions"
    out.mkdir(exist_ok=True)
    blob = build_predictions_zip(frames)
    (out / "predictions.zip").write_bytes(blob)
    for key, df in frames.items():
        df.to_csv(out / SCHEMAS[key].filename, index=False)
    print(f"predictions.zip: {len(frames)} file(s), {len(blob):,} bytes -> {out / 'predictions.zip'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
