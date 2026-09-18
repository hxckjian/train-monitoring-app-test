# HANDOFF — read this first if you are a new session

NebulaX Problem Statement 3, Train Condition Monitoring. This file exists so a
dead token budget, a crashed machine or a fresh chat costs minutes, not hours.

**Read in this order:**

1. This file — status, what is done, what is next.
2. `PROJECT-STATE.md` — the verified facts. **Single source of truth.** Anything
   that disagrees with it is wrong, including this file.
3. `.claude/agents/*.md` — 8 agent definitions, one per subsystem plus three
   discipline agents.
4. The subsystem README you are working on, e.g. `subsystems/door/README.md`.

**Environment:** conda env `nebula-ps3` (isolated; the FYP env `ungt` is
separate and must not be touched). Run everything as:

```bash
conda run -n nebula-ps3 --no-capture-output python <script>
```

---

## 1. Status at a glance — 2026-09-18

| Piece | State |
|---|---|
| Dataset cloned | DONE — `repo/`, 7.6 GB, gitignored |
| Isolated conda env | DONE — `nebula-ps3` + Jupyter kernel |
| All four scoring formulas | DONE — `scoring/metrics.py`, 28 tests pass |
| **Door subsystem** | **DONE** — IoU-weighted F1 0.9909 ± 0.0182, smoke test 15/15 |
| SHM | Rainflow cached; **S-N fit script written but NOT yet run to completion** |
| Rail | Not started |
| ACV | Schema fully profiled; no model yet |
| Streamlit app | Not started |
| Design system | Published |
| Review of teammate's build | DONE — findings in section 6 |

---

## 2. The team situation

Three people, three different AI assistants, helping each other.

- **This folder is the Door owner's workspace.** Door is finished.
- A teammate has a **separate, complete 4-subsystem build** at
  `C:\Users\Asus\Desktop\Everything in one\k84mjMhEcw8uQKbN-grok-workspace`
  (TanStack/React/Vercel app + one Python training script). It produces a valid
  `predictions.zip` for all four subsystems. **Reviewed in section 6 — it has
  real coverage but no validation split anywhere and two concrete bugs.**
- **Four subsystems, three people.** Overall Score divides by 4 *always*, so an
  unowned subsystem is a guaranteed zero on 25% of it. Coverage beats polish.

`scoring/metrics.py` should be shared with both teammates so all three optimise
against the same numbers.

---

## 3. Rebuild from nothing

```bash
conda env create -f environment.yml
conda activate nebula-ps3
python -m ipykernel install --user --name nebula-ps3 --display-name "Python (nebula-ps3)"

git clone --depth 1 https://github.com/aochinwen/NebulaX-Hackathon-ProblemStatement.git repo

python -m pytest tests/ -q                       # expect 28 passed
python -m subsystems.door.train                  # expect 0.9909 +/- 0.0182
python -m subsystems.door.tests.smoke_test       # expect 15/15 PASS
```

If all three pass, the project is fully restored.

---

## 4. What is DONE — details

### 4.1 Scoring — `scoring/metrics.py`, `tests/test_metrics.py`

All four official formulas, transcribed from the Info Kits (**not guessed** —
every formula is disclosed with a worked example). 28 tests pass, including
every published worked example.

- `shm_score(y_true, y_pred)` → `max(0, 1 - MAPE)`
- `acv_case_score(ranked, true)` / `acv_score(...)` → `(n - (r-1))/n`
- `macro_f1(y_true, y_pred)` → unweighted mean per-class F1
- `door_iou_weighted_f1(true_segs, pred_segs)` → greedy one-to-one by IoU

Baselines worth knowing, all unit-tested:
- **ACV random ranking already scores 0.5625.** Total headroom is only ~0.44.
- **Rail always-Normal scores ~0.33** macro F1 at 85–90% accuracy.
- SHM constant guess floors at 0.

