"""Aligned three-condition joint-success metric for SeedIQ.

Definition (unchanged)
----------------------
A test row succeeds only if, **on the same sample**:

  1. the crop prediction is correct,
  2. the yield prediction is within +/-25% of the actual yield per hectare,
  3. the seed-viability prediction is correct.

Why alignment is the whole point
--------------------------------
Crop, yield and seed are trained on three separate tables. Those tables carry
no shared sample identifier, so a row of one table is not the "same sample" as
a row of another. Pairing them by position (crop row ``i`` with yield row ``i``
and seed row ``i % n_seed``) manufactures rows that exist nowhere in the data:
it silently repeats the seed component (effective n = the seed test size),
drops the tail of the yield table, and lets a joint rate be reported as if it
came from a real sample of that size. This module never does that.

What it does instead
--------------------
* ``joint_success_report`` counts only rows that are genuinely joined on a key
  present in **every** source, and it validates that the key is unique in each
  source (a duplicated key is an error, not a silent many-to-many join).
* When no such key exists it returns ``evaluable=False`` with the reason and
  the per-source row counts: the joint metric is NOT EVALUABLE from these
  separate test sets.
* Rows missing any required ground truth or prediction are dropped and
  counted, never imputed.

Usage
-----
    from joint_metrics import joint_success_report, NOT_EVALUABLE

    report = joint_success_report({
        'crop':  crop_test_df,    # key + crop_pred, crop_true
        'yield': yield_test_df,   # key + yield_pred_total, yield_area_ha, yield_true_total
        'seed':  seed_test_df,    # key + seed_pred, seed_true
    })
    if not report['evaluable']:
        print(report['status'], report['reason'])

Ground truth for a *yield* row is expressed as the district-style total that the
model predicts plus the area it applies to; the +/-25% test is applied to the
per-hectare figure, which is what the tolerance is defined on.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Public constants
# --------------------------------------------------------------------------- #
NOT_EVALUABLE = "NOT EVALUABLE"

#: Columns that could identify the *same* sample across model-specific tables.
ALIGNMENT_KEY_CANDIDATES: Tuple[str, ...] = (
    "sample_id", "record_id", "plot_id", "field_id", "farm_id", "uid", "id",
)

#: Required columns per source (besides the shared key).
JOINT_REQUIRED: Dict[str, Tuple[str, ...]] = {
    "crop": ("crop_pred", "crop_true"),
    "yield": ("yield_pred_total", "yield_area_ha", "yield_true_total"),
    "seed": ("seed_pred", "seed_true"),
}

YIELD_TOLERANCE = 0.25

JOINT_DEFINITION = (
    "crop prediction correct AND yield prediction within +/-25% of actual "
    "per-hectare yield AND seed-viability prediction correct, evaluated on rows "
    "genuinely aligned by a shared sample key"
)

_NO_KEY_REASON = (
    "The crop, yield and seed test sets share no sample identifier "
    "(no common key column). No row of one set is the same sample as a row of "
    "another, so a joint-success rate cannot be computed from these separate "
    "test sets. Reporting a paired/round-robin figure would fabricate rows that "
    "exist nowhere in the data."
)


class JointEvaluationError(ValueError):
    """Raised when a joint evaluation is requested on structurally invalid input."""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> Tuple[float, float]:
    """Two-sided Wilson score interval for a binomial proportion."""
    if total <= 0:
        return 0.0, 0.0
    p = successes / total
    denom = 1.0 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = (z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _resolve_key_column(frame: pd.DataFrame, key: str) -> Optional[str]:
    """Return the frame's actual column name for ``key`` (case-insensitive)."""
    for column in frame.columns:
        if str(column).strip().lower() == key.strip().lower():
            return column
    return None


