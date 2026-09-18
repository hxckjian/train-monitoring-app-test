# NebulaX PS3 — Train Condition Monitoring — PROJECT STATE

Single source of truth. Agents read this first. Last updated 2026-09-18.

Data lives at `repo/PS3/` (cloned from
`github.com/aochinwen/NebulaX-Hackathon-ProblemStatement`, 7.6 GB total).
Spec: `repo/PS3/01_Problem_Statement_3_Specifications.md`.
Info kits: `repo/PS3/03_References/<Subsystem>/`.

---

## 1. Scoring — VERIFIED, exact, from the Info Kits

All four formulas are fully disclosed. **Nothing here is guessed.**

| Subsystem | Metric | Exact formula |
|---|---|---|
| SHM | MAPE-derived | `MAPE = mean(|true-pred| / |true|)`; `score = max(0, 1 - MAPE)` |
| ACV | linear rank-decay | per file `score = (n - (r - 1)) / n`, `r` = rank of true faulty car, `n` = cars ranked; unranked/missing = 0; averaged over files |
| Rail | macro F1 | unweighted mean of per-class F1 over Normal / Side I / Side II |
| Door | IoU-weighted F1 | see 1.1 |

### 1.1 Door IoU-weighted F1 — the full rule

- A prediction may only match a true segment with the **same label**. Wrong label = cannot
  match at all.
- `intersection = max(0, min(true_end,pred_end) - max(true_start,pred_start))`;
  `union = (true_end-true_start) + (pred_end-pred_start) - intersection`;
  `IoU = intersection/union` (0 if union <= 0). Candidate requires IoU > 0.
- Matching is **one-to-one, greedy by highest IoU first**.
- Credit per match is **the IoU value itself**, not 1.
- `soft_recall = sum(IoU) / n_true`; `soft_precision = sum(IoU) / n_predicted`;
  `score = harmonic mean` (0 if both 0).

Consequences that drive design:
- A wrong label costs **twice**: a miss *and* a false positive.
- Over-segmenting is penalised — `n_predicted` is the precision denominator.
- Boundary sloppiness bleeds score continuously; it does not fall off a cliff.

### 1.2 The two combined scores

- **Overall Score** — sum across all 4 subsystems / 4, always. Attempting more can only raise it.
- **Average Score** — sum / number attempted. A weak subsystem *drags this down*.

These pull in opposite directions. Decide which is being optimised. Attempting all four is
strictly correct for Overall and is the stated plan.

### 1.3 Baselines worth knowing

- **ACV random ranking scores 0.5625** (mean of `(8-(r-1))/8` over r=1..8). The achievable
  gain over random is only ~0.44, but it is cheap to get.
- **Rail "always Normal" scores macro F1 ~0.33** despite ~85-90% accuracy.
- **SHM constant guess floors at 0** (Info Kit worked example: ~108% MAPE).

---

## 2. The data — VERIFIED by direct inspection

### 2.1 SHM  (`repo/PS3/02_Datasets/SHM/`, 502 MB, 81 files)

- `Train/train01.csv` … `train64.csv` (64), `Test/test01.csv` … `test16.csv` (16).
- `Train_Labels.csv`: columns `filename`, `damage`. Example `train01.csv,0.103662995`.
- **Files have NO HEADER and exactly ONE column** — a bare stress value per line.
  `train01.csv` = **581,120 rows**. Read with `header=None`.
- File numbers are **randomly assigned**; they carry no order and no damage information.
- Two lines, two load conditions **AW0 and AW4**. All samples healthy.
- **The labels were produced by rainflow counting + Miner's rule** — stated outright in the
  Info Kit §1.3. Recovering `(m, C)` is fitting the label-generating process, not guessing.

### 2.2 Door  (`repo/PS3/02_Datasets/Door/`, 1.6 MB, 3 files)

- `Train.csv` **18,037 rows**, `Test.csv` **6,254 rows**, `Train_Segments_Answer.csv`.
- `Train_Segments_Answer.csv`: **110 segments — 80 Normal, 30 Abnormal resistance.**
  Columns `segment_id,start_time,end_time,operation,status,n_rows`.
  `operation` (Open/Close) is informational and **is not predicted**.
