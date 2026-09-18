"""Tests for the four official scoring formulas.

Each metric is checked against the worked example printed in its own Info Kit.
If one of these fails, every downstream number in the project is wrong.

Run:  python -m pytest tests/ -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scoring.metrics import (  # noqa: E402
    Segment,
    acv_case_score,
    acv_score,
    door_iou_weighted_f1,
    macro_f1,
    shm_score,
)

# ------------------------------------------------------------------ SHM ---


def test_shm_info_kit_worked_example():
    """SHM_Info_Kit.md Section 4: MAPE 15.0% -> score 0.850."""
    true = [0.10, 0.30, 0.50, 0.70, 0.90]
    pred = [0.15, 0.28, 0.55, 0.68, 0.85]
    assert shm_score(true, pred) == pytest.approx(0.850, abs=5e-4)


def test_shm_perfect_prediction_scores_one():
    true = [0.10, 0.30, 0.50]
    assert shm_score(true, true) == pytest.approx(1.0)


def test_shm_constant_guess_floors_at_zero():
    """The kit's comparison case: predicting 0.50 everywhere has ~108% MAPE."""
    true = [0.10, 0.30, 0.50, 0.70, 0.90]
    pred = [0.50] * 5
    assert shm_score(true, pred) == 0.0


def test_shm_ten_percent_error_scores_point_nine():
    # every prediction off by exactly 10% of its true value
    true = [0.2, 0.4, 0.8]
    pred = [t * 1.1 for t in true]
    assert shm_score(true, pred) == pytest.approx(0.90)


def test_shm_zero_true_value_raises_rather_than_guessing():
    with pytest.raises(ValueError, match="undefined"):
        shm_score([0.0, 0.5], [0.1, 0.5])


# ------------------------------------------------------------------ ACV ---


@pytest.mark.parametrize("rank,expected", [
    (1, 1.000), (2, 0.875), (3, 0.750), (4, 0.625), (8, 0.125),
])
def test_acv_info_kit_worked_table(rank, expected):
    """ACV_Subsystem_Info_Kit.md Section 4, the 8-car table."""
    cars = [f"{i:02d}" for i in range(1, 9)]
    true_car = cars[rank - 1]
    assert acv_case_score(cars, true_car) == pytest.approx(expected)


def test_acv_unranked_car_scores_zero():
    assert acv_case_score(["01", "02", "03"], "07") == 0.0


def test_acv_empty_ranking_scores_zero():
    assert acv_case_score([], "01") == 0.0


def test_acv_random_ranking_baseline_is_0_5625():
    """Worth knowing: a random ordering of 8 cars already averages 0.5625.

    This is the number any reported ACV score must be read against.
    """
    cars = [f"{i:02d}" for i in range(1, 9)]
    mean = sum(acv_case_score(cars, c) for c in cars) / len(cars)
    assert mean == pytest.approx(0.5625)


def test_acv_score_averages_across_cases():
    assert acv_score([["01", "02"], ["01", "02"]], ["01", "02"]) == pytest.approx(0.75)


# ----------------------------------------------------------------- Rail ---


def test_rail_always_normal_scores_about_one_third():
    """The kit's central warning: always-Normal is ~0.33 macro F1, not ~0.9."""
    true = ["Normal"] * 18 + ["Side I"] + ["Side II"]
    pred = ["Normal"] * 20
    assert macro_f1(true, pred) == pytest.approx(1 / 3, abs=0.02)


def test_rail_perfect_prediction_scores_one():
    true = ["Normal", "Side I", "Side II", "Normal"]
    assert macro_f1(true, true) == pytest.approx(1.0)


def test_rail_macro_f1_averages_per_class_unweighted():
    """Two classes perfect, one never predicted -> (1 + 1 + 0)/3."""
    true = ["Normal", "Normal", "Side I", "Side II"]
    pred = ["Normal", "Normal", "Side I", "Side I"]
    # Normal F1 = 1.0; Side I: tp=1 fp=1 fn=0 -> 2/(2+1+0)=0.667; Side II = 0
    assert macro_f1(true, pred) == pytest.approx((1.0 + 2 / 3 + 0.0) / 3)


