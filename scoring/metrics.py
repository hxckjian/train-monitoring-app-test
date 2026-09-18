"""Local reimplementation of the four official PS3 scoring formulas.

Every formula here is transcribed from the disclosed specification, not inferred:

  SHM   repo/PS3/03_References/SHM/SHM_Info_Kit.md                 Section 4
  ACV   repo/PS3/03_References/ACV/ACV_Subsystem_Info_Kit.md       Section 4
  Rail  repo/PS3/03_References/Rail_Corrugation/..._Info_Kit.md    Section 4
  Door  repo/PS3/03_References/Door/Door_Subsystem_Info_Kit.md     Section 4

This is OUR reimplementation. The organisers score with `judge_leaderboard.py`,
which is not in the repository, so agreement is checked against the worked
examples in the Info Kits (see tests/test_metrics.py) rather than assumed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

# ---------------------------------------------------------------- SHM -----


def shm_score(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    """max(0, 1 - MAPE), where MAPE = mean(|true - pred| / |true|).

    Info Kit Section 4. A zero true value would make the relative error
    undefined; the kit does not define that case, so we raise rather than
    silently substituting a value and reporting a number nobody can defend.
    """
    t = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    if t.shape != p.shape:
        raise ValueError(f"shape mismatch: true {t.shape} vs pred {p.shape}")
    if t.size == 0:
        raise ValueError("no values to score")
    if np.any(t == 0):
        raise ValueError(
            "true damage of exactly 0 makes MAPE undefined; the Info Kit does "
            "not define this case - resolve it explicitly before scoring"
        )
    mape = float(np.mean(np.abs(t - p) / np.abs(t)))
    return max(0.0, 1.0 - mape)


# ---------------------------------------------------------------- ACV -----


def acv_case_score(ranked_cars: Sequence[str], true_car: str) -> float:
    """(n - (r - 1)) / n for one case; 0 if the true car is not ranked.

    Info Kit Section 4. `n` is the number of cars actually ranked in that file.
    """
    ranked = list(ranked_cars)
    n = len(ranked)
    if n == 0:
        return 0.0
    if true_car not in ranked:
        return 0.0
    r = ranked.index(true_car) + 1
    return (n - (r - 1)) / n


def acv_score(rankings: Iterable[Sequence[str]], true_cars: Iterable[str]) -> float:
    """Mean of the per-case rank-decay score."""
    scores = [acv_case_score(rk, tc) for rk, tc in zip(rankings, true_cars)]
    if not scores:
        raise ValueError("no cases to score")
    return float(np.mean(scores))


# --------------------------------------------------------------- Rail -----

RAIL_CLASSES = ("Normal", "Side I", "Side II")


def macro_f1(y_true: Sequence[str], y_pred: Sequence[str],
             classes: Sequence[str] = RAIL_CLASSES) -> float:
    """Unweighted mean of per-class F1. Info Kit Section 4.

    A class never predicted and never correct contributes 0, which is the whole
    point of the metric: always-Normal scores about 0.33, not 0.9.
    """
    t = np.asarray(list(y_true))
    p = np.asarray(list(y_pred))
    if t.shape != p.shape:
        raise ValueError(f"shape mismatch: true {t.shape} vs pred {p.shape}")
    f1s = []
    for c in classes:
        tp = int(np.sum((t == c) & (p == c)))
        fp = int(np.sum((t != c) & (p == c)))
        fn = int(np.sum((t == c) & (p != c)))
        denom = 2 * tp + fp + fn
        f1s.append(0.0 if denom == 0 else 2 * tp / denom)
    return float(np.mean(f1s))


# --------------------------------------------------------------- Door -----


@dataclass(frozen=True)
class Segment:
    """A time segment with a label. start/end are floats in a common unit."""
    start: float
    end: float
    label: str


def _iou(a: Segment, b: Segment) -> float:
    """Info Kit Section 4.1 formula, verbatim."""
    intersection = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    union = (a.end - a.start) + (b.end - b.start) - intersection
    return 0.0 if union <= 0 else intersection / union


def door_iou_weighted_f1(true_segments: Sequence[Segment],
                         pred_segments: Sequence[Segment]) -> float:
    """IoU-weighted F1. Info Kit Section 4.

    Matching rules, in the kit's order:
      1. a prediction may only match a true segment with the SAME label;
      2. a pair is a candidate only if IoU > 0;
      3. matching is one-to-one, assigned greedily by highest IoU first;
      4. credit per match is the IoU value itself, not 1.

    Then soft_recall = sum(IoU)/n_true, soft_precision = sum(IoU)/n_pred, and
    the score is their harmonic mean (0 if both are 0).
    """
    n_true, n_pred = len(true_segments), len(pred_segments)
    if n_true == 0 and n_pred == 0:
        return 0.0

    candidates = []
    for i, t in enumerate(true_segments):
        for j, p in enumerate(pred_segments):
            if t.label != p.label:          # rule 1: wrong label cannot match
                continue
            v = _iou(t, p)
            if v > 0:                        # rule 2: must actually overlap
                candidates.append((v, i, j))

    # rule 3: greedy, highest IoU first. Ties broken by index so the result is
    # deterministic - two runs on the same input must give the same score.
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))

    used_true: set[int] = set()
    used_pred: set[int] = set()
    total_iou = 0.0
    for v, i, j in candidates:
        if i in used_true or j in used_pred:
            continue
        used_true.add(i)
        used_pred.add(j)
        total_iou += v                       # rule 4: credit is the IoU itself

    soft_recall = total_iou / n_true if n_true else 0.0
    soft_precision = total_iou / n_pred if n_pred else 0.0
    if soft_recall + soft_precision == 0:
        return 0.0
    return 2 * soft_recall * soft_precision / (soft_recall + soft_precision)
