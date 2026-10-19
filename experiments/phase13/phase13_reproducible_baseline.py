"""
Phase 13 — Reproducible baseline (read-only F3 rerun under the pinned serving stack).

Purpose
--------
Establish that the F3 baseline is deterministic under one pinned environment: two
independent runs with identical data, seed, folds, and evaluation code should produce
identical predictions and metrics within numerical tolerance.

This script does NOT:
- run any candidates
- tune anything
- alter the production model or production code
- modify Phase 12 results

It reuses the existing F3 evaluation code from the improved-dataset track by importing
the read-only f3_oof / f3_predict helpers from phase10_error_analysis. If that import
is unavailable in the current environment, the script fails clearly rather than silently
inventing numbers.

Environment
-----------
Choose the pinned serving stack (scikit-learn 1.6.1 / numpy 2.0.2 / pandas 2.3.3) because
it is the only local stack under which the committed production artifact unpickles, and it
is already installed. Record the versions at runtime.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
import scipy

# ---------------------------------------------------------------------------
# 1. Choose and record the environment
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent  # workspace root (SeedIQ/)


def record_environment() -> dict:
    return {
        "executable": sys.executable,
        "python": sys.version.split()[0],
        "scikit_learn": sklearn.__version__,
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "platform": platform.platform(),
    }


ENV = record_environment()

# ---------------------------------------------------------------------------
# 2. Data source sanity check (same source as the improved-dataset track)
# ---------------------------------------------------------------------------

ENRICHED_CSV = ROOT / "experiments" / "improved_dataset" / "data" / "enriched_yield_karnataka.csv"
assert ENRICHED_CSV.exists(), f"expected enriched dataset at {ENRICHED_CSV}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


ENRICHED_SHA = sha256_file(ENRICHED_CSV)

# ---------------------------------------------------------------------------
# 3. Import the read-only F3 evaluation helpers from the existing track
# ---------------------------------------------------------------------------

# Allow the script to be run from anywhere; the track code is at a fixed location.
TRACK_PHASE10 = ROOT / "experiments" / "improved_dataset" / "phase10"
if str(TRACK_PHASE10) not in sys.path:
    sys.path.insert(0, str(TRACK_PHASE10))

import importlib

try:
    _pmod = importlib.import_module("phase10_error_analysis")
except Exception as e:
    raise RuntimeError(
        "Cannot import the existing F3 evaluation code from "
        f"{TRACK_PHASE10 / 'phase10_error_analysis.py'}: {e}\n"
        "This script is read-only and must reuse that code rather than reimplement it."
    ) from e


def _prepare():
    """Replicate phase10's data + split preparation exactly (same code path as main())."""
    _df, base_features = _pmod.load_base()
    _df = _pmod.add_dynamic_rainfall(_df)
    _df["group_key"] = _df["District"].astype(str) + "|" + _df["Year"].astype(str)
    groups = _df["group_key"].values
    y = _df["yield_per_hectare"].values
    gss = _pmod.GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr_idx, te_idx = next(gss.split(_df, y, groups))
    df_tr = _df.iloc[tr_idx].reset_index(drop=True)
    df_te = _df.iloc[te_idx].reset_index(drop=True)
    y_tr = df_tr["yield_per_hectare"]
    y_te = df_te["yield_per_hectare"]
    groups_tr = df_tr["group_key"]
    crops_tr = df_tr["Crop"]
    crops_te = df_te["Crop"].values
    feats_A = base_features
    feats_B = base_features + [
        f for f in _pmod.DYN_FEATURES if f not in base_features
    ]
    return df_tr, y_tr, groups_tr, crops_tr, df_te, crops_te, feats_A, feats_B


# ---------------------------------------------------------------------------
# 4. Run F3 twice, independently
# ---------------------------------------------------------------------------


def run_once(label: str) -> dict:
    """One full F3 baseline run: grouped OOF on the 80% split + frozen holdout on 20%.

    Returns a dict with the metric summary and the per-row predictions for both the OOF
    and the holdout, so a later comparison can check prediction-level determinism.
    """
    df_tr, y_tr, groups_tr, crops_tr, df_te, crops_te, feats_A, feats_B = _prepare()
    oof = _pmod.f3_oof(df_tr, y_tr, groups_tr, crops_tr, feats_A, feats_B)
    pred = _pmod.f3_predict(df_tr, y_tr, crops_tr, df_te, crops_te, feats_A, feats_B)
    oof_metrics = _pmod.metrics_dict(y_tr, oof)
    hold_metrics = _pmod.metrics_dict(y_te, pred)
    return {
        "label": label,
        "oof": {
            "predictions": oof.tolist(),
            "truth": y_tr.tolist(),
            "metrics": oof_metrics,
        },
        "holdout": {
            "predictions": pred.tolist(),
            "truth": y_te.tolist(),
            "metrics": hold_metrics,
        },
    }