`judge_leaderboard.py` is **not** in the repo. This is our reimplementation.

### 4.2 Door — COMPLETE, `subsystems/door/`

**Result: IoU-weighted F1 = 0.9909 ± 0.0182**, 5 contiguous time blocks.
Always-Normal reference 0.7273. One misclassification in 110 cycles.

Segmentation is *solved*, verified by `scripts/eda_door.py`:
- Rows exist **only during cycles** — the 110 answer segments cover 100% of the
  18,036 training rows.
- Interval inside a cycle is exactly **0.020 s**; between cycles **≥ 10.215 s**.
  A **510× separation**.
- **Any gap threshold from 0.05 s to 5 s recovers exactly 110 segments.**
  `train.py` derives it per run (0.452 s) from the largest multiplicative jump
  in sorted gaps — it never reads the answer file.
- Boundaries are exactly first/last row timestamps, so IoU = 1.0 on matches.
  **The Door score therefore reduces to per-cycle classification accuracy.**
- Test.csv → 38 segments. `Door Locked` is constant, carries no information.

Classifier: RandomForest, 400 trees, seed 20260918. Top features are the
resistance physics — `cur_mean_mid` (sustained current excluding inrush),
`cur_integral`, `cur_per_emf`, `cur_per_volt`. Abnormal cycles draw 720 mA
sustained vs 537 mA; `cur_max` is *lower* for abnormal, so it is sustained load
not inrush.

Interface: `from subsystems.door.predict import predict; predict([uploaded_file])`
→ DataFrame(38, 3). Output at `predictions/door_predictions.csv`.

**Caveat to keep honest:** 0.9909 is one door, one recording. Treat as an upper
bound; a different door could be materially harder.

### 4.3 SHM — PARTIALLY DONE

**Done:** `scripts/shm_rainflow_cache.py` has rainflow-counted all 80 files and
cached them to `artifacts_cache/shm_{train,test}_cycles.npz` (~95 s total).

The cache is **gitignored** (large binaries). It exists on the original machine;
on a fresh clone regenerate it once with
`conda run -n nebula-ps3 --no-capture-output python scripts/shm_rainflow_cache.py`
and then never again — the fitting step reads only the cache.

Verified facts:
- 581,120 samples per file, **identical across all files**. No header, one column.
- 158,616–183,968 rainflow cycles per file. Stress range [-61.63, 60.20].
- **Train damage: min 0.0286, max 0.9283, 32.4× spread.** Quartiles 0.046 /
  0.099 / 0.388.

**NOT done:** `scripts/shm_fit_sn.py` was written but has **not completed a
run** — it was still executing when the session ended. Run it:

```bash
conda run -n nebula-ps3 --no-capture-output python scripts/shm_fit_sn.py
```

If it is too slow, the bottleneck is `log_S` recomputing a logsumexp over
~170k cycles for every m in the grid. Fix by pre-binning cycle ranges into a
histogram per file once, then the m-sweep is trivial.

**The method, and why it should work:** the Info Kit states outright that the
reference damage values were produced by rainflow + Miner. So

```
D = sum(n_i / N_i),  N_i = C / sigma_i^m   =>   D = (1/C) * sum(n_i * sigma_i^m)
```

For a fixed m the whole model is **one scalar**: `D = S(m)/C`. Fit by a 1-D
search over m with log C in closed form. Two parameters, not a regression.

Two traps already handled in the script:
- **MAPE is relative**, so fit in log space. Least squares chases large-damage
  files and wrecks the small ones, which dominate the metric.
- `(range/2)^m = range^m / 2^m`, so the amplitude-vs-range convention folds
  entirely into C and does not matter.
- Constants must be fitted **inside each CV fold**.

### 4.4 ACV — schema fully profiled, no model yet

Verified by direct inspection of all 7 files:

| file | cols | params/car | rows |
|---|---|---|---|
| acv_case_01/02/03/05/06 | 67 | 8 | 3,263–9,187 |
| **acv_case_04** | **483** | **63** | **22,262** |
| acv_test_case | 67 | 8 | 9,082 |

- **`acv_case_04` is the 60+ parameter file** the Info Kit mentions. Confirmed.
- **Only ONE parameter name is common to all seven files.** Union is 71.
- `acv_case_04` has **no `Indoor Average Temperature`** — it uses
  `Passenger Cabin Temperature Detected Value` and `Target Temperature Value`.
- `acv_case_05` and `06` use `Outside Temperature Sensor Reading` where the
  others use `Outdoor Average Temperature`.
- **Per-car column order is scrambled**, and differently per file. Car-id run
  length is 59 for case 01 and the test file (identical scramble), 58 for case 05.
- Test file sheet name is Chinese ("Fault case 3"), not `Sheet1`.
- Labels: `01, 02, 03, 01, 04, 06`. **The prior is poisoned** — low-numbered,
  with `01` twice. Any rule benefiting from car number is fitting the answers.

A name-normalisation layer is **mandatory**, not optional.

### 4.5 Design system — published

https://claude.ai/artifact/6z5wNhj37WvB6ufe1RPeFG

Tokens, status language, chart rules, six components (StatusChip, VerdictCard,
DamageGauge, DoorTimeline, AxleGrid, CarRank). Source in `design-system/`.