- **17 columns, exact header string:**
  `Datetime,Motor current(mA),Motor Voltage(10mV),Motor electrodynamic force,Door opening time(.1s),Door closing time(.1s),Close command,Open command,DCSR,DCSL,DLSR,DLSL,Door Opened,Door Locked,Door is opening,Door is closing,Door leaf position`
- **Timestamps are NOT zero-padded**: `2023-7-5-0-0-0-0`,
  `Year-Month-Day-Hour-Minute-Second-Millisecond`. Parse with an explicit format.
- **DISCREPANCY**: `Door Data Headers.md` lists `Car Type`, `Car Number`, `Door Number` and
  calls the EMF column "Motor back electromotive force". The actual CSV has neither the three
  ID columns nor that spelling. **The file wins.**
- Submission has **no `file_id`** — `start_time,end_time,prediction`, one row per predicted
  segment. Label strings exactly `Normal` / `Abnormal resistance`.

**Segmentation is SOLVED — verified by `scripts/eda_door.py`:**

- Rows exist **only while a cycle is in progress**. The 110 answer segments account for
  **100%** of the 18,036 training rows (`sum(n_rows) == len(Train.csv)`).
- Within a cycle the interval is **exactly 0.020 s** (17,926 of 18,035 gaps). Between cycles
  the gap is **≥ 10.215 s**. Separation ratio **510×**.
- **Any gap threshold from 0.05 s to 5 s recovers exactly 110 segments.** This is a wide safe
  band, not a tuned constant. `train.py` derives it per run (0.452 s) without ever looking at
  the answer file.
- Segment boundaries are exactly the first and last row timestamps, so **IoU is 1.0** on every
  matched segment. The Door score therefore reduces to per-cycle classification accuracy.
- Test.csv yields **38 segments** at every threshold in the same band.
- `Door Locked` is **constant** across the whole stream — carries no information.
- Class signal: abnormal cycles average **719.8 mA** sustained current vs **537.5 mA** normal.
  `cur_max` is slightly *lower* for abnormal (2255 vs 2324) — it is sustained load, not inrush.
- Operation split is 55 Open / 55 Close.

**Result: IoU-weighted F1 = 0.9909 ± 0.0182** on 5 contiguous time blocks (always-Normal
reference 0.7273). One misclassification in 110 cycles. See `subsystems/door/README.md`.

### 2.3 Rail Corrugation  (`repo/PS3/02_Datasets/Rail_Corrugation/`, 5.5 GB, 341 files)

- `Train/Train1.csv` … `Train272.csv`, `Test/Test1.csv` … `Test68.csv`, `Train_Labels.csv`
  (`filename`, `label`).
- **Label counts verified: 234 Normal, 14 Side I, 24 Side II.**
- **Files have a header row**, 10,001 lines = header + **10,000 samples**, **129 columns**,
  1 second at **10 kHz**, units m/s².
- Column 1 `Rotating speed`. Columns 2-129 are named, not positional:
  `Vibration of bearing in position P of car C` / `Shock of bearing in position P of car C`,
  for C = 1..8, P = 1..8 — **64 axle boxes x 2 channels**.
- **Positions 1,3,5,7 = Side I rail; positions 2,4,6,8 = Side II rail.**
- Speed is derivable exactly: toothed wheel, **90 teeth**, **wheel diameter 0.85 m**, speed
  from counting 0/1 transitions.
- **CONTRADICTION IN THE SPEC**: Info Kit §2.2 says 14 Side I / 234 Normal (matches the data);
  Info Kit §4 says "~9 Side I against ~190 Normal". §2.2 and the actual labels win.

### 2.4 ACV  (`repo/PS3/02_Datasets/ACV/`, 43 MB, 8 files)

- `Train/acv_case_01.xlsx` … `acv_case_06.xlsx` (6), `Test/acv_test_case.xlsx` (1).
- `Train_Labels.csv`: `filename,faulty_car` →
  `01, 02, 03, 01, 04, 06` for cases 01-06. **Car `01` is the answer twice.**
- All three files inspected have **67 columns**: 3 id columns
  (`Car model`, `Train number`, `Time`) + 8 cars x 8 parameters. Sampled every 30 s.
