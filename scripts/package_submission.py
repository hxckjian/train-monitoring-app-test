"""Build the submission folder exactly as Problem Statement 3 Section 4 lays it out.

    .venv/Scripts/python -m scripts.package_submission --team "Team Name" [--video path/to/demo.mp4]

Produces  dist/<Team Name>/
    demo_video.<ext>          copied from --video if given (record it with the app; <= 3 min)
    predictions.zip           rebuilt through the same pipeline as the app's Submission page
    app/                      this project without the dataset, environments and caches
    Optional_Items/
        write_up.md           approach, validation, assumptions (one copy covers all four)
        Door/ ACV/ Rail Corrugation/ SHM/    each with code/ and model/

Raw datasets and the example-submission folder are never copied (spec Section 4 notes).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EXCLUDE = {"repo", ".venv", "venv", "artifacts_cache", ".git", ".pytest_cache", "__pycache__",
           "dist", ".ipynb_checkpoints"}
FOLDER = {"door": "Door", "acv": "ACV", "rail": "Rail Corrugation", "shm": "SHM"}


def copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, ignore=lambda d, names: [n for n in names if n in EXCLUDE],
                    dirs_exist_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", required=True, help="exactly as registered")
    ap.add_argument("--video", type=Path, help="demo recording, <= 3 minutes")
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    a = ap.parse_args()

    team = a.out / a.team
    if team.exists():
        shutil.rmtree(team)
    team.mkdir(parents=True)

    from scripts.build_predictions import main as build
    if build() != 0:
        raise SystemExit("predictions.zip did not validate; fix that first")
    shutil.copy2(ROOT / "predictions" / "predictions.zip", team / "predictions.zip")

    copy_tree(ROOT, team / "app")
    (team / "app" / "predictions").mkdir(exist_ok=True)

    opt = team / "Optional_Items"
    opt.mkdir()
    write_up = opt / "write_up.md"
    parts = ["# NebulaX PS3 write-up (covers all four subsystems)\n",
             "This single write-up covers Door, ACV, Rail Corrugation and SHM.\n"]
    for name in ("HANDOFF.md", "DESIGN.md", "PROJECT-STATE.md"):
        p = ROOT / name
        if p.exists():
            parts.append(f"\n\n---\n\n## From {name}\n\n" + p.read_text(encoding="utf-8"))
    write_up.write_text("".join(parts), encoding="utf-8")

    for key, folder in FOLDER.items():
        src = ROOT / "subsystems" / key
        if not (src / "artifacts").exists():
            continue
        code, model = opt / folder / "code", opt / folder / "model"
        code.mkdir(parents=True)
        model.mkdir(parents=True)
        for f in src.glob("*.py"):
            shutil.copy2(f, code / f.name)
        for f in (src / "artifacts").iterdir():
            shutil.copy2(f, model / f.name)
        for extra in ("scoring", "core"):
            copy_tree(ROOT / extra, code / extra)

    if a.video:
        shutil.copy2(a.video, team / f"demo_video{a.video.suffix.lower()}")
    else:
        (team / "demo_video.TODO.txt").write_text(
            "Record a <= 3 minute screen capture of the app: pick a subsystem, upload a file, "
            "view the verdict, download the CSV, then build predictions.zip. Save it here as "
            "demo_video.mp4 and delete this note.\n", encoding="utf-8")

    size = sum(f.stat().st_size for f in team.rglob("*") if f.is_file()) / 1e6
    print(f"submission folder: {team}  ({size:.1f} MB)")
    for p in sorted(team.rglob("*")):
        if p.is_dir() and p.parent in (team, opt):
            print("  ", p.relative_to(team))


if __name__ == "__main__":
    main()
