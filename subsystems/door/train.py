"""Train the Door subsystem and save every artifact inference needs.

Run from the project root:

    python -m subsystems.door.train

Importing this module does not train anything.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

MODULE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODULE_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scoring.metrics import Segment, door_iou_weighted_f1  # noqa: E402
from subsystems.door.features import (  # noqa: E402
    FEATURE_COLUMNS,
    LABEL_ABNORMAL,
    LABEL_NORMAL,
    VALID_LABELS,
    clean_data,
    extract_features,
    parse_datetime_series,
    segment_data,
)

SEED = 20260918
N_FOLDS = 5
ARTIFACT_DIR = MODULE_DIR / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "model.joblib"
CONFIG_PATH = ARTIFACT_DIR / "config.json"

DEFAULT_DATA_DIR = PROJECT_ROOT / "repo" / "PS3" / "02_Datasets" / "Door"


# --------------------------------------------------------------------------
# Gap threshold, derived from the data rather than chosen
# --------------------------------------------------------------------------

def derive_gap_seconds(df: pd.DataFrame) -> tuple[float, dict]:
    """Find the cut between within-cycle sampling and between-cycle silence.

    Unsupervised: the sorted inter-row gaps are strongly bimodal, so we take the
    largest multiplicative jump between consecutive sorted gaps and put the
    threshold at the geometric mean of that pair. This never looks at the answer
    file, so it transfers to an unseen stream.
    """
    gaps = df["_t"].diff().dt.total_seconds().dropna().to_numpy()
    gaps = np.sort(gaps[gaps > 0])
    if gaps.size < 2:
        raise ValueError("not enough rows to derive a gap threshold")
    ratios = gaps[1:] / np.maximum(gaps[:-1], 1e-9)
    k = int(np.argmax(ratios))
    threshold = float(np.sqrt(gaps[k] * gaps[k + 1]))
    diag = {
        "largest_within_cycle_gap_s": float(gaps[k]),
        "smallest_between_cycle_gap_s": float(gaps[k + 1]),
        "separation_ratio": float(gaps[k + 1] / max(gaps[k], 1e-9)),
    }
    return threshold, diag


# --------------------------------------------------------------------------
# Labelling detected segments from the answer file
# --------------------------------------------------------------------------

def label_segments(segments, answer: pd.DataFrame) -> np.ndarray:
    """Attach the true status to each detected segment by maximum overlap.

    Uses the same IoU definition the metric uses. A detected segment that
    overlaps nothing gets None and is excluded from training.
    """
    a0 = parse_datetime_series(answer["start_time"]).to_numpy()
    a1 = parse_datetime_series(answer["end_time"]).to_numpy()
    status = answer["status"].to_numpy()

    out = []
    for seg in segments:
        s = np.datetime64(seg.start_time)
        e = np.datetime64(seg.end_time)
        inter = (np.minimum(a1, e) - np.maximum(a0, s)) / np.timedelta64(1, "s")
        inter = np.maximum(inter, 0.0)
        union = ((a1 - a0) / np.timedelta64(1, "s")
                 + (e - s) / np.timedelta64(1, "s") - inter)
        iou = np.where(union > 0, inter / np.maximum(union, 1e-9), 0.0)
        out.append(status[int(np.argmax(iou))] if iou.max() > 0 else None)
    return np.array(out, dtype=object)


def to_metric_segments(segments, labels) -> list[Segment]:
    """Convert to the scorer's representation, in seconds from a common origin."""
    if not len(segments):
        return []
    origin = min(s.start_time for s in segments)
    return [
        Segment(
            start=(s.start_time - origin).total_seconds(),
            end=(s.end_time - origin).total_seconds(),
            label=str(lab),
        )
        for s, lab in zip(segments, labels)
    ]


def build_model() -> RandomForestClassifier:
    """A deliberately plain baseline. The MVP brief says no heavy tuning."""
    return RandomForestClassifier(
        n_estimators=400,
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        random_state=SEED,
        n_jobs=-1,
    )


# --------------------------------------------------------------------------
# Leakage-safe validation
# --------------------------------------------------------------------------

def contiguous_folds(n_items: int, n_folds: int) -> list[np.ndarray]:
    """Split an ordered sequence into contiguous blocks - never shuffled.

    Door is one continuous recording. Neighbouring cycles share operating
    conditions, so a random split would put a cycle's near-twin in the training
    set and report a flattering number. Contiguous time blocks are the closest
    honest analogue of 'a different stretch of the same door'.
    """
    return [np.array(sorted(b)) for b in np.array_split(np.arange(n_items), n_folds)]