- **Per-car column order IS scrambled — VERIFIED.** Car-id run length is 59 for
  `acv_case_01` and the test file, 58 for `acv_case_05`, versus 8 if grouped by car.
  The test file's scramble is *identical* to `acv_case_01`'s; `acv_case_05` differs.
  **Parse by column name. Never by position.**
- **Parameter NAMES differ between files — VERIFIED.** `acv_case_05` has
  `Outside Temperature Sensor Reading` where cases 01 and the test file have
  `Outdoor Average Temperature`. A name-normalisation layer is required, not optional.
- Column pattern `Car <NN> - <parameter>`; `ranked_cars` must use the bare two-digit id
  (`03`, not `Car 3`), pipe-separated, **every car listed** (omission scores 0).
- Info Kit claims one file carries 60+ parameters per car. **Not yet found** — cases 02, 03,
  04, 06 not yet inspected. Open.

---

## 3. Deliverables — RESOLVED

Compulsory (spec §4.1): **demo video ≤3 min**, **`predictions.zip`**, **the app**.

- The four Info Kits each still demand a `predict.py` with an `--input`/`--output` CLI.
  **The top-level spec §4.1 supersedes them** — it lists only the three items above, states
  that "how you produced them is not separately re-checked", and puts development code and
  models under *Optional* §4.2. The top-level `README.md` does not require `predict.py`.
  Build the app; ship `predict.py` only as optional evidence.
- `predictions.zip`: `*_predictions.csv` at the **top level, no subfolders**.
- Held-out **test inputs are distributed before the deadline** and are already in the repo —
  predictions can be generated now.
- Scored by `judge_leaderboard.py`, which is **not in the repo**. Our local scorer is a
  reimplementation from the disclosed formulas, not the judge's code.

---

## 4. Method per subsystem

- **SHM** — rainflow + Miner, fit `(m, C)`. **MAPE is relative, so fit in log-space / minimise
  relative error**, never least squares on raw damage: small-damage files dominate the metric.
  `(m, C)` fitted inside each fold only. Group folds by load condition (AW0/AW4) if it can be
  inferred, since it plausibly changes the constants.
- **Door** — segment on what actually changes at a boundary (the Info Kit explicitly warns
  against assuming the opening/closing flags are the robust signal). Then classify each cycle.
  Tune the operating point against the real metric, not accuracy — a wrong label is a double
  penalty and an extra segment is not free.
- **Rail** — per-side features. Corrugation wavelength is physical: **λ = v / f**, so convert
  the spectrum to the wavelength domain using the measured rotating speed and look for energy
  in the few-cm to tens-of-cm band. Speed normalisation is the main lever most teams will skip.
  Class-weighted model, stratified repeated CV grouped by file.
- **ACV** — deterministic ranking on indoor-temperature drift from the cooling setpoint while
  in cooling mode, relative to the other 7 cars. Leave-one-case-out over the 6 cases.
  **Watch the prior**: faulty cars in train are 01,02,03,01,04,06 — low-numbered. Any rule that
  benefits from that bias is fitting the answer file.

---

## 5. Rules

1. **Tests before models.** `scoring/metrics.py` implements all four formulas; `tests/` checks
   each against the Info Kit worked examples. A number not produced by this code does not ship.
2. **Leakage discipline** — spec §3.2 makes it a *scored* criterion: "a high score achieved
   through a leaky split will not score well". Door = contiguous time blocks. Rail = stratified
   repeated CV grouped by file. ACV = leave-one-case-out. SHM = constants fitted in-fold.
3. **Pre-register** the measure, split and success criteria before computing a score.
4. **Never type a number** — every figure regenerates from data.
5. **Parse by column name, explicit timestamp formats, no header assumptions.**

---

## 6. Open questions

- Hackathon length and team size — still unanswered. Decides Streamlit vs Next.js (2-3x build
  time). **Blocking the app decision.**
- ACV cases 02, 03, 04, 06 column sets not yet inspected (the 60+ parameter file).
- Whether AW0/AW4 load condition is recoverable per SHM file.
- Rail: 5.5 GB means a local batch mode is required regardless of app framework.
