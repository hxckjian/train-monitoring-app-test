"""Pre-registered model search and benchmark for Rail, Door and ACV.

    .venv/Scripts/python -m scripts.model_search [--rail] [--door] [--acv]

Protocols (fixed before running; a null result stays a null result):

RAIL   Candidates: random forest, extra trees, histogram gradient boosting, logistic
       regression and RBF SVC over a small grid, on the ported feature set and on the
       set with wavelength features. Two numbers per candidate:
         (a) repeated grouped CV: 5 stratified group folds x 3 seeds, side-swap
             augmentation inside training folds only, macro F1 pooled per repeat;
         (b) NESTED estimate of the whole selection procedure: for each of the 5
             original outer folds, the candidate is chosen by (a) restricted to the
             outer-training files (3 inner folds x 1 seed), refitted, scored on the
             outer fold. This is the honest number for "we searched".
       Decision: adopt the top candidate by (a) only if its (a) mean beats the current
       recipe's (a) mean by >= 0.01 AND the nested estimate is not below the current
       recipe's (a) mean minus 0.01. Otherwise keep rail-v1.

DOOR   Same 5 contiguous time blocks as training. Candidates: current RF, extra trees,
       histogram gradient boosting, scaled logistic regression. Decision: adopt only if
       the mean IoU-weighted F1 improves by >= 0.01 with no fold worse. One recording,
       110 cycles: ties go to the incumbent.

ACV    Rule variants over the same peer-relative features (no parameters are fitted, so
       leave-one-case-out equals a plain evaluation). Decision: adopt only if a variant
       is at least as good on every case and strictly better on one (dominance).

Everything is written to subsystems/<key>/artifacts/benchmark.json, and the Validation
page draws the tables.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import (ExtraTreesClassifier, HistGradientBoostingClassifier,
                              RandomForestClassifier)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.registry import DATA_ROOT                          # noqa: E402
from scoring.metrics import acv_score, door_iou_weighted_f1  # noqa: E402

SEED = 42
LABELS = ("Normal", "Side I", "Side II")


# ------------------------------------------------------------------ rail

def rail_candidates() -> dict[str, object]:
    c: dict[str, object] = {}
    for mf in ("sqrt", 0.7):
        for leaf in (1, 3):
            c[f"rf_{mf}_leaf{leaf}"] = RandomForestClassifier(
                n_estimators=300, max_features=mf, min_samples_leaf=leaf,
                class_weight="balanced", random_state=SEED, n_jobs=-1)
            c[f"et_{mf}_leaf{leaf}"] = ExtraTreesClassifier(
                n_estimators=300, max_features=mf, min_samples_leaf=leaf,
                class_weight="balanced", random_state=SEED, n_jobs=-1)
    c["rf_0.7_leaf1_600"] = RandomForestClassifier(n_estimators=600, max_features=0.7,
                                                   class_weight="balanced", random_state=SEED, n_jobs=-1)
    for lr, depth in ((0.05, 3), (0.1, None)):
        c[f"hgb_lr{lr}_d{depth}"] = HistGradientBoostingClassifier(
            learning_rate=lr, max_depth=depth, max_iter=300, class_weight="balanced", random_state=SEED)
    for C in (0.1, 1.0, 10.0):
        c[f"logreg_C{C}"] = make_pipeline(StandardScaler(), LogisticRegression(
            C=C, class_weight="balanced", max_iter=5000))
    for C in (1.0, 10.0):
        c[f"svc_C{C}"] = make_pipeline(StandardScaler(), SVC(C=C, class_weight="balanced"))
    return c


def augment(x: pd.DataFrame, y: pd.Series):
    m = x.copy()
    for col in [col for col in x.columns if col.startswith("side_i_")]:
        c2 = "side_ii_" + col[len("side_i_"):]
        if c2 in x.columns:
            m[col], m[c2] = x[c2].to_numpy(), x[col].to_numpy()
    for col in [col for col in x.columns if col.startswith("side_contrast_")]:
        m[col] = -x[col].to_numpy()
    return (pd.concat([x, m], ignore_index=True),
            pd.concat([y, y.replace({"Side I": "Side II", "Side II": "Side I"})], ignore_index=True))


def fit_predict(model, x, y, tr, va):
    ax, ay = augment(x.iloc[tr], y.iloc[tr])
    return clone(model).fit(ax, ay).predict(x.iloc[va])


def grouped_folds(x, y, groups, seed, k=5):
    folds = np.zeros(len(y), dtype=int)
    for i, (_, va) in enumerate(StratifiedGroupKFold(k, shuffle=True, random_state=seed).split(x, y, groups)):
        folds[va] = i
    return folds


def repeated_cv(model, x, y, groups, seeds=(1, 2, 3), k=5) -> list[float]:
    out = []
    for s in seeds:
        folds = grouped_folds(x, y, groups, s, k)
        pred = np.empty(len(y), dtype=object)
        for f in range(k):
            va, tr = np.where(folds == f)[0], np.where(folds != f)[0]
            pred[va] = fit_predict(model, x, y, tr, va)
        out.append(float(f1_score(y, pred, labels=list(LABELS), average="macro")))
    return out


def search_rail() -> dict:
    t0 = time.time()
    x_all = pd.read_pickle(ROOT / "artifacts_cache" / "rail_train_features.pkl")
    labels = pd.read_csv(DATA_ROOT / "Rail_Corrugation" / "Train_Labels.csv")
    y = labels.label
    wl = [c for c in x_all.columns if "_wl_" in c]
    base = [c for c in x_all.columns if c not in wl]
    feature_sets = {"base": base, "base+wl": base + wl}
    groups = pd.util.hash_pandas_object(x_all[base], index=False).to_numpy()
    cands = rail_candidates()
    incumbent = ("rf_0.7_leaf1", "base")

    # (a) repeated grouped CV for every candidate x feature set
    table = []
    for fs, cols in feature_sets.items():
        for name, model in cands.items():
            scores = repeated_cv(model, x_all[cols], y, groups)
            table.append({"candidate": name, "features": fs, "repeats": [round(s, 4) for s in scores],
                          "mean": float(np.mean(scores)), "std": float(np.std(scores))})
            print(f"rail {fs:8s} {name:22s} {np.mean(scores):.4f} ± {np.std(scores):.4f}   {time.time() - t0:.0f}s", flush=True)
    table.sort(key=lambda r: -r["mean"])
    best = table[0]
    inc = next(r for r in table if (r["candidate"], r["features"]) == incumbent)

    # (b) nested estimate of the selection procedure on the original outer folds
    oof = pd.read_csv(ROOT / "subsystems" / "rail" / "artifacts" / "oof.csv").set_index("file_id")
    outer = oof.loc[labels.filename, "fold"].to_numpy()
    nested_pred = np.empty(len(y), dtype=object)
    chosen_per_fold = []
    for f in sorted(set(outer)):
        va, tr = np.where(outer == f)[0], np.where(outer != f)[0]
        best_inner, best_score = None, -1
        for fs, cols in feature_sets.items():
            xi, yi, gi = x_all.iloc[tr][cols].reset_index(drop=True), y.iloc[tr].reset_index(drop=True), groups[tr]
            for name, model in cands.items():
                s = np.mean(repeated_cv(model, xi, yi, gi, seeds=(1,), k=3))
                if s > best_score:
                    best_inner, best_score = (name, fs), s
        name, fs = best_inner
        nested_pred[va] = fit_predict(cands[name], x_all[feature_sets[fs]], y, tr, va)
        chosen_per_fold.append({"outer_fold": int(f), "chosen": name, "features": fs, "inner_score": round(float(best_score), 4)})
        print(f"rail nested outer fold {f}: chose {name}/{fs} (inner {best_score:.4f})   {time.time() - t0:.0f}s", flush=True)
    nested = float(f1_score(y, nested_pred, labels=list(LABELS), average="macro"))
    nested_folds = [float(f1_score(y[outer == f], nested_pred[outer == f], labels=list(LABELS), average="macro"))
                    for f in sorted(set(outer))]

    adopt = (best["mean"] >= inc["mean"] + 0.01) and (nested >= inc["mean"] - 0.01) \
        and (best["candidate"], best["features"]) != incumbent
    report = {"protocol": __doc__.split("DOOR")[0].strip(), "n_files": int(len(y)),
              "incumbent": {"candidate": incumbent[0], "features": incumbent[1], "mean": inc["mean"], "std": inc["std"]},
              "table": table, "best_by_repeated_cv": best,
              "nested": {"macro_f1_pooled": nested, "per_outer_fold": nested_folds,
                         "mean": float(np.mean(nested_folds)), "std": float(np.std(nested_folds)),
                         "chosen_per_fold": chosen_per_fold},
              "decision": {"adopt": bool(adopt),
                           "reason": f"best {best['candidate']}/{best['features']} repeated-CV {best['mean']:.4f} vs incumbent "
                                     f"{inc['mean']:.4f}; nested estimate {nested:.4f}"},
              "seconds": round(time.time() - t0)}
    art = ROOT / "subsystems" / "rail" / "artifacts"
    (art / "benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("rail decision:", report["decision"], flush=True)

    if adopt:
        cols = feature_sets[best["features"]]
        model = cands[best["candidate"]]
        ax, ay = augment(x_all[cols], y)
        final = clone(model).fit(ax, ay)
        # out-of-fold predictions of the adopted candidate on the original folds, for the report
        pred = np.empty(len(y), dtype=object)
        for f in sorted(set(outer)):
            va, tr = np.where(outer == f)[0], np.where(outer != f)[0]
            pred[va] = fit_predict(model, x_all[cols], y, tr, va)
        cr = classification_report(y, pred, output_dict=True, zero_division=0)
        per_fold = [float(f1_score(y[outer == f], pred[outer == f], labels=list(LABELS), average="macro")) for f in sorted(set(outer))]
        joblib.dump({"model": final, "feature_names": cols}, art / "model.joblib")
        cfg = json.loads((art / "config.json").read_text(encoding="utf-8"))
        cfg["model_version"] = "rail-v2"
        cfg["origin"] += f"; v2 = {best['candidate']} on {best['features']} features, adopted by scripts/model_search.py (artifacts/benchmark.json)"
        cfg["validation"].update({
            "split": "5 stratified grouped folds over 272 files (original fold ids), side-swap augmentation inside training folds; "
                     "candidate chosen by 5x3 repeated grouped CV; nested estimate of the search reported alongside",
            "mean_score": round(float(np.mean(per_fold)), 4), "std_score": round(float(np.std(per_fold)), 4),
            "pooled_out_of_fold_score": round(float(f1_score(y, pred, labels=list(LABELS), average="macro")), 4),
            "folds": [round(v, 4) for v in per_fold],
            "per_class_f1": {k: round(cr[k]["f1-score"], 4) for k in LABELS},
            "side_i_recall": round(cr["Side I"]["recall"], 4),
            "repeated_cv_mean": round(best["mean"], 4), "repeated_cv_std": round(best["std"], 4),
            "nested_search_estimate": round(nested, 4),
            "in_sample_score": round(float(f1_score(y, final.predict(x_all[cols]), labels=list(LABELS), average="macro")), 4),
        })
        (art / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        pd.DataFrame({"file_id": labels.filename, "truth": y, "estimate": pred, "fold": outer}).to_csv(art / "oof.csv", index=False)
        print("rail-v2 written", flush=True)
    return report


# ------------------------------------------------------------------ door

def search_door() -> dict:
    from subsystems.door import train as dt
    from subsystems.door.features import clean_data, extract_features, segment_data
    raw = pd.read_csv(DATA_ROOT / "Door" / "Train.csv")
    answer = pd.read_csv(DATA_ROOT / "Door" / "Train_Segments_Answer.csv")
    df = clean_data(raw)
    gap, _ = dt.derive_gap_seconds(df)
    segs = segment_data(df, gap)
    y_all = dt.label_segments(segs, answer)
    keep = np.array([lab is not None for lab in y_all])
    segs = [s for s, k in zip(segs, keep) if k]
    y = y_all[keep]
    X = extract_features(df, segs)
    folds = dt.contiguous_folds(len(segs), dt.N_FOLDS)
    cands = {
        "rf_current": dt.build_model(),
        "extra_trees": ExtraTreesClassifier(n_estimators=400, class_weight="balanced", random_state=20260918),
        "hgb": HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, class_weight="balanced", random_state=20260918),
        "logreg_scaled": make_pipeline(StandardScaler(), LogisticRegression(C=1.0, class_weight="balanced", max_iter=5000)),
    }
    table = []
    for name, model in cands.items():
        scores = []
        for va in folds:
            tr = np.setdiff1d(np.arange(len(segs)), va)
            pred = clone(model).fit(X.iloc[tr], y[tr]).predict(X.iloc[va])
            scores.append(door_iou_weighted_f1(dt.to_metric_segments([segs[j] for j in va], y[va]),
                                               dt.to_metric_segments([segs[j] for j in va], pred)))
        table.append({"candidate": name, "folds": [round(s, 4) for s in scores],
                      "mean": float(np.mean(scores)), "std": float(np.std(scores))})
        print(f"door {name:14s} {np.mean(scores):.4f} ± {np.std(scores):.4f}", flush=True)
    inc = table[0]
    better = [r for r in table[1:] if r["mean"] >= inc["mean"] + 0.01
              and all(a >= b for a, b in zip(r["folds"], inc["folds"]))]
    report = {"protocol": "5 contiguous time blocks, whole pipeline scored with IoU-weighted F1",
              "table": table, "decision": {"adopt": bool(better),
                                           "reason": (f"{better[0]['candidate']} dominates" if better
                                                      else "no candidate beats the incumbent by 0.01 on every fold; incumbent kept")}}
    (ROOT / "subsystems" / "door" / "artifacts" / "benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("door decision:", report["decision"], flush=True)
    return report


# ------------------------------------------------------------------ acv

def search_acv() -> dict:
    from subsystems.acv.features import extract_features, load
    labels = pd.read_csv(DATA_ROOT / "ACV" / "Train_Labels.csv", dtype=str)
    feats = {}
    for name in labels.filename:
        with open(DATA_ROOT / "ACV" / "Train" / name, "rb") as f:
            frame, cars = load(f)
        feats[name] = extract_features(frame, cars)
        print(f"acv features {name}", flush=True)
    variants = {
        "peer_mean (current)": lambda x: x.peer_mean,
        "peer_q90": lambda x: x.peer_q90,
        "peer_hot_fraction": lambda x: x.peer_hot_fraction,
        "excess_mean (own setpoint)": lambda x: x.excess_mean,
        "excess_peer_mean": lambda x: x.excess_peer_mean,
        "z-combined (peer_mean + excess_peer_mean)": lambda x: ((x.peer_mean - x.peer_mean.mean()) / (x.peer_mean.std() or 1)
                                                               + (x.excess_peer_mean - x.excess_peer_mean.mean()) / (x.excess_peer_mean.std() or 1)),
    }
    table = []
    for vname, fn in variants.items():
        per_case = []
        for name, true in zip(labels.filename, labels.faulty_car):
            x = feats[name]
            s = np.array(fn(x).to_numpy(dtype=float), dtype=float, copy=True)
            s[x.index.isin(x.attrs.get("unobserved", []))] = -np.inf
            ranked = [x.index[i] for i in np.argsort(-s, kind="stable")]
            per_case.append(acv_score([ranked], [true]))
        table.append({"variant": vname, "per_case": [round(v, 4) for v in per_case], "mean": float(np.mean(per_case))})
        print(f"acv {vname:44s} {np.mean(per_case):.4f}  {per_case}", flush=True)
    inc = table[0]
    dominant = [r for r in table[1:] if all(a >= b for a, b in zip(r["per_case"], inc["per_case"]))
                and any(a > b for a, b in zip(r["per_case"], inc["per_case"]))]
    report = {"protocol": "leave-one-case-out over 6 cases; rules have no fitted parameters",
              "table": table, "decision": {"adopt": bool(dominant),
                                           "reason": (f"{dominant[0]['variant']} dominates the current rule" if dominant
                                                      else "no variant is at least as good on every case and better on one; current rule kept")}}
    (ROOT / "subsystems" / "acv" / "artifacts" / "benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("acv decision:", report["decision"], flush=True)
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rail", action="store_true")
    ap.add_argument("--door", action="store_true")
    ap.add_argument("--acv", action="store_true")
    a = ap.parse_args()
    if not (a.rail or a.door or a.acv):
        a.rail = a.door = a.acv = True
    if a.acv:
        search_acv()
    if a.door:
        search_door()
    if a.rail:
        search_rail()


if __name__ == "__main__":
    main()