run1 = run_once("run1")
run2 = run_once("run2")

# ---------------------------------------------------------------------------
# 5. Compare predictions and metrics
# ---------------------------------------------------------------------------


def predictions_identical_within(a: list, b: list, tol: float = 1e-12) -> bool:
    aa = np.asarray(a, dtype=float)
    bb = np.asarray(b, dtype=float)
    return bool(np.all(np.abs(aa - bb) <= tol))


def compare(name: str, r1: dict, r2: dict) -> dict:
    p1, p2 = np.asarray(r1["predictions"], dtype=float), np.asarray(
        r2["predictions"], dtype=float
    )
    max_abs_dev = float(np.max(np.abs(p1 - p2)))
    mean_abs_dev = float(np.mean(np.abs(p1 - p2)))
    metrics_identical = r1["metrics"] == r2["metrics"]
    return {
        "label": name,
        "n_rows": len(p1),
        "max_abs_prediction_deviation": max_abs_dev,
        "mean_abs_prediction_deviation": mean_abs_dev,
        "predictions_identical_within_1e_12": predictions_identical_within(p1, p2),
        "metrics_identical": metrics_identical,
        "run1_metrics": r1["metrics"],
        "run2_metrics": r2["metrics"],
    }


oof_comparison = compare("grouped_oof", run1["oof"], run2["oof"])
hold_comparison = compare("frozen_holdout", run1["holdout"], run2["holdout"])

# ---------------------------------------------------------------------------
# 6. Write results
# ---------------------------------------------------------------------------

RESULTS = {
    "phase": 13,
    "script": "phase13_reproducible_baseline.py",
    "objective": "reproducible production baseline before further improvement",
    "chosen_environment": {
        "label": "pinned serving stack (.freebuff/venv: py3.9.6 / sklearn 1.6.1)",
        "why": "the pinned serving stack in SeedIQ/requirements.txt (scikit-learn 1.6.1 / numpy 2.0.2 / pandas 2.3.3 / scipy 1.13.1) — the only local stack under which the committed production artifact unpickles; already installed, so no package change",
        "recorded_versions": {**ENV, "is_the_pinned_serving_interpreter": True, "matches_pin_sklearn_1_6_1": ENV["scikit_learn"] == "1.6.1"},
        "dependency_files": {
            "SeedIQ/requirements.txt": {
                "present": (ROOT / "SeedIQ" / "requirements.txt").exists(),
                "numeric_stack_pins": {
                    "numpy": "2.0.2",
                    "pandas": "2.3.3",
                    "scipy": "1.13.1",
                    "scikit-learn": "1.6.1",
                    "xgboost": "2.1.4",
                    "joblib": "1.5.3",
                },
                "comment": "pins the numeric stack because every committed model artifact was serialized with scikit-learn 1.6.1 (sklearn>=1.7 removed the private `_loss` module the yield pickle references)",
            },
            "root .python-version": "3.11.17",
            "root requirements.txt": "-r SeedIQ/requirements.txt",
        },
        "deployment_note": ".python-version pins 3.11.17 for Railway; the local venv is Python 3.9.6 with the SAME pinned numeric stack (same sklearn/numpy/pandas/scipy, different Python minor) — recorded as residual risk, not ignored",
    },
    "other_local_environment": {
        "python": "3.14.6",
        "scikit_learn": "1.9.1",
        "numpy": "2.5.3",
        "pandas": "3.0.6",
        "scipy": "1.18.1",
        "executable": "/usr/local/opt/python@3.14/bin/python3.14",
        "interpreter": "/usr/local/bin/python3",
        "ok": True,
    },
    "data": {
        "file": str(ENRICHED_CSV.relative_to(ROOT)),
        "sha256": ENRICHED_SHA,
        "rows": len(df),
    },
    "seed": 42,
    "folds": "GroupKFold(5) District|Year (OOF) + GroupShuffleSplit(0.2, rs=42) holdout",
    "evaluation_code": "phase10_error_analysis.f3_oof / f3_predict (read-only import)",
    "grouped_oof": {
        "note": "80% training split, 5-fold grouped out-of-fold — kept separate from the holdout",
        "comparison": oof_comparison,
    },
    "frozen_holdout": {
        "note": "fit on the 80% split, evaluate the untouched 20% district-year holdout — kept separate from the OOF",
        "comparison": hold_comparison,
    },
    "pass": bool(
        oof_comparison["predictions_identical_within_1e_12"]
        and oof_comparison["metrics_identical"]
        and hold_comparison["predictions_identical_within_1e_12"]
        and hold_comparison["metrics_identical"]
    ),
}

out_dir = HERE / "results"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "phase13_results.json"
out_path.write_text(json.dumps(RESULTS, indent=2), encoding="utf-8")

print(json.dumps(RESULTS, indent=2))
print("\nWROTE", out_path)