Palettes validated computationally for colour-vision deficiency in both themes.
The finding that changed the design: a green/amber/**orange** traffic light
separates by only ΔE 1.2 under simulated CVD (8.4 even in full colour) — so the
alert colour is a **true red**, lifting the worst pair to 20.8.

---

## 5. Rules this project runs on

Two of these are **scored** — spec §3.2: *"a high score achieved through a leaky
split will not score well."*

1. **Tests before models.** Every number comes from `scoring/metrics.py`.
2. **Leakage discipline:** Door = contiguous time blocks. Rail = stratified
   repeated CV grouped by file. ACV = leave-one-case-out. SHM = constants fitted
   in-fold only.
3. **Pre-register** the measure, split and success criteria before computing.
   Report a null as null.
4. **Never type a number.** Everything regenerates from data.
5. **Parse by column name.** Explicit timestamp formats. No positional indexing.

---

## 6. Review of the teammate's grok-workspace build

Path: `C:\Users\Asus\Desktop\Everything in one\k84mjMhEcw8uQKbN-grok-workspace`
Training script: `ps3/train_all.py` (678 lines). Params: `src/lib/models/params.json`.

**Genuinely good:** complete 4/4 coverage with correct schemas and row counts
(16/68/1/38), valid `predictions.zip` with no subfolders. SHM computes rainflow
and Σn·ampᵐ (right idea). Rail groups odd/even by side correctly. ACV parses by
regex on column name. Door `gap_ms=200` sits safely inside the verified band.

**Systemic problem: no validation split anywhere.** Every number is in-sample.

| Reported | What it actually is |
|---|---|
| Door `train_iou_f1: 1.0` | threshold = `(max_normal + min_abnormal)/2`, fitted to the extreme order statistics of the labels. Returns 1.0 by construction if classes separate |
| Rail `train_macro_f1: 0.686` | the **maximum** of a 441-point threshold sweep over full train — a selected max, not an estimate |
| SHM `train_mape: 0.163` | in-sample ridge on 12 features |
| ACV rank-decay | in-sample; weights `2.0 / 0.5 / 0.15` hand-tuned against 6 known answers |

**Bug 1 — ACV case 04 silently scores zero for every car.** No
`Indoor Average Temperature` column, so `series()` returns `None`, every car
gets `0.0`, and the tie-break falls to numerical order `01,02,...`. The true
answer for case 04 *is* `01`, so it scores a **perfect 1.0 by accident**,
inflating the reported average. Their test prediction also ranks `01` first —
needs a leave-one-case-out check before anyone trusts it.

**Bug 2 — SHM decimation corrupts rainflow.** `x[::2]` runs on every file (all
581,120 > 200,000 threshold). Measured:

```
train01  cycles -49.9%   S3 -15.7%   S5 -6.7%    S7 -5.2%
train32  cycles -51.7%   S3 -15.3%   S5 -8.4%    S7 -9.7%
train64  cycles -52.1%   S3 -10.3%   S5 -10.0%   S7 -13.6%
```

Half the cycles vanish and **the bias varies between files** (−5% to −16%). A
constant bias absorbs into the intercept; a varying one is noise in the target.
Since the metric is MAPE, that is a direct floor on the score. Their SHM
predictions also reach **1.369**, above the training max of 0.928 — under
Miner's rule D ≥ 1.0 means already failed.

**Structural:** `ROOT = Path("/tmp/nebulax/...")` and `OUT = Path("/workspace/...")`
are hardcoded sandbox paths — **the script cannot run on this machine**.
`artifacts/` is empty; inference is reimplemented in TypeScript from
`params.json`, so two copies of the feature logic can drift. Their own spec
forbids that.

**Fix order by score impact:**
1. **Rail** — they predict 2 Side II where the training ratio implies ~6, and
   each class is a third of macro F1. `speed_tog` is computed then never used:
   no speed normalisation, no FFT. **λ = v/f is the lever** (90 teeth, 0.85 m
   wheel — speed is exactly computable).
2. **SHM** — drop decimation, fit (m, C) directly instead of ridge on 12 features.
3. **ACV** — fix case 04, mask to cooling mode, run leave-one-case-out.
4. **Door** — theirs is probably fine; ours disagree on 4 of 38 segments.

---

## 7. Next actions, in order

1. **Finish the SHM fit** (`scripts/shm_fit_sn.py`). Highest score-per-hour left
   — the generating process is known, it is a 2-parameter fit.
2. **Rail** — FFT band energies converted to the **wavelength** domain using
   measured speed, per side, class-weighted, stratified repeated CV grouped by
   file. This is the lever nobody else is using.
3. **ACV** — deterministic drift ranking with cooling-mode masking and a name
   normalisation layer that handles case 04; leave-one-case-out.
4. **App** — see the open question below.
5. Regenerate `predictions.zip` **through the app** before submitting.

---

## 8. Open questions

1. **Hackathon length and team size — asked three times, never answered.** It
   decides Streamlit vs Next.js (2–3× build time). The teammate has already
   built a React/Vercel app, which may settle it by default — check whether the
   team is consolidating onto that app rather than building a second one.
2. Is the held-out test input the same files already in `repo/`, or new ones
   distributed later? Spec §2.3 says they are distributed before the deadline.
3. Whether AW0/AW4 load condition is recoverable per SHM file — it would be a
   natural CV grouping variable.

---

## 9. Where things are

```
Nebula/
├── HANDOFF.md              this file
├── PROJECT-STATE.md        verified facts — source of truth
├── environment.yml         isolated conda env
├── .claude/agents/         8 agent definitions
├── scoring/metrics.py      all four official metrics  <- SHARE WITH TEAM
├── tests/test_metrics.py   28 tests
├── scripts/
│   ├── eda_door.py             reproducible Door EDA
│   ├── shm_rainflow_cache.py   DONE — cache built
│   └── shm_fit_sn.py           WRITTEN, NOT YET RUN TO COMPLETION
├── artifacts_cache/        rainflow cycles for all 80 SHM files
├── subsystems/door/        finished Door package
├── predictions/            door_predictions.csv (38 rows)
├── design-system/          source for the published design system
└── repo/                   cloned dataset — NOT in git, 7.6 GB
```

## 10. Backup

This folder is a git repository. `repo/` and environments are excluded.
Commit after any meaningful step.

```bash
git log --oneline
git status
```
