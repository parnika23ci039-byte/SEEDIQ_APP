#!/usr/bin/env python3
"""Tests for the aligned three-condition joint metric (``SeedIQ/joint_metrics.py``).

The point of these tests is that the metric REFUSES to fabricate a joint rate:
separate model test sets with no shared sample key must yield NOT EVALUABLE, and
only genuinely joined rows may be counted.

Run:
    cd SeedIQ && ../.freebuff/venv/bin/python -m pytest tests/test_joint_metrics.py -q
"""

from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from joint_metrics import (  # noqa: E402
    NOT_EVALUABLE,
    JointEvaluationError,
    align_frames,
    find_alignment_key,
    joint_success_report,
    wilson_interval,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def aligned_frames():
    """Three sources that DO share a sample key, with known per-row outcomes.

    Rows (key -> crop / yield / seed outcome):
      1: crop correct, yield within 25%, seed correct        -> SUCCESS
      2: crop wrong,   yield within 25%, seed correct        -> fail (crop)
      3: crop correct, yield outside 25%, seed correct       -> fail (yield)
      4: crop correct, yield within 25%, seed wrong          -> fail (seed)
    """
    crop = pd.DataFrame({
        "sample_id": [1, 2, 3, 4],
        "crop_pred": [7, 1, 7, 7],
        "crop_true": [7, 7, 7, 7],
    })
    yield_ = pd.DataFrame({
        "sample_id": [1, 2, 3, 4],
        "yield_pred_total": [100.0, 100.0, 100.0, 100.0],
        "yield_area_ha": [10.0, 10.0, 10.0, 10.0],
        # row 3 actual per-ha is 4.0 vs predicted 10.0 -> outside +/-25%
        "yield_true_total": [100.0, 100.0, 40.0, 100.0],
    })
    seed = pd.DataFrame({
        "sample_id": [1, 2, 3, 4],
        "seed_pred": [1, 1, 1, 0],
        "seed_true": [1, 1, 1, 1],
    })
    return {"crop": crop, "yield": yield_, "seed": seed}


def unaligned_frames():
    """The real project situation: three test sets with no shared key."""
    return {
        "crop": pd.DataFrame({"Acl": [1.0], "Bcl": [2.0], "crop_pred": [7], "crop_true": [7]}),
        "yield": pd.DataFrame({"Area_Hectares": [100.0], "yield_pred_total": [50.0],
                               "yield_area_ha": [100.0], "yield_true_total": [50.0]}),
        "seed": pd.DataFrame({"Moisture_Level": [12.0], "seed_pred": [1], "seed_true": [1]}),
    }


# --------------------------------------------------------------------------- #
# Key discovery
# --------------------------------------------------------------------------- #
def test_finds_shared_key():
    key, details = find_alignment_key(aligned_frames())
    assert key == "sample_id"
    assert details["shared_key_columns"] == ["sample_id"]


def test_reports_per_source_key_columns_when_nothing_is_shared():
    key, details = find_alignment_key(unaligned_frames())
    assert key is None
    assert "crop" in details["key_columns_found_per_source"]
    assert details["shared_key_columns"] == []


# --------------------------------------------------------------------------- #
# Alignment
# --------------------------------------------------------------------------- #
def test_unaligned_sets_are_not_evaluable():
    report = joint_success_report(unaligned_frames())
    assert report["evaluable"] is False
    assert report["status"] == NOT_EVALUABLE
    assert report["aligned_rows"] == 0
    assert report["per_source_test_rows"] == {"crop": 1, "yield": 1, "seed": 1}
    assert "share no sample identifier" in report["reason"]
    # No fabricated rate may ever appear.
    assert "rate" not in report
    assert "successes" not in report


def test_partial_key_overlap_counts_only_shared_samples():
    frames = aligned_frames()
    frames["seed"] = frames["seed"].iloc[:2].copy()  # keys 1, 2 only
    report = joint_success_report(frames)
    assert report["evaluable"] is True
    assert report["aligned_rows"] == 2
    assert report["successes"] == 1  # key 1 succeeds, key 2 fails on crop


def test_missing_required_column_is_an_error_not_a_silent_skip():
    frames = aligned_frames()
    frames["yield"] = frames["yield"].drop(columns=["yield_area_ha"])
    with pytest.raises(JointEvaluationError) as excinfo:
        align_frames(frames)
    assert "yield_area_ha" in str(excinfo.value)


def test_duplicate_key_is_rejected_not_joined_many_to_many():
    frames = aligned_frames()
    frames["crop"] = pd.concat([frames["crop"], frames["crop"].iloc[[0]]], ignore_index=True)
    with pytest.raises(JointEvaluationError) as excinfo:
        align_frames(frames)
    assert "duplicated" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# Evaluation correctness
# --------------------------------------------------------------------------- #
def test_aligned_joint_counts_and_components():
    report = joint_success_report(aligned_frames())
    assert report["evaluable"] is True
    assert report["key"] == "sample_id"
    assert report["test_rows"] == 4
    assert report["successes"] == 1
    assert report["rate"] == pytest.approx(0.25)
    assert report["component_pass_rate"]["crop"] == pytest.approx(0.75)
    assert report["component_pass_rate"]["yield_within_25pct"] == pytest.approx(0.75)
    assert report["component_pass_rate"]["seed"] == pytest.approx(0.75)
    assert report["component_failures"] == {"crop": 1, "yield": 1, "seed": 1}
    low, high = report["rate_ci95_wilson"]
    assert low < report["rate"] < high


def test_yield_tolerance_is_per_hectare():
    """Predicted 100 t over 10 ha = 10 t/ha; the boundary is actual 8 t/ha.

    Per-hectare and total tolerance must give the same verdict because the area
    cancels. True total 80.0 -> 8 t/ha -> exactly 25% off -> within.
    True total 79.0 -> 7.9 t/ha -> 26.6% off -> outside.
    """
    def frames_with_true_total(true_total):
        f = aligned_frames()
        f = {k: v.iloc[[0]].copy() for k, v in f.items()}
        f["yield"]["yield_true_total"] = [true_total]
        return f

    within = joint_success_report(frames_with_true_total(80.0))
    assert within["component_pass_rate"]["yield_within_25pct"] == 1.0
    outside = joint_success_report(frames_with_true_total(79.0))
    assert outside["component_pass_rate"]["yield_within_25pct"] == 0.0


def test_rows_missing_ground_truth_are_dropped_and_counted():
    frames = aligned_frames()
    frames["seed"].loc[0, "seed_true"] = None
    report = joint_success_report(frames)
    assert report["evaluable"] is True
    assert report["aligned_rows"] == 4
    assert report["test_rows"] == 3
    assert report["rows_dropped_missing_values"] == 1


def test_every_row_missing_is_not_evaluable():
    frames = aligned_frames()
    frames["seed"]["seed_true"] = None
    report = joint_success_report(frames)
    assert report["evaluable"] is False
    assert report["status"] == NOT_EVALUABLE
    assert "missing at least one required value" in report["reason"]


def test_non_positive_area_is_rejected():
    frames = aligned_frames()
    frames["yield"].loc[1, "yield_area_ha"] = 0.0
    with pytest.raises(JointEvaluationError):
        joint_success_report(frames)


def test_explicit_key_can_be_supplied():
    frames = aligned_frames()
    report = joint_success_report(frames, key="sample_id")
    assert report["evaluable"] is True
    assert report["key"] == "sample_id"


def test_wilson_interval_brackets_the_rate():
    low, high = wilson_interval(5, 10)
    assert low < 0.5 < high
    assert wilson_interval(0, 0) == (0.0, 0.0)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
