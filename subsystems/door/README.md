# Subsystem

- **Name:** Door — abnormal opening/closing resistance detection
- **Automatically chosen slug:** `door`
- **Owner:** _to be filled in by the team member_

# Task

Given one continuous, unlabelled door-controller stream, **find each
open/close cycle within it and classify that cycle** as `Normal` or
`Abnormal resistance`.

This is temporal segment detection followed by binary classification. The
prediction unit is **one row per detected segment** — not one row per file.
There is no `file_id` column, because the held-out test set is a single
continuous stream with no per-file structure to key on.

`operation` (Open/Close) appears in the training answer file but is
informational; it is **not** predicted. It is used as an input feature only.

# Input

- **Accepted file types:** `.csv`
- **Expected number of files:** normally one. `predict()` accepts a list; each
  file is segmented independently and results are concatenated, sorted by start
  time.
- **Required columns:** all 17 of the Door schema, by exact name —
  `Datetime`, `Motor current(mA)`, `Motor Voltage(10mV)`,
  `Motor electrodynamic force`, `Door opening time(.1s)`,
  `Door closing time(.1s)`, `Close command`, `Open command`, `DCSR`, `DCSL`,
  `DLSR`, `DLSL`, `Door Opened`, `Door Locked`, `Door is opening`,
  `Door is closing`, `Door leaf position`.
- **Important assumptions:**
  - Timestamps are `Year-Month-Day-Hour-Minute-Second-Millisecond`,
    hyphen-separated and **not zero-padded** (`2023-7-5-0-0-3-760`). Parsed with
    an explicit splitter — a generic datetime inferrer silently disagrees
    between rows on this format.
  - The controller writes rows **only while a cycle is in progress**. Verified:
    the 110 answer segments account for 100% of the 18,036 training rows.
  - Sampling inside a cycle is 0.020 s.
- **How uploaded files are interpreted:** as a raw continuous stream. No
  pre-processing by the user is required or expected.

> Note: `03_References/Door/Door Data Headers.md` also lists `Car Type`,
> `Car Number` and `Door Number`, and calls the EMF column "Motor back
> electromotive force". **Those columns do not exist in the CSV** and the
> spelling differs. The file is authoritative; the code follows the file.

# Data processing

**Cleaning** — parse timestamps explicitly, sort by time, drop exact duplicate
timestamps. The constant `Door Locked` column is deliberately *kept* in the
schema check (so validation stays a real check) and simply not used as a
feature.

**Segmentation** — cut the stream wherever the gap between consecutive rows
exceeds a threshold. The threshold is **derived from the data, not chosen**:
the sorted inter-row gaps are strongly bimodal, so `train.py` takes the largest
multiplicative jump and puts the threshold at the geometric mean of that pair.
On the training stream that gives:

```
largest within-cycle gap   : 0.0200 s
smallest between-cycle gap : 10.2150 s
separation ratio           : 510.8x
threshold chosen           : 0.4520 s
segments found: 110   answer file: 110   MATCH
```

Any threshold between roughly 0.05 s and 5 s recovers the same 110 segments, so
this is a wide safe band rather than a tuned constant. The threshold never looks
at the answer file, so it transfers to an unseen stream.

**Feature engineering** — 27 aggregates per cycle, in a fixed saved column
order. The physically meaningful ones, which are also the ones the model
actually uses:

| Feature | Why |
|---|---|
| `cur_mean_mid` | mean current over the middle 60% of the cycle, excluding motor inrush and the stop ramp — the sustained load a resistance fault raises |
| `cur_integral` | total charge moved, mA·s at 20 ms sampling |
| `cur_per_emf` | current per unit back-EMF; back-EMF tracks motor speed, so this is a torque-per-speed proxy |
| `cur_per_volt` | current drawn per unit supply voltage |

**Learned preprocessing artifacts:** the gap threshold and the feature column
order are both saved in `artifacts/config.json` and asserted at inference time.
Nothing is recomputed from uploaded test data.

# Validation

- **Split method:** 5 **contiguous time blocks** over the ordered cycle
  sequence. No shuffling.
- **Grouping unit:** the door cycle. No cycle is ever split across a boundary.
- **Why it prevents leakage:** Door is one continuous recording of one door.
  Neighbouring cycles share operating conditions, wear state and ambient
  conditions, so a random row or random cycle split would place a cycle's near
  twin in training and report a flattering number. Contiguous blocks are the
  closest honest analogue of "a different stretch of running".
- **Official metric:** IoU-weighted F1, implemented in `scoring/metrics.py` from
  `Door_Subsystem_Info_Kit.md` Section 4 and unit-tested against hand-worked
  examples in `tests/test_metrics.py`.
- **Validation score:** **IoU-weighted F1 = 0.9909 ± 0.0182** (mean ± sd across
  the 5 blocks; per-fold 0.9545, 1.0, 1.0, 1.0, 1.0).
  Cycle accuracy 0.9909. **Always-Normal reference: 0.7273.**

The metric is evaluated on the **whole pipeline** per fold — segment, featurise,
classify, score — not on the classifier in isolation.

# Model

- **Model type:** `RandomForestClassifier`, 400 trees, `min_samples_leaf=2`,
  `class_weight="balanced_subsample"`.
