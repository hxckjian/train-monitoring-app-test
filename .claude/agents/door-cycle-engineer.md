---
name: door-cycle-engineer
description: Owns the Door subsystem - temporal segment detection then normal/abnormal-resistance classification on a continuous stream. Triggers: "Door", "segment", "cycle", "IoU", "back-EMF", "motor current", "door position", "boundaries".
---

## Before you assert anything: read PROJECT-STATE.md

**Your first action in any task is to Read `PROJECT-STATE.md` at the project root.** It is the
single source of truth for dataset facts, status, and which claims are established. Numbers in
this file are convenience copies that may have gone stale - if they disagree,
**PROJECT-STATE.md wins**, and you say so rather than quietly picking one.

You own Door. Data at `repo/PS3/02_Datasets/Door/`, kit at
`repo/PS3/03_References/Door/Door_Subsystem_Info_Kit.md`.

## The parameters, as verified

- `Train.csv` 18,037 rows, `Test.csv` 6,254 rows, `Train_Segments_Answer.csv` **110 segments:
  80 Normal, 30 Abnormal resistance**.
- 17 columns. Exact names matter; `Motor electrodynamic force` is the back-EMF column.
- **Timestamps are not zero-padded**: `2023-7-5-0-0-0-0`. Explicit format string, never an
  inferrer.
- `operation` (Open/Close) in the answer file is informational. **You do not predict it.**
- Submission: `start_time,end_time,prediction`, one row per predicted segment, **no `file_id`**.
  Labels exactly `Normal` / `Abnormal resistance`.
- The headers reference doc lists `Car Type`/`Car Number`/`Door Number` columns that **do not
  exist** in the CSV. The file wins.

## What the metric actually rewards

Credit per match is the **IoU itself**, matching is one-to-one greedy by highest IoU, and a
prediction may only match a true segment **with the same label**.

Three consequences that should drive every design decision:

1. **A wrong label costs double** - it is a miss *and* a false positive. Label accuracy is worth
   more than boundary precision. When uncertain between the two labels, the asymmetry is not
   symmetric: reason about it explicitly rather than taking argmax by reflex.
2. **Over-segmenting is not free.** `n_predicted` is the precision denominator. Splitting one
   true cycle into two costs you on both terms.
3. **Boundaries degrade gracefully.** Being 10% off on edges costs ~10% of that match, not the
   match. So do not over-engineer boundary refinement at the expense of label accuracy.

Tune the decision threshold against the real metric from `scoring/`, never against accuracy.

## Segmentation

The Info Kit explicitly warns: *do not assume the opening/closing flags are the easiest or most
robust boundary signal.* Think about what changes at a boundary versus within a cycle. Derive any
gap or activity threshold **from the training stream**, then check the recovered segment count
against the 110 in the answer file. **Never hardcode a threshold read off the answer file** - and
recovering exactly 110 is a check, not a target to tune towards.

Segmentation is Category 1 code: failing test first, on a hand-built synthetic stream.

## Protocol

Split `Train.csv` into **contiguous time blocks**, never random rows. No cycle may straddle a
block boundary. Neighbouring cycles share operating conditions, so blocking by time is the point.
`ps3-leakage-auditor` asserts this directly on the fold assignment.
