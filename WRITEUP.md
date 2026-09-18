# NebulaX Problem Statement 3 · Train Condition Monitoring · write-up

One write-up for all four subsystems (spec Section 4.2). Every figure below is read from the model cards and validation reports in `subsystems/*/artifacts/`, which the training and validation scripts wrote; nothing is typed by hand.

## 1. What was built

- **Part 1, models**: four subsystems, each with its own leakage-safe split, the official metric reimplemented and unit-tested against the Info Kit worked examples (`scoring/metrics.py`, 28 tests), and a model card with the cross-validated score and its spread.
- **Part 2, the operator**: one console (`app/`) that turns each verdict into an action with urgency, reason and owner; a fleet log with acknowledge / shelve / close; a live network map with NEA weather and, given a DataMall key, service alerts and platform crowding; Operator and Engineer views; 'How to read this' notes for someone new to the data. Design sources in `DESIGN.md`.
- **Deliverables**: `predictions.zip` built through the app (schema-validated), `predict.py` CLI per Info Kit Section 5, `scripts/package_submission.py` for the team folder, Cloud Run deployment files.

## 2. Door · temporal segment detection + classification

- **Data**: one continuous stream, 110 labelled cycles (30 abnormal). Rows exist only during a cycle; the gap between cycles is ≥ 10 s against 0.02 s within one.
- **Segmentation**: gap threshold derived from the data (0.452 s, separation ratio 511×), never from the answer file. Boundaries are exact, so IoU = 1 on matches.
- **Model**: random forest (400 trees, seed 20260918) on 27 per-cycle features; objective Gini impurity, class weight balanced; the operating point is judged on the official metric.
- **Split / leakage**: 5 contiguous time blocks over the ordered cycle sequence, no shuffling, grouped so no cycle is split.
- **Result**: IoU-weighted F1 **0.9909 ± 0.0182** (always-Normal reference 0.7273). Folds: 0.955, 1.000, 1.000, 1.000, 1.000.
- **Benchmark** (`benchmark.json`): rf_current 0.9909; extra_trees 1.0000; hgb 0.9909; logreg_scaled 0.9909. Decision: no candidate beats the incumbent by 0.01 on every fold; incumbent kept.
- **Caveat**: one door, one recording; treat the score as an upper bound.

## 3. SHM · cumulative fatigue damage (regression)

- **Data**: 64 files of 581,120 stress samples; labels from rainflow + Miner (Info Kit §1.3).
- **Model**: rainflow counting, then D = Σ nᵢ·σᵢ^m / C with (m, C) fitted **in log space** so the objective matches MAPE (relative error). Fitted m = 5.030, the textbook exponent for welded steel; folds give m in [5.01, 5.03].
- **Split / leakage**: 5-fold over files, seed 20260918; m and C fitted inside each fold only.
- **Result**: max(0, 1 − MAPE) **0.9729 ± 0.0067**; pinned m = 5 gives 0.9729; constant-median baseline 0.085; RandomForest on summary statistics 0.732. In-sample 0.9739 versus cross-validated: a two-parameter physical model cannot overfit.

## 4. Rail corrugation · 3-class classification

- **Data**: 272 one-second recordings at 10000 Hz, 64 axle boxes × (vibration, shock); classes {'Normal': 234, 'Side I': 14, 'Side II': 24}. Positions 1,3,5,7 = Side I, 2,4,6,8 = Side II.
- **Features**: ported per-side statistics and spectral bands + measured speed from the 90-tooth pulse; speed from the 90-tooth pulse and 0.85 m wheel.
- **Model**: rail-v2: v2 = rf_0.7_leaf3 on base features, adopted by scripts/model_search.py (artifacts/benchmark.json). Objective Gini impurity with balanced class weights (macro F1 gives the 14 Side I files a third of the score); side-swap augmentation inside training folds only.
- **Split / leakage**: 5 stratified grouped folds over 272 files (original fold ids), side-swap augmentation inside training folds; candidate chosen by 5x3 repeated grouped CV; nested estimate of the search reported alongside.
- **Result**: macro F1 **0.8290 ± 0.0594** on the original folds (pooled 0.8193); per class {'Normal': 0.9717, 'Side I': 0.7143, 'Side II': 0.7719}; Side I recall 0.71.
- **Hyperparameter search** (`benchmark.json`, pre-registered): 32 candidate × feature-set combinations under 5×3 repeated grouped CV; best rf_0.7_leaf3 0.8285 vs incumbent 0.8134; **nested estimate of the whole search 0.8034** (0.8034 ± 0.0518), the honest number.
- **Wavelength features** (λ = v/f, pre-registered): original folds 0.8151 vs 0.8193; fresh shuffles 0.8201 vs 0.8134; kept out of the model, shown on the page as the physical reading.
- **Note**: the teammate's build reported 0.8524 as the best of five candidates on these folds; re-running the selected recipe here gives the numbers above.

## 5. ACV · refrigerant-leak localisation (ranking)

- **Data**: 6 labelled cases, one test case; column order scrambled per file and parameter names differ, so parsing is by normalised name.
- **Rule** (acv-v2): primary: fraction of valid cooling readings where the car is more than 2 degC above the median of the other cars (leak episodes); tie-break: mean excess over the other cars (the v1 rule). No fitted parameters, so nothing can be tuned to the six answers.
- **Split / leakage**: leave-one-case-out over the 6 labelled cases, all eight cars of a case held out together.
- **Result**: rank decay **1.0000 ± 0.0000** (v1 mean-excess rule 0.9792; random ranking 0.5625).
- **Rule benchmark** (`benchmark.json`): peer_mean (current) 0.9792; peer_q90 0.9167; peer_hot_fraction 1.0000; excess_mean (own setpoint) 0.9792; excess_peer_mean 0.9792; z-combined (peer_mean + excess_peer_mean) 0.9792. Decision: peer_hot_fraction dominates the current rule.
- **Caveat**: six cases and six rule variants: the margins in cases 04 and 05 and in the test file are a few tenths of a percent of readings, so the top pick on the test file is unchanged from v1 (Car 01) and only lower ranks move. Treat 1.0 as an upper bound.

## 6. Assumptions stated where the documentation left a choice

- Door: `Door Data Headers.md` lists columns the CSV does not have; the file wins.
- Rail: Info Kit §4 says ~9 Side I of ~190; the labels say 14 of 272; the labels win.
- ACV: which running-mode value means cooling was read from the data (contains 'cool'); case 04 uses different parameter names, handled by aliases.
- SHM: the AW0 / AW4 load condition is not recoverable per file, so folds are by file.
- Held-out inputs: the test files already in the repository were used, as spec §2.3 describes.

## 7. How to reproduce

```
python -m pytest tests/ -q            # metrics, schema, pages, CLI
python -m scripts.build_predictions    # predictions.zip + dashboard cache
python -m scripts.model_search         # pre-registered benchmarks
python -m scripts.package_submission --team "<name>"
```