def cross_validate(df: pd.DataFrame, answer: pd.DataFrame,
                   gap_seconds: float) -> dict:
    """Score the WHOLE pipeline per fold: segment, featurise, classify, score."""
    all_segments = segment_data(df, gap_seconds)
    y_all = label_segments(all_segments, answer)

    keep = np.array([lab is not None for lab in y_all])
    segments = [s for s, k in zip(all_segments, keep) if k]
    y = y_all[keep]
    X = extract_features(df, segments)

    folds = contiguous_folds(len(segments), N_FOLDS)
    scores, accs, details = [], [], []

    for i, val_idx in enumerate(folds, start=1):
        train_idx = np.setdiff1d(np.arange(len(segments)), val_idx)
        model = build_model()
        model.fit(X.iloc[train_idx], y[train_idx])

        val_segments = [segments[j] for j in val_idx]
        pred = model.predict(X.iloc[val_idx])

        true_m = to_metric_segments(val_segments, y[val_idx])
        pred_m = to_metric_segments(val_segments, pred)
        score = door_iou_weighted_f1(true_m, pred_m)
        acc = float(np.mean(pred == y[val_idx]))

        scores.append(score)
        accs.append(acc)
        n_abn = int(np.sum(y[val_idx] == LABEL_ABNORMAL))
        details.append({"fold": i, "n_segments": len(val_idx),
                        "n_abnormal": n_abn, "iou_weighted_f1": score,
                        "accuracy": acc})
        print(f"  fold {i}: {len(val_idx):3d} cycles "
              f"({n_abn:2d} abnormal)  IoU-weighted F1 = {score:.4f}  "
              f"accuracy = {acc:.4f}")

    return {
        "folds": details,
        "mean_iou_weighted_f1": float(np.mean(scores)),
        "std_iou_weighted_f1": float(np.std(scores)),
        "mean_accuracy": float(np.mean(accs)),
        "n_segments": len(segments),
        "X": X, "y": y, "segments": segments,
    }


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Train the Door subsystem.")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                    help="folder holding Train.csv and Train_Segments_Answer.csv")
    args = ap.parse_args()

    train_csv = args.data_dir / "Train.csv"
    answer_csv = args.data_dir / "Train_Segments_Answer.csv"
    for p in (train_csv, answer_csv):
        if not p.exists():
            print(f"ERROR: required file not found: {p}", file=sys.stderr)
            return 2

    print(f"Door subsystem - training\n  data: {args.data_dir}")
    raw = pd.read_csv(train_csv)
    answer = pd.read_csv(answer_csv)
    df = clean_data(raw)
    print(f"  Train.csv {raw.shape}   answer segments: {len(answer)}")

    gap_seconds, gap_diag = derive_gap_seconds(df)
    segments = segment_data(df, gap_seconds)
    print(f"\nSEGMENTATION (threshold derived from data, answer file not used)")
    print(f"  largest within-cycle gap : {gap_diag['largest_within_cycle_gap_s']:.4f} s")
    print(f"  smallest between-cycle gap: {gap_diag['smallest_between_cycle_gap_s']:.4f} s")
    print(f"  separation ratio          : {gap_diag['separation_ratio']:.1f}x")
    print(f"  threshold chosen          : {gap_seconds:.4f} s")
    print(f"  segments found: {len(segments)}   answer file: {len(answer)}"
          f"   {'MATCH' if len(segments) == len(answer) else 'MISMATCH'}")

    print(f"\nCROSS-VALIDATION ({N_FOLDS} contiguous time blocks, no shuffling)")
    cv = cross_validate(df, answer, gap_seconds)

    print(f"\n  official metric  IoU-weighted F1 = "
          f"{cv['mean_iou_weighted_f1']:.4f} +/- {cv['std_iou_weighted_f1']:.4f}")
    print(f"  cycle accuracy                    = {cv['mean_accuracy']:.4f}")

    # Majority-class reference: the number any result must beat.
    y = cv["y"]
    majority = float(np.mean(y == LABEL_NORMAL))
    print(f"  always-Normal reference           = {majority:.4f} accuracy, "
          f"IoU-weighted F1 "
          f"{door_iou_weighted_f1(to_metric_segments(cv['segments'], y), to_metric_segments(cv['segments'], [LABEL_NORMAL] * len(y))):.4f}")

    print("\nFINAL MODEL (trained on all labelled cycles)")
    final = build_model()
    final.fit(cv["X"], cv["y"])

    importances = sorted(zip(FEATURE_COLUMNS, final.feature_importances_),
                         key=lambda kv: -kv[1])[:8]
    print("  top features:")
    for name, imp in importances:
        print(f"    {name:22s} {imp:.4f}")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, MODEL_PATH)
    config = {
        "model_version": "door-v1",
        "trained_at_seed": SEED,
        "gap_seconds": gap_seconds,
        "gap_diagnostics": gap_diag,
        "feature_columns": list(FEATURE_COLUMNS),
        "labels": list(VALID_LABELS),
        "n_training_segments": int(len(cv["y"])),
        "n_abnormal": int(np.sum(cv["y"] == LABEL_ABNORMAL)),
        "validation": {
            "split": f"{N_FOLDS} contiguous time blocks over the ordered cycle "
                     "sequence, no shuffling, grouped so no cycle is split",
            "metric": "IoU-weighted F1 (Door_Subsystem_Info_Kit.md Section 4)",
            "mean_iou_weighted_f1": cv["mean_iou_weighted_f1"],
            "std_iou_weighted_f1": cv["std_iou_weighted_f1"],
            "mean_accuracy": cv["mean_accuracy"],
            "folds": cv["folds"],
        },
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"\n  saved {MODEL_PATH.relative_to(PROJECT_ROOT)}")
    print(f"  saved {CONFIG_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
