"""Pre-registered Rail experiment: do wavelength-domain features beat the ported baseline?

Protocol (fixed before running):
- Same 272 files, same 5 grouped folds as the ported model (fold ids from
  subsystems/rail/artifacts/oof.csv), same side-swap augmentation inside the
  training folds only, same classifier (RandomForest 300 trees, max_features 0.7,
  class_weight balanced, seed 42).
- Feature sets compared: baseline (ported), baseline + wavelength, wavelength only.
- Decision rule: adopt baseline + wavelength only if its macro F1 is higher on
  the original folds AND on 3 fresh grouped shuffles (seeds 1, 2, 3).
- Everything is written to subsystems/rail/artifacts/experiment_wavelength.json.
  A null result is reported as a null result.

    .venv/Scripts/python -m scripts.rail_wavelength_experiment
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import StratifiedGroupKFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.registry import DATA_ROOT                                 # noqa: E402
from subsystems.rail.features import LABELS, clean_data, extract_features, load_input  # noqa: E402
from subsystems.rail.wavelength import wavelength_features         # noqa: E402

ART = ROOT / "subsystems" / "rail" / "artifacts"
CACHE = ROOT / "artifacts_cache" / "rail_train_features.pkl"
SEED = 42


def augment(x: pd.DataFrame, y: pd.Series):
    m = x.copy()
    for c in [c for c in x.columns if c.startswith("side_i_")]:
        c2 = "side_ii_" + c[len("side_i_"):]
        if c2 in x.columns:
            m[c], m[c2] = x[c2].to_numpy(), x[c].to_numpy()
    for c in [c for c in x.columns if c.startswith("side_contrast_")]:
        m[c] = -x[c].to_numpy()
    return (pd.concat([x, m], ignore_index=True),
            pd.concat([y, y.replace({"Side I": "Side II", "Side II": "Side I"})], ignore_index=True))


def model():
    return RandomForestClassifier(n_estimators=300, max_features=0.7, class_weight="balanced",
                                  random_state=SEED, n_jobs=-1)


def features_all() -> tuple[pd.DataFrame, pd.Series, list[str]]:
    labels = pd.read_csv(DATA_ROOT / "Rail_Corrugation" / "Train_Labels.csv")
    if CACHE.exists():
        x = pd.read_pickle(CACHE)
    else:
        rows, t = [], time.time()
        for i, name in enumerate(labels.filename, 1):
            frame = load_input(DATA_ROOT / "Rail_Corrugation" / "Train" / name)
            base = extract_features(frame).iloc[0].to_dict()
            base.update(wavelength_features(frame, clean_data(frame)))
            rows.append(base)
            if i % 20 == 0:
                print(f"features {i}/{len(labels)}  {time.time() - t:.0f}s", flush=True)
        x = pd.DataFrame(rows)
        CACHE.parent.mkdir(exist_ok=True)
        x.to_pickle(CACHE)
    return x, labels.label, list(labels.filename)


def cv_score(x, y, folds):
    pred = np.empty(len(y), dtype=object)
    per_fold = []
    for k in sorted(set(folds)):
        va = np.where(folds == k)[0]
        tr = np.where(folds != k)[0]
        ax, ay = augment(x.iloc[tr], y.iloc[tr])
        m = model().fit(ax, ay)
        pred[va] = m.predict(x.iloc[va])
        per_fold.append(float(f1_score(y.iloc[va], pred[va], labels=list(LABELS), average="macro")))
    pooled = float(f1_score(y, pred, labels=list(LABELS), average="macro"))
    return pooled, per_fold, pred


def main() -> None:
    x, y, names = features_all()
    wl_cols = [c for c in x.columns if "_wl_" in c]
    base_cols = [c for c in x.columns if c not in wl_cols]
    sets = {"baseline": base_cols, "baseline_plus_wavelength": base_cols + wl_cols,
            "wavelength_only": wl_cols}
    oof = pd.read_csv(ART / "oof.csv").set_index("file_id")
    orig_folds = oof.loc[names, "fold"].to_numpy()
    groups = pd.util.hash_pandas_object(x[base_cols], index=False).to_numpy()

    report = {"protocol": __doc__.strip(), "n_files": len(y), "n_features": {k: len(v) for k, v in sets.items()},
              "original_folds": {}, "fresh_shuffles": {}}
    preds = {}
    for name, cols in sets.items():
        pooled, per_fold, pred = cv_score(x[cols], y, orig_folds)
        preds[name] = pred
        report["original_folds"][name] = {"pooled_macro_f1": pooled, "per_fold": per_fold,
                                          "mean": float(np.mean(per_fold)), "std": float(np.std(per_fold))}
        print(f"{name:26s} original folds: pooled {pooled:.4f}  mean {np.mean(per_fold):.4f} ± {np.std(per_fold):.4f}", flush=True)
    for name in ("baseline", "baseline_plus_wavelength"):
        vals = []
        for seed in (1, 2, 3):
            folds = np.zeros(len(y), dtype=int)
            for k, (_, va) in enumerate(StratifiedGroupKFold(5, shuffle=True, random_state=seed).split(x, y, groups)):
                folds[va] = k
            vals.append(cv_score(x[sets[name]], y, folds)[0])
        report["fresh_shuffles"][name] = {"pooled_by_seed": vals, "mean": float(np.mean(vals))}
        print(f"{name:26s} fresh shuffles: {np.round(vals, 4).tolist()}  mean {np.mean(vals):.4f}", flush=True)

    b, w = report["original_folds"]["baseline"]["pooled_macro_f1"], report["original_folds"]["baseline_plus_wavelength"]["pooled_macro_f1"]
    fb, fw = report["fresh_shuffles"]["baseline"]["mean"], report["fresh_shuffles"]["baseline_plus_wavelength"]["mean"]
    adopt = (w > b) and (fw > fb)
    chosen = "baseline_plus_wavelength" if adopt else "baseline"
    report["decision"] = {"adopt_wavelength": adopt, "chosen": chosen,
                          "reason": (f"original folds {w:.4f} vs {b:.4f}; fresh shuffles {fw:.4f} vs {fb:.4f}")}
    cols = sets[chosen]
    report["chosen_classification"] = classification_report(y, preds[chosen], output_dict=True, zero_division=0)

    # overfitting check: in-sample score of the final fit vs the out-of-fold score
    ax, ay = augment(x[cols], y)
    final = model().fit(ax, ay)
    in_sample = float(f1_score(y, final.predict(x[cols]), labels=list(LABELS), average="macro"))
    report["overfit_check"] = {"in_sample_macro_f1": in_sample,
                               "out_of_fold_macro_f1": report["original_folds"][chosen]["pooled_macro_f1"],
                               "note": "a random forest fits its training set almost perfectly; the gap is expected and the out-of-fold number is the one to trust"}
    print("decision:", report["decision"], flush=True)
    (ART / "experiment_wavelength.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    if adopt:
        joblib.dump({"model": final, "feature_names": cols}, ART / "model.joblib")
        cfg = json.loads((ART / "config.json").read_text(encoding="utf-8"))
        r = report["original_folds"][chosen]
        cr = report["chosen_classification"]
        cfg.update({
            "model_version": "rail-v2",
            "origin": cfg["origin"] + "; v2 adds wavelength-domain (λ = v/f) band features, adopted by the pre-registered experiment in artifacts/experiment_wavelength.json",
            "validation": {**cfg["validation"],
                           "mean_score": round(r["mean"], 4), "std_score": round(r["std"], 4),
                           "pooled_out_of_fold_score": round(r["pooled_macro_f1"], 4),
                           "folds": [round(v, 4) for v in r["per_fold"]],
                           "per_class_f1": {k: round(cr[k]["f1-score"], 4) for k in LABELS},
                           "side_i_recall": round(cr["Side I"]["recall"], 4),
                           "in_sample_score": round(in_sample, 4)},
        })
        (ART / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        pd.DataFrame({"file_id": names, "truth": y, "estimate": preds[chosen], "fold": orig_folds}).to_csv(ART / "oof.csv", index=False)
        print("rail-v2 artifact written", flush=True)
    else:
        cfg = json.loads((ART / "config.json").read_text(encoding="utf-8"))
        cfg["validation"]["in_sample_score"] = round(float(f1_score(
            y, model().fit(*augment(x[base_cols], y)).predict(x[base_cols]), labels=list(LABELS), average="macro")), 4)
        (ART / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        print("baseline kept; null result recorded", flush=True)


if __name__ == "__main__":
    main()
