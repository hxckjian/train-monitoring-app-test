"""Command-line inference, as required by each Info Kit (Section 5):

    python predict.py --subsystem rail --input Test1.csv Test2.csv --output rail_predictions.csv
    python predict.py --subsystem door --input Test.csv --output door_predictions.csv
    python predict.py --subsystem all  --output predictions/     # every subsystem on the bundled test inputs

--input takes one or more files (or a directory, which is expanded). --output is a
CSV path, or a directory in which the official filename is used. Every output
passes the same schema validator the app uses before it is written. This is the
same predict() the app calls; there is one inference path.
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.registry import SUBSYSTEMS  # noqa: E402
from core.submission import SCHEMAS, validate_submission  # noqa: E402


def _files(paths: list[Path], accepts: tuple[str, ...]) -> list[io.BytesIO]:
    out = []
    for p in paths:
        cands = sorted(p.iterdir()) if p.is_dir() else [p]
        for c in cands:
            if c.suffix.lower().lstrip(".") in accepts:
                b = io.BytesIO(c.read_bytes())
                b.name = c.name
                out.append(b)
    if not out:
        raise SystemExit(f"no input files with extension {accepts} in {paths}")
    return out


def run(key: str, inputs: list[Path] | None, output: Path) -> Path:
    spec = SUBSYSTEMS[key]
    if not spec.available:
        raise SystemExit(f"{key}: no trained model available")
    paths = inputs or spec.test_inputs()
    if not paths:
        raise SystemExit(f"{key}: no --input given and no bundled test data found")
    files = _files([Path(p) for p in paths], spec.accepts)
    df = spec.module.predict(files)
    expected = None if key == "door" else [f.name for f in files]
    errors = validate_submission(key, df, expected_ids=expected)
    if errors:
        raise SystemExit(f"{key}: output failed schema validation:\n  " + "\n  ".join(errors))
    dest = output / SCHEMAS[key].filename if (output.is_dir() or output.suffix == "") else output
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dest, index=False)
    print(f"{key}: {len(df)} rows -> {dest}")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subsystem", choices=list(SUBSYSTEMS) + ["all"], required=True)
    ap.add_argument("--input", nargs="*", type=Path, help="input file(s) or a directory; default: bundled test data")
    ap.add_argument("--output", type=Path, required=True, help="CSV path, or a directory")
    a = ap.parse_args()
    keys = list(SUBSYSTEMS) if a.subsystem == "all" else [a.subsystem]
    if a.subsystem == "all" and a.input:
        raise SystemExit("--input applies to one subsystem at a time; use --subsystem <key>")
    for k in keys:
        run(k, a.input, a.output)


if __name__ == "__main__":
    main()