- **Fixed random seed:** `20260918`.
- **Main features:** sustained mid-cycle current, current integral,
  current-per-back-EMF, current-per-volt (top four by importance, together ~60%).
- **Why suitable for the MVP:** the class signal is a clean scalar separation
  (abnormal cycles average 720 mA sustained versus 537 mA), 110 training
  examples is far too few to justify anything larger, and a forest gives usable
  feature importances for the app's explanation panel at no extra cost.

Deliberately **not** tuned. The MVP brief says baseline first, and the
validation score leaves almost no headroom to tune into.

# Artifacts

| Artifact | Why inference needs it |
|---|---|
| `artifacts/model.joblib` | the trained classifier |
| `artifacts/config.json` | the derived gap threshold, the exact feature column order (asserted at load, so a silent reorder cannot produce a confident wrong answer), the allowed labels, and the recorded validation result |

# Training

From the project root:

```bash
python -m subsystems.door.train
```

Optional: `--data-dir <path>` if the dataset is not at
`repo/PS3/02_Datasets/Door`.

# Prediction interface

```python
from io import BytesIO
from pathlib import Path
from subsystems.door.predict import predict

path = Path("repo/PS3/02_Datasets/Door/Test.csv")
uploaded_file = BytesIO(path.read_bytes())
uploaded_file.name = path.name          # keep the .csv extension

result = predict([uploaded_file])
result.to_csv("door_predictions.csv", index=False)
```

`predict()` always takes a **list**, returns a `pandas.DataFrame`, never
retrains, contains no Streamlit code, and holds no personal absolute paths.

# Smoke test

From the project root:

```bash
python -m subsystems.door.tests.smoke_test
```

# Output

- **Columns, in this exact order:** `start_time`, `end_time`, `prediction`
- **Valid labels:** `Normal`, `Abnormal resistance` (exact spelling and case)
- **Timestamp format:** the dataset's native unpadded
  `Y-M-D-H-M-S-ms`, matching `04_Example_Submission/door_predictions.csv`
  byte-for-byte in shape
- **Rows:** one per detected cycle (38 on the provided `Test.csv`)

```csv
start_time,end_time,prediction
2023-7-5-0-0-0-0,2023-7-5-0-0-3-760,Normal
2023-7-5-0-0-15-5,2023-7-5-0-0-18-765,Normal
2023-7-5-0-1-2-40,2023-7-5-0-1-4-840,Normal
```

# Dependencies

No subsystem-specific packages beyond the project baseline: `pandas`, `numpy`,
`scikit-learn`, `joblib`. No Excel support needed for Door.

# Known limitations

1. **0.9909 is suspiciously high, and should be read carefully.** The signal is
   genuinely strong and physical, and the split is honest — but this is one
   door, one recording. A held-out stream from a different door or a different
   wear state could be materially harder. The Info Kit itself warns that
   distributions differ between doors. Treat this as an upper bound.
2. **One misclassification total**, in fold 1. With 30 abnormal cycles, a single
   error moves the score by about 0.009, so the ±0.018 spread is one event wide
   — it is not a precise estimate of anything.
3. **Segmentation assumes rows exist only during cycles.** This is verified on
   both provided streams, but a held-out stream that also records idle time
   would break the gap rule. The threshold is derived per run, which mitigates
   this, but does not fix a genuinely different recording regime.
4. **Multi-file uploads are concatenated**, not merged. Since the schema has no
   `file_id`, uploading two overlapping streams would produce ambiguous rows.
   The intended use is one stream.
5. Only two labels are supported, matching the data. A third class would need
   retraining, not a config change.

# Handoff summary

**Files created**

```
scoring/metrics.py                       all four official metrics
tests/test_metrics.py                    28 tests, incl. every Info Kit example
scripts/eda_door.py                      reproducible EDA
subsystems/door/__init__.py
subsystems/door/features.py              shared by train and predict
subsystems/door/train.py
subsystems/door/predict.py               public predict(uploaded_files)
subsystems/door/expected_output.csv
subsystems/door/README.md                this file
subsystems/door/tests/__init__.py
subsystems/door/tests/smoke_test.py
subsystems/door/artifacts/model.joblib
subsystems/door/artifacts/config.json
predictions/door_predictions.csv         38 rows, generated from Test.csv
```

**Artifacts created:** `model.joblib`, `config.json`.

**Validation result:** IoU-weighted F1 `0.9909 ± 0.0182`, 5 contiguous time
blocks. Always-Normal reference `0.7273`.

**Smoke-test status:** 15/15 checks pass.

**Assumptions:** listed under *Input* and *Known limitations* above. The two
that matter: rows exist only during cycles, and the gap threshold is derived per
run rather than hardcoded.

**Remaining issues for the team leader:**

1. `predictions/door_predictions.csv` was generated by calling `predict()`
   directly. The spec requires the final submission to be produced **through the
   app**. Regenerate it via the Streamlit app before packaging `predictions.zip`.
2. The organisers score with `judge_leaderboard.py`, which is **not** in the
   repository. `scoring/metrics.py` is our reimplementation from the disclosed
   formulas, checked against the published worked examples — close, but not the
   judge's own code.
3. Confirm whether the held-out Door test input distributed before the deadline
   is the same `Test.csv` already in the repo, or a new stream.