def find_alignment_key(
    frames: Mapping[str, pd.DataFrame],
    candidates: Sequence[str] = ALIGNMENT_KEY_CANDIDATES,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Find a key column present in every frame, or ``None``.

    Returns ``(key, details)``. Candidate names are compared case-insensitively
    and the *lower-case* candidate is returned so callers can rename uniformly.
    """
    lowered = [str(c).strip().lower() for c in candidates]
    per_source: Dict[str, list] = {}
    for name, frame in frames.items():
        columns = {str(c).strip().lower() for c in frame.columns}
        per_source[name] = sorted(columns.intersection(lowered))

    shared: set = set(per_source[next(iter(frames))]) if frames else set()
    for found in per_source.values():
        shared &= set(found)

    details = {
        "candidates": list(candidates),
        "key_columns_found_per_source": per_source,
        "shared_key_columns": sorted(shared),
    }
    key = sorted(shared)[0] if shared else None
    return key, details


def _per_source_rows(frames: Mapping[str, pd.DataFrame]) -> Dict[str, int]:
    return {name: int(len(frame)) for name, frame in frames.items()}


def _required_columns_error(name: str, frame: pd.DataFrame, required: Sequence[str]) -> list:
    return [c for c in required if c not in frame.columns]


# --------------------------------------------------------------------------- #
# Alignment
# --------------------------------------------------------------------------- #
def align_frames(
    frames: Mapping[str, pd.DataFrame],
    key: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
    """Inner-join model-specific test sets on a shared sample key.

    Each frame must expose the shared key plus its own required columns
    (:data:`JOINT_REQUIRED`); extra columns are dropped so a join can never
    silently bring one model's feature into another's row.

    Returns ``(aligned_frame_or_None, report)``. ``None`` means the sets cannot
    be aligned, and ``report['status']`` explains why.
    """
    if len(frames) < 2:
        raise JointEvaluationError("At least two sources are required to align a joint frame.")

    report: Dict[str, Any] = {
        "per_source_test_rows": _per_source_rows(frames),
        "sources": sorted(frames),
        "key": None,
    }

    for name, frame in frames.items():
        if name not in JOINT_REQUIRED:
            raise JointEvaluationError(
                f"Unknown source {name!r}; expected one of {sorted(JOINT_REQUIRED)}."
            )
        missing = _required_columns_error(name, frame, JOINT_REQUIRED[name])
        if missing:
            raise JointEvaluationError(
                f"Source {name!r} is missing required column(s) {missing}; "
                f"it must provide {list(JOINT_REQUIRED[name])}."
            )

    details: Dict[str, Any] = {}
    if key is None:
        key, details = find_alignment_key(frames)
    report["key_search"] = details

    if key is None:
        report["status"] = NOT_EVALUABLE
        report["evaluable"] = False
        report["aligned_rows"] = 0
        report["reason"] = _NO_KEY_REASON
        return None, report

    report["key"] = key

    merged: Optional[pd.DataFrame] = None
    for name, frame in frames.items():
        actual = _resolve_key_column(frame, key)
        if actual is None:
            raise JointEvaluationError(f"Source {name!r} has no {key!r} column.")
        if frame[actual].isna().any():
            raise JointEvaluationError(
                f"Source {name!r} has missing values in the alignment key {key!r}."
            )
        if frame[actual].duplicated().any():
            duplicates = int(frame[actual].duplicated().sum())
            raise JointEvaluationError(
                f"Source {name!r} has {duplicates} duplicated {key!r} value(s); "
                f"a joint row would be ambiguous."
            )
        keep = frame[[actual] + list(JOINT_REQUIRED[name])].rename(columns={actual: key})
        merged = keep if merged is None else merged.merge(keep, on=key, how="inner")

    assert merged is not None  # frames is non-empty and key is not None
    report["aligned_rows"] = int(len(merged))
    if report["aligned_rows"] == 0:
        report["status"] = NOT_EVALUABLE
        report["evaluable"] = False
        report["reason"] = (
            f"Key {key!r} exists in every source but the sources have no key values "
            f"in common, so no sample has crop, yield and seed ground truth together. "
            f"Joint success is NOT EVALUABLE from these separate test sets."
        )
        return None, report
    return merged, report


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def evaluate_aligned(
    aligned: pd.DataFrame,
    key: Optional[str] = None,
    tolerance: float = YIELD_TOLERANCE,
) -> Dict[str, Any]:
    """Compute the three-condition joint success on an aligned frame.

    A row is counted only when its crop label, yield total, area and seed label
    are all present and finite; incomplete rows are dropped and counted.
    """
    if aligned is None or len(aligned) == 0:
        raise JointEvaluationError("No aligned rows to evaluate.")

    missing = [c for c in ("crop_pred", "crop_true", "yield_pred_total", "yield_area_ha",
                           "yield_true_total", "seed_pred", "seed_true")
               if c not in aligned.columns]
    if missing:
        raise JointEvaluationError(f"Aligned frame is missing column(s): {missing}")

    numeric = aligned[[
        "crop_pred", "crop_true", "yield_pred_total",
        "yield_area_ha", "yield_true_total", "seed_pred", "seed_true",
    ]].apply(pd.to_numeric, errors="coerce")
    complete = numeric.notna().all(axis=1) & np.isfinite(numeric.to_numpy(dtype=float)).all(axis=1)
    dropped = int((~complete).sum())
    frame = numeric[complete]

    if len(frame) == 0:
        return {
            "evaluable": False,
            "status": NOT_EVALUABLE,
            "reason": "Every aligned row is missing at least one required value.",
            "aligned_rows": int(len(aligned)),
            "rows_dropped_missing_values": dropped,
            "definition": JOINT_DEFINITION,
        }

    areas = frame["yield_area_ha"].to_numpy(dtype=float)
    bad_area = areas <= 0
    if bad_area.any():
        raise JointEvaluationError(
            f"{int(bad_area.sum())} aligned row(s) have a non-positive area, so "
            f"per-hectare yield is undefined."
        )

    crop_true = frame["crop_true"].to_numpy()
    crop_pred = frame["crop_pred"].to_numpy()
    seed_true = frame["seed_true"].to_numpy()
    seed_pred = frame["seed_pred"].to_numpy()

    true_per_ha = frame["yield_true_total"].to_numpy(dtype=float) / areas
    pred_per_ha = frame["yield_pred_total"].to_numpy(dtype=float) / areas

    crop_ok = crop_pred == crop_true
    seed_ok = seed_pred == seed_true
    yield_ok = np.abs(pred_per_ha - true_per_ha) <= tolerance * np.abs(true_per_ha)
    success = crop_ok & yield_ok & seed_ok

    n = int(len(frame))
    k = int(success.sum())
    low, high = wilson_interval(k, n)
    return {
        "evaluable": True,
        "status": "EVALUABLE",
        "key": key,
        # rows genuinely joined on the shared key (before incomplete rows drop)
        "aligned_rows": int(len(aligned)),
        "rows_evaluated": n,
        "rows_dropped_missing_values": dropped,
        "test_rows": n,
        "successes": k,
        "failures": n - k,
        "rate": round(k / n, 6),
        "rate_ci95_wilson": [round(low, 6), round(high, 6)],
        "component_pass_rate": {
            "crop": round(float(crop_ok.mean()), 6),
            "yield_within_25pct": round(float(yield_ok.mean()), 6),
            "seed": round(float(seed_ok.mean()), 6),
        },
        "component_failures": {
            "crop": int((~crop_ok).sum()),
            "yield": int((~yield_ok).sum()),
            "seed": int((~seed_ok).sum()),
        },
        "yield_tolerance": tolerance,
        "definition": JOINT_DEFINITION,
    }


def joint_success_report(
    frames: Mapping[str, pd.DataFrame],
    key: Optional[str] = None,
    tolerance: float = YIELD_TOLERANCE,
) -> Dict[str, Any]:
    """Align the three model test sets and compute joint success on them.

    Never pairs by position. Returns ``evaluable=False`` (with ``status``
    ``NOT EVALUABLE``) when the sets cannot be genuinely aligned.
    """
    aligned, report = align_frames(frames, key=key)
    report.pop("evaluable", None)
    if aligned is None:
        report.setdefault("status", NOT_EVALUABLE)
        report["evaluable"] = False
        report["definition"] = JOINT_DEFINITION
        report["note"] = (
            "Pairing separate test sets by position is not a joint evaluation; "
            "this report deliberately withholds a rate rather than fabricate one."
        )
        return report

    metrics = evaluate_aligned(aligned, key=report.get("key"), tolerance=tolerance)
    if not metrics.get("evaluable"):
        merged = dict(report)
        merged.update(metrics)
        merged["evaluable"] = False
        return merged

    result = dict(report)
    result.update(metrics)
    result["per_source_test_rows"] = report["per_source_test_rows"]
    return result


def describe_alignment(frames: Mapping[str, pd.DataFrame]) -> str:
    """One-line human summary of whether the three test sets can be aligned."""
    _, report = align_frames(frames) if all(
        not _required_columns_error(n, f, JOINT_REQUIRED[n]) for n, f in frames.items()
    ) else (None, {"status": NOT_EVALUABLE, "reason": _NO_KEY_REASON,
                   "per_source_test_rows": _per_source_rows(frames)})
    if report.get("status") == NOT_EVALUABLE:
        rows = ", ".join(f"{k}={v}" for k, v in report.get("per_source_test_rows", {}).items())
        return f"{NOT_EVALUABLE}: {report.get('reason')} ({rows})"
    return (f"aligned on {report.get('key')!r}: {report.get('aligned_rows')} shared rows "
            f"of {report.get('per_source_test_rows')}")
