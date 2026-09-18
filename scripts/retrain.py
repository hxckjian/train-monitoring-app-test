"""Gated retrain from operator outcomes.

    .venv/Scripts/python -m scripts.retrain [--min-outcomes 10] [--dry-run]

For Door and Rail, every fault closed with "confirmed" or "no fault found" whose
raw file is stored under data/uploads/ becomes a labelled example. The challenger
is trained on the competition training data plus those examples and scored under
the same leakage-safe folds as the incumbent (Door: 5 contiguous time blocks of
the original stream, new cycles appended as a sixth block; Rail: the original
5 grouped folds, new files as a sixth group). Promotion rule, fixed here:

    adopt only if the challenger's mean score on the ORIGINAL folds is at least
    the incumbent's minus 0.005 (it must not have forgotten the competition data)
    AND its score on the outcome block is higher than the incumbent's by 0.02.

SHM (a physics fit) and ACV (a fixed rule) do not retrain; their outcomes are
reported so watch bands can be reviewed by a person. Every attempt is appended
to data/retrain_log.json, promoted or not.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import events  # noqa: E402
from core.registry import DATA_ROOT  # noqa: E402
from scoring.metrics import door_iou_weighted_f1, macro_f1  # noqa: E402

LOG = ROOT / "data" / "retrain_log.json"


def log(entry: dict) -> None:
    LOG.parent.mkdir(exist_ok=True)
    hist = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else []
    hist.append({"at": events.now().isoformat(), **entry})
    LOG.write_text(json.dumps(hist, indent=1, default=str), encoding="utf-8")
    print(f"{entry['subsystem']}: {entry['summary']}")


def retrain_rail(oc: pd.DataFrame, dry_run: bool) -> None:
    from sklearn.base import clone
    from subsystems.rail.features import extract_features, load_input
    from subsystems.rail.predict import load_saved_model
    from scripts.model_search import augment, fit_predict
    rows = oc[(oc["subsystem"] == "rail") & oc["stored_file"].notna()]
    if rows.empty:
        return log({"subsystem": "rail", "promoted": False, "summary": "no stored outcomes"})
    artifact, cfg = load_saved_model()
    names = artifact["feature_names"]
    labels = pd.read_csv(DATA_ROOT / "Rail_Corrugation" / "Train_Labels.csv")
    cache = ROOT / "artifacts_cache" / "rail_train_features.pkl"
    x_tr = pd.read_pickle(cache) if cache.exists() else pd.concat(
        [extract_features(load_input(DATA_ROOT / "Rail_Corrugation" / "Train" / n)) for n in labels.filename], ignore_index=True)
    x_tr = x_tr.reindex(columns=names)
    y_tr = labels.label.reset_index(drop=True)
    # outcome label: confirmed keeps the verdict, no fault found means Normal
    xs, ys = [], []
    for r in rows.itertuples():
        feat = extract_features(load_input(r.stored_file)).reindex(columns=names)
        pred = str(r.title).split(":")[-1].replace("rail corrugated", "").strip()
        ys.append(pred if r.outcome == "confirmed" and pred in ("Side I", "Side II") else "Normal")
        xs.append(feat)
    x_new, y_new = pd.concat(xs, ignore_index=True), pd.Series(ys)
    oof = pd.read_csv(ROOT / "subsystems" / "rail" / "artifacts" / "oof.csv").set_index("file_id")
    folds = oof.loc[labels.filename, "fold"].to_numpy()
    x_all = pd.concat([x_tr, x_new], ignore_index=True)
    y_all = pd.concat([y_tr, y_new], ignore_index=True)
    f_all = np.concatenate([folds, np.full(len(y_new), 99)])
    model = artifact["model"]

    def cv(train_extra: bool) -> tuple[float, float]:
        pred = np.empty(len(y_all), dtype=object)
        for k in sorted(set(f_all)):
            va = np.where(f_all == k)[0]
            tr = np.where((f_all != k) & (train_extra | (f_all != 99)))[0]
            pred[va] = fit_predict(model, x_all, y_all, tr, va)
        orig = f_all != 99
        return (float(macro_f1(y_all[orig].tolist(), pred[orig].tolist())),
                float(macro_f1(y_all[~orig].tolist(), pred[~orig].tolist())))
    inc_orig, inc_new = cv(False)
    ch_orig, ch_new = cv(True)
    promote = ch_orig >= inc_orig - 0.005 and ch_new >= inc_new + 0.02
    summary = (f"{len(y_new)} outcome file(s); incumbent orig {inc_orig:.4f} / outcomes {inc_new:.4f}; "
               f"challenger orig {ch_orig:.4f} / outcomes {ch_new:.4f}; {'PROMOTED' if promote else 'kept incumbent'}")
    if promote and not dry_run:
        ax, ay = augment(x_all, y_all)
        final = clone(model).fit(ax, ay)
        joblib.dump({"model": final, "feature_names": names}, ROOT / "subsystems" / "rail" / "artifacts" / "model.joblib")
        cfg["model_version"] = cfg["model_version"] + "+outcomes"
        cfg.setdefault("lineage", []).append({"at": events.now().isoformat(), "outcomes": int(len(y_new)), "summary": summary})
        (ROOT / "subsystems" / "rail" / "artifacts" / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    log({"subsystem": "rail", "promoted": bool(promote and not dry_run), "summary": summary})


def retrain_door(oc: pd.DataFrame, dry_run: bool) -> None:
    from sklearn.base import clone
    from subsystems.door import train as dt
    from subsystems.door.features import clean_data, extract_features, segment_data
    from subsystems.door.predict import load_saved_model
    rows = oc[(oc["subsystem"] == "door") & oc["stored_file"].notna()]
    if rows.empty:
        return log({"subsystem": "door", "promoted": False, "summary": "no stored outcomes"})
    model, cfg = load_saved_model()
    raw = pd.read_csv(DATA_ROOT / "Door" / "Train.csv")
    answer = pd.read_csv(DATA_ROOT / "Door" / "Train_Segments_Answer.csv")
    df = clean_data(raw)
    gap = float(cfg["gap_seconds"])
    segs = segment_data(df, gap)
    y_all = dt.label_segments(segs, answer)
    keep = np.array([lab is not None for lab in y_all])
    segs = [s for s, k in zip(segs, keep) if k]
    y = np.array(y_all[keep])
    X = extract_features(df, segs)
    folds = dt.contiguous_folds(len(segs), dt.N_FOLDS)
    # outcome cycles: each stored stream's cycle number is in the event id title; label from outcome
    xs, ys, ms = [], [], []
    for path, grp in rows.groupby("stored_file"):
        d = clean_data(pd.read_csv(path))
        sg = segment_data(d, gap)
        feats = extract_features(d, sg)
        for r in grp.itertuples():
            try:
                cyc = int(str(r.title).split("cycle")[1].split()[0])
            except (IndexError, ValueError):
                continue
            if 1 <= cyc <= len(sg):
                xs.append(feats.iloc[[cyc - 1]])
                ys.append("Abnormal resistance" if r.outcome == "confirmed" else "Normal")
                ms.append(sg[cyc - 1])
    if not xs:
        return log({"subsystem": "door", "promoted": False, "summary": "outcomes could not be matched to cycles"})
    Xn, yn = pd.concat(xs, ignore_index=True), np.array(ys)

    def score_block(train_idx_X, train_idx_y, val_X, val_y, val_segs):
        m = clone(model).fit(train_idx_X, train_idx_y)
        pred = m.predict(val_X)
        return door_iou_weighted_f1(dt.to_metric_segments(val_segs, val_y), dt.to_metric_segments(val_segs, pred))
    inc_orig = np.mean([score_block(X.iloc[np.setdiff1d(np.arange(len(segs)), va)], y[np.setdiff1d(np.arange(len(segs)), va)],
                                    X.iloc[va], y[va], [segs[j] for j in va]) for va in folds])
    ch_orig = np.mean([score_block(pd.concat([X.iloc[np.setdiff1d(np.arange(len(segs)), va)], Xn]),
                                   np.concatenate([y[np.setdiff1d(np.arange(len(segs)), va)], yn]),
                                   X.iloc[va], y[va], [segs[j] for j in va]) for va in folds])
    inc_new = score_block(X, y, Xn, yn, ms)
    ch_new = np.mean([score_block(pd.concat([X, Xn.drop(index=i)]), np.concatenate([y, np.delete(yn, i)]),
                                  Xn.iloc[[i]], yn[[i]], [ms[i]]) for i in range(len(yn))])   # leave-one-outcome-out
    promote = ch_orig >= inc_orig - 0.005 and ch_new >= inc_new + 0.02
    summary = (f"{len(yn)} outcome cycle(s); incumbent orig {inc_orig:.4f} / outcomes {inc_new:.4f}; "
               f"challenger orig {ch_orig:.4f} / outcomes {ch_new:.4f}; {'PROMOTED' if promote else 'kept incumbent'}")
    if promote and not dry_run:
        final = clone(model).fit(pd.concat([X, Xn]), np.concatenate([y, yn]))
        joblib.dump(final, ROOT / "subsystems" / "door" / "artifacts" / "model.joblib")
        cfg["model_version"] = cfg["model_version"] + "+outcomes"
        cfg.setdefault("lineage", []).append({"at": events.now().isoformat(), "outcomes": int(len(yn)), "summary": summary})
        (ROOT / "subsystems" / "door" / "artifacts" / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    log({"subsystem": "door", "promoted": bool(promote and not dry_run), "summary": summary})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-outcomes", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    oc = events.outcomes()
    oc = oc[oc["outcome"].isin(["confirmed", "no_fault_found"])] if len(oc) else oc
    for key in ("shm", "acv"):
        n = int((oc["subsystem"] == key).sum()) if len(oc) else 0
        log({"subsystem": key, "promoted": False,
             "summary": f"{n} outcome(s); physics fit / fixed rule: not retrained, review watch bands"})
    for key, fn in (("door", retrain_door), ("rail", retrain_rail)):
        n = int((oc["subsystem"] == key).sum()) if len(oc) else 0
        if n < a.min_outcomes:
            log({"subsystem": key, "promoted": False, "summary": f"{n} outcome(s), below the minimum of {a.min_outcomes}"})
            continue
        fn(oc, a.dry_run)


if __name__ == "__main__":
    main()