def test_rail_class_never_present_and_never_predicted_contributes_zero():
    true = ["Normal", "Normal"]
    pred = ["Normal", "Normal"]
    # Side I and Side II both have denom 0 -> 0.0 each, by the kit's rule
    assert macro_f1(true, pred) == pytest.approx(1 / 3)


# ----------------------------------------------------------------- Door ---

N = "Normal"
A = "Abnormal resistance"


def test_door_perfect_submission_scores_one():
    true = [Segment(0, 10, N), Segment(20, 30, A)]
    assert door_iou_weighted_f1(true, list(true)) == pytest.approx(1.0)


def test_door_wrong_label_cannot_match_at_all():
    """Perfect timing, wrong label: scores exactly 0, per Section 4.1 rule 1."""
    true = [Segment(0, 10, N)]
    pred = [Segment(0, 10, A)]
    assert door_iou_weighted_f1(true, pred) == 0.0


def test_door_no_overlap_scores_zero():
    true = [Segment(0, 10, N)]
    pred = [Segment(50, 60, N)]
    assert door_iou_weighted_f1(true, pred) == 0.0


def test_door_half_overlap_hand_worked():
    """One segment, pred shifted by 5 of 10 units.

    intersection = 5, union = 10 + 10 - 5 = 15, IoU = 1/3.
    soft_recall = soft_precision = 1/3, so score = 1/3.
    """
    true = [Segment(0, 10, N)]
    pred = [Segment(5, 15, N)]
    assert door_iou_weighted_f1(true, pred) == pytest.approx(1 / 3)


def test_door_missed_segment_lowers_recall_only():
    """Two true, one found perfectly.

    sum_iou = 1. soft_recall = 1/2, soft_precision = 1/1.
    score = 2 * 0.5 * 1 / 1.5 = 2/3.
    """
    true = [Segment(0, 10, N), Segment(20, 30, N)]
    pred = [Segment(0, 10, N)]
    assert door_iou_weighted_f1(true, pred) == pytest.approx(2 / 3)


def test_door_spurious_segment_lowers_precision_only():
    """One true found perfectly, plus one invented segment.

    sum_iou = 1. soft_recall = 1/1, soft_precision = 1/2 -> 2/3.
    Over-segmenting is not free.
    """
    true = [Segment(0, 10, N)]
    pred = [Segment(0, 10, N), Segment(100, 110, N)]
    assert door_iou_weighted_f1(true, pred) == pytest.approx(2 / 3)


def test_door_matching_is_one_to_one_greedy_by_highest_iou():
    """Two predictions overlap one true segment; only the better one matches.

    pred A has IoU 1.0, pred B overlaps the same true segment. B must become a
    false positive rather than double-counting.
    """
    true = [Segment(0, 10, N)]
    pred = [Segment(0, 10, N), Segment(8, 18, N)]
    # sum_iou = 1.0 (only the exact match), recall 1.0, precision 0.5
    assert door_iou_weighted_f1(true, pred) == pytest.approx(2 / 3)


def test_door_wrong_label_costs_twice():
    """A mislabelled segment is a miss AND a false positive.

    Two true segments, both found with perfect timing, one mislabelled.
    sum_iou = 1 (only the correctly-labelled one matches).
    soft_recall = 1/2, soft_precision = 1/2 -> score 0.5, not 0.75.
    """
    true = [Segment(0, 10, N), Segment(20, 30, A)]
    pred = [Segment(0, 10, N), Segment(20, 30, N)]
    assert door_iou_weighted_f1(true, pred) == pytest.approx(0.5)


def test_door_empty_prediction_scores_zero():
    assert door_iou_weighted_f1([Segment(0, 10, N)], []) == 0.0


def test_door_is_deterministic_on_ties():
    """Equal-IoU candidates must resolve the same way every run."""
    true = [Segment(0, 10, N), Segment(0, 10, N)]
    pred = [Segment(0, 10, N), Segment(0, 10, N)]
    first = door_iou_weighted_f1(true, pred)
    for _ in range(5):
        assert door_iou_weighted_f1(true, pred) == first
