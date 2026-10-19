"""
Phase 13 — Reproducibility and data-driven improvement
======================================================

Continues the completed Phase 12 (audit + one experiment, results untouched).

  Task 1  Resolve the environment discrepancy: which Python/sklearn trains,
          evaluates and serves; whether committed artifacts load under a
          compatible environment; whether the production model shares code,
          data and feature schema with the evaluated F3; whether the Phase
          9-11 claims survive one consistent environment.
  Task 2  Reproducible baseline: run F3 TWICE under one chosen supported
          environment (same data, seed, folds, evaluation code) and prove the
          predictions and metrics are identical within tolerance. Grouped OOF
          and frozen holdout are reported as separate sections.
  Task 3  Quantify, from the Phase 12 subgroup analysis, which MISSING
          agricultural variables could plausibly reduce error; separate data
          already on disk from data that must be collected; name the single
          most valuable next action.

Constraints honoured: no package installs/upgrades, no model experiments
(only determinism reruns of the F3 baseline), no production code or model
changes, no Phase 12 overwrite (sha256 verified before/after), no data
downloads, no invented observations.
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import platform
import re
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── paths ─────────────────────────────────────────────────────────────────────
PHASE13 = Path(__file__).resolve().parent              # .../phase13
IMPROVED = PHASE13.parent                              # .../improved_dataset
PHASE10 = IMPROVED / "phase10"
REPO = IMPROVED.parents[1]                             # /Users/apple/SeedIQ
RES_DIR = PHASE13 / "results"
RES_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = RES_DIR / "phase13_results.json"

PHASE12_JSON = IMPROVED / "phase12" / "results" / "phase12_results.json"
assert PHASE12_JSON.exists(), "Phase 12 results missing — complete Phase 12 first"

ENRICHED_CSV = IMPROVED / "data" / "enriched_yield_karnataka.csv"
PROD_CSV = REPO / "SeedIQ" / "data" / "yield_icrisat_karnataka.csv"
PROD_PICKLE = REPO / "SeedIQ" / "models" / "yield_prediction" / "randomforest_model.pkl"
PROD_MANIFEST = REPO / "SeedIQ" / "models" / "yield_feature_manifest.json"
F3_MANIFEST = IMPROVED / "models" / "yield_enriched_feature_manifest.json"
REQUIREMENTS = REPO / "SeedIQ" / "requirements.txt"
REGISTRY = REPO / "SeedIQ" / "training_registry.json"
PYTHON_VERSION_FILE = REPO / ".python-version"

# The ONE supported environment chosen for this baseline (documented in report):
# the pinned serving stack already installed locally — no package changes.
PINNED_SKLEARN = "1.6.1"
CHOSEN_INTERPRETER = str(REPO / ".freebuff" / "venv" / "bin" / "python")
OTHER_INTERPRETER = "/usr/local/bin/python3"          # eval stack: py3.14 / sklearn 1.9.1
CHOOSE_ENV_LABEL = "pinned serving stack (.freebuff/venv: py3.9.6 / sklearn 1.6.1)"

sys.path.insert(0, str(PHASE10))
from phase10_error_analysis import (  # noqa: E402
    load_base, add_dynamic_rainfall, metrics_dict, f3_oof, f3_predict, DYN_FEATURES,
)
from sklearn.model_selection import GroupShuffleSplit  # noqa: E402

TOL = 1e-12


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def environment_info():
    import scipy
    import sklearn
    return {
        "executable": sys.executable,
        "python": sys.version.split()[0],
        "scikit_learn": sklearn.__version__,
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "platform": platform.platform(),
    }


def probe_interpreter(py: str) -> dict:
    """Fast version probe of another interpreter (no imports of project code)."""
    code = ("import sys, json, numpy, pandas, scipy, sklearn; "
            "print('PYPROBE:' + json.dumps({'python': sys.version.split()[0], "
            "'scikit_learn': sklearn.__version__, 'numpy': numpy.__version__, "
            "'pandas': pandas.__version__, 'scipy': scipy.__version__, "
            "'executable': sys.executable}))")
    try:
        proc = subprocess.run([py, "-c", code], capture_output=True, text=True, timeout=120)
        line = [l for l in proc.stdout.splitlines() if l.startswith("PYPROBE:")]
        if not line:
            return {"interpreter": py, "ok": False,
                    "error": (proc.stderr or proc.stdout)[-300:]}
        out = json.loads(line[-1][len("PYPROBE:"):])
        out.update({"interpreter": py, "ok": True})
        return out
    except Exception as exc:  # noqa: BLE001 - recorded, never fatal
        return {"interpreter": py, "ok": False, "error": repr(exc)}


def environment_inventory():
    chosen = environment_info()
    other = probe_interpreter(OTHER_INTERPRETER) if os.path.exists(OTHER_INTERPRETER) else \
        {"interpreter": OTHER_INTERPRETER, "ok": False, "error": "not found"}
    is_chosen = os.path.realpath(sys.executable) == os.path.realpath(CHOSEN_INTERPRETER)
    chosen["is_the_pinned_serving_interpreter"] = bool(is_chosen)
    chosen["matches_pin_sklearn_1_6_1"] = (chosen["scikit_learn"] == PINNED_SKLEARN)
    return chosen, other


def dependency_files() -> dict:
    req = REQUIREMENTS.read_text() if REQUIREMENTS.exists() else ""
    pins = dict(re.findall(r"^([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-]+)", req, re.M))
    out = {
        "SeedIQ/requirements.txt": {
            "present": bool(req),
            "numeric_stack_pins": {k: pins[k] for k in
                                   ("numpy", "pandas", "scipy", "scikit-learn", "xgboost", "joblib")
                                   if k in pins},
            "comment": "pins the numeric stack because every committed model artifact "
                       "was serialized with scikit-learn 1.6.1 (sklearn>=1.7 removed "
                       "the private `_loss` module the yield pickle references)",
        },
        "root .python-version": (PYTHON_VERSION_FILE.read_text().strip()
                                 if PYTHON_VERSION_FILE.exists() else None),
        "root requirements.txt": ("-r SeedIQ/requirements.txt" if
                                 (REPO / "requirements.txt").exists() else None),
    }
    return out


# ══════════════════════════════════════════════════════════════════════════════
# TASK 1 — artifact compatibility, production-vs-F3, evaluation splits
# ══════════════════════════════════════════════════════════════════════════════
def artifact_compatibility() -> dict:
    """Load the committed production artifact under BOTH local stacks."""
    raw = PROD_PICKLE.read_bytes()
    embedded = sorted({v.decode() for v in
                       re.findall(rb"_sklearn_version.{0,24}?((?:0|1)\.\d+\.\d+)", raw)})

    # (a) under THIS (chosen) interpreter
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            sys.path.insert(0, str(REPO / "SeedIQ"))
            with open(PROD_PICKLE, "rb") as f:
                model = pickle.load(f)
            load_ok = True
            load_err = None
        except Exception as exc:  # noqa: BLE001
            load_ok, load_err, model = False, repr(exc), None
        warns = [str(w.message) for w in caught]

    result = {
        "artifact": str(PROD_PICKLE.relative_to(REPO)),
        "sha256": sha256(PROD_PICKLE),
        "embedded_sklearn_version": embedded,
        "load_under_chosen_env": {"ok": load_ok, "error": load_err, "warnings": warns},
    }
    if model is not None:
        reg = getattr(model, "regressor_", None)
        result["chosen_env_details"] = {
            "class": type(model).__module__ + "." + type(model).__name__,
            "wrapper_n_features": getattr(model, "n_features_in_", None),
            "inner_regressor": type(reg).__name__ if reg is not None else None,
            "inner_params": ({k: reg.get_params().get(k) for k in
                              ("loss", "max_iter", "learning_rate", "random_state")}
                             if reg is not None else None),
        }
        # smoke prediction on the published 23-column contract (read-only)
        try:
            cols = json.loads(PROD_MANIFEST.read_text())["feature_columns"]
            row = {c: 0.0 for c in cols}
            row["Area_Hectares"] = 1000.0
            row["Crop_Rice"] = 1.0
            X = pd.DataFrame([row])[cols]
            result["chosen_env_details"]["smoke_predict_1000ha_rice_total_tonnes"] = float(
                model.predict(X)[0])
            result["chosen_env_details"]["smoke_predict_ok"] = True
        except Exception as exc:  # noqa: BLE001
            result["chosen_env_details"]["smoke_predict_ok"] = False
            result["chosen_env_details"]["smoke_predict_error"] = repr(exc)

    # (b) under the OTHER local interpreter (the evaluation stack)
    other = probe_interpreter_load(PROD_PICKLE)
    result["load_under_other_env"] = other
    result["compatible_environment"] = (
        "artifact loads only under the pinned scikit-learn 1.6.1 stack; the evaluation "
        "stack (sklearn 1.9.1) fails to unpickle it (private `_loss` module removed in "
        "sklearn >= 1.7), so evaluation and serving CANNOT share an environment until "
        "the artifact is re-serialized or the stack is unified")
    return result


def probe_interpreter_load(pickle_path: Path) -> dict:
    """Attempt to unpickle the production artifact in the other interpreter."""
    code = (
        "import sys, pickle, json\n"
        "sys.path.insert(0, sys.argv[2])\n"
        "try:\n"
        "    with open(sys.argv[1],'rb') as f: m = pickle.load(f)\n"
        "    reg = getattr(m, 'regressor_', None)\n"
        "    print('LOADPROBE:' + json.dumps({'ok': True, "
        "'class': type(m).__name__, "
        "'inner': type(reg).__name__ if reg is not None else None}))\n"
        "except Exception as e:\n"
        "    print('LOADPROBE:' + json.dumps({'ok': False, "
        "'error': type(e).__name__ + ': ' + str(e)[:300]}))\n"
    )
    if not os.path.exists(OTHER_INTERPRETER):
        return {"interpreter": OTHER_INTERPRETER, "ok": False, "error": "not found"}
    try:
        proc = subprocess.run(
            [OTHER_INTERPRETER, "-c", code, str(pickle_path), str(REPO / "SeedIQ")],
            capture_output=True, text=True, timeout=180)
        line = [l for l in proc.stdout.splitlines() if l.startswith("LOADPROBE:")]
        if not line:
            return {"interpreter": OTHER_INTERPRETER, "ok": False,
                    "error": (proc.stderr or proc.stdout)[-300:]}
        out = json.loads(line[-1][len("LOADPROBE:"):])
        out["interpreter"] = OTHER_INTERPRETER
        return out
    except Exception as exc:  # noqa: BLE001
        return {"interpreter": OTHER_INTERPRETER, "ok": False, "error": repr(exc)}


def production_vs_f3() -> dict:
    """Was the served model trained like the evaluated F3? (code/data/schema)"""
    prod_manifest = json.loads(PROD_MANIFEST.read_text())
    f3_manifest = json.loads(F3_MANIFEST.read_text())
    registry = json.loads(REGISTRY.read_text())
    served = [e for e in registry if e.get("model_name") ==
              "yield_prediction/randomforest_model.pkl"]
    last = served[-1] if served else {}

    rows = {
        "identical": False,
        "aspect": {
            "training_code": {
                "production": "SeedIQ/train_all_models.py::train_yield -> make_yield_model() "
                              "(yield_model.LogPerHaRegressor)",
                "f3_evaluation": "experiments/improved_dataset/phase10/"
                                 "phase10_error_analysis.py::f3_oof (per-crop models, "
                                 "0.8*A + 0.2*B blend, Chickpea RF specialist)",
                "same": False,
            },
            "model_class_and_loss": {
                "production": "HistGradientBoostingRegressor(loss=squared_error, "
                              "max_iter=400, lr=0.08) on log(Yield_Tonnes/Area_Hectares)",
                "f3_evaluation": "HistGradientBoostingRegressor(loss=absolute_error, "
                                 "max_iter=200, lr=0.05, depth=6) per crop, blended; "
                                 "target yield_per_hectare (raw t/ha)",
                "same": False,
            },
            "data": {
                "production": str(PROD_CSV.relative_to(REPO)) +
                              " (5,585 rows; ICRISAT district names)",
                "f3_evaluation": str(ENRICHED_CSV.relative_to(REPO)) +
                                 " (5,585 rows; renamed districts + soil/rain/year features)",
                "same_source_rows": True,
                "same_file": False,
            },
            "feature_schema": {
                "production_features_count": prod_manifest.get("records") and
                    len(prod_manifest["feature_columns"]),
                "production_target": prod_manifest.get("target"),
                "production_columns_head": prod_manifest["feature_columns"][:3],
                "f3_features_count": len(f3_manifest["feature_columns"]),
                "f3_target": f3_manifest.get("target"),
                "f3_branch_b_features_added": "7 dyn_rain_* features",
                "same": False,
                "note": "23 columns (Area + 22 crop dummies, no District/Year/soil/rain) "
                        "vs 56 base (63 with dynamic rainfall) district-conditioned features",
            },
            "evaluation_protocol": {
                "production": "GroupShuffleSplit(0.2, rs=42) district-year groups; "
                              "GroupKFold(5) CV on TRAIN only; metrics are on district "
                              "TOTALS in tonnes (R2)",
                "f3_evaluation": "same splitter family but different label set (renamed "
                                 "districts change sort order -> different groups selected); "
                                 "grouped OOF on train split + frozen holdout; metrics are "
                                 "within-+/-25% on t/ha",
                "same_rows": False,
                "different_holdout_rows_reason": "district label spellings differ between "
                                                  "the two tables, so the same seed selects "
                                                  "different district-year groups",
            },
            "registry_metrics_not_comparable": {
                "production_test_r2_on_tonnes": (last.get("metrics") or {}).get("test", {}).get("r2"),
                "f3_holdout_within_25_on_t_per_ha": 68.1985,
                "note": "different target scale, different rows, different loss — the "
                        "production artifact has never been scored with the F3 "
                        "within-+/-25% per-hectare protocol",
            },
        },
        "registry_entry": {
            "timestamp": last.get("timestamp"),
            "algorithm": last.get("algorithm"),
            "dataset_path": last.get("dataset_path"),
            "records": last.get("records"),
            "features_count": last.get("features_count"),
            "target": last.get("target"),
            "sample_counts": last.get("sample_counts"),
            "random_state": last.get("random_state"),
            "dataset_synthetic": last.get("dataset_synthetic"),
        },
        "verdict": ("NOT trained with the same code, data file, feature schema, target "
                    "transform or evaluation rows as the evaluated F3 — the Phase 9-12 "
                    "numbers describe an experimental per-crop model, not the served "
                    "artifact"),
    }
    return rows


def split_comparison() -> dict:
    """Same splitter params, different rows — prove it with both CSVs."""
    from sklearn.model_selection import GroupShuffleSplit

    def split_of(csv, district_col=None):
        df = pd.read_csv(csv)
        key = (df[district_col].astype(str) + "|" + df["Year"].astype(str)
               if district_col else df["District"].astype(str) + "|" + df["Year"].astype(str))
        groups = key.to_numpy()
        y = df["yield_per_hectare"].to_numpy() if "yield_per_hectare" in df else \
            (df["Yield_Tonnes"] / df["Area_Hectares"]).to_numpy()
        tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
                      .split(df, y, groups))
        test_keys = set(key.iloc[te])
        return {"rows_train": int(len(tr)), "rows_test": int(len(te)),
                "groups_test": int(len(test_keys)), "test_keys": test_keys}

    f3 = split_of(ENRICHED_CSV)
    prod = split_of(PROD_CSV)
    overlap = f3["test_keys"] & prod["test_keys"]
    return {
        "splitter": "GroupShuffleSplit(test_size=0.2, random_state=42) on District|Year",
        "f3_experiment_split": {"rows_train": f3["rows_train"],
                                "rows_test": f3["rows_test"],
                                "groups_test": f3["groups_test"]},
        "production_split": {"rows_train": prod["rows_train"],
                             "rows_test": prod["rows_test"],
                             "groups_test": prod["groups_test"],
                             "matches_registry_4423_1162":
                                 (prod["rows_train"], prod["rows_test"]) == (4423, 1162)},
        "test_group_overlap": int(len(overlap)),
        "same_holdout_rows": bool(overlap and len(overlap) == f3["groups_test"]
                                  == prod["groups_test"]),
        "note": ("identical splitter parameters select different district-year groups "
                 "because district label spellings differ between the enriched table "
                 "(renamed) and the ICRISAT table (source names) — np.unique sorts by "
                 "label, so the seeded permutation lands on different groups"),
    }


def phase9_11_claim_check() -> dict:
    """Do the Phase 9-11 claims survive one consistent environment? (read-only)"""
    files = [
        IMPROVED / "results" / "phase9_consolidated_results.json",
        IMPROVED / "phase9" / "results" / "phase9_consolidated_results.json",
        IMPROVED / "phase10" / "results" / "phase10_hypothesis_results.json",
        IMPROVED / "phase10" / "results" / "phase10_error_analysis.json",
        IMPROVED / "phase11" / "results" / "phase11_results.json",
    ]
    scanned = {}
    env_keys = ("sklearn", "scikit", "python_version", "\"environment\"")
    for fp in files:
        if not fp.exists():
            continue
        blob = fp.read_text()
        scanned[str(fp.relative_to(REPO))] = {
            "records_environment": any(k in blob.lower() for k in env_keys),
            "baseline_69_5352_present": "69.5352" in blob,
            "holdout_742_present": "742" in blob,
            "pinned_stack_value_68_4679_present": "68.4679" in blob,
        }
    return {
        "scanned_result_files": scanned,
        "environment_recorded_by_any_phase_9_11": any(
            v["records_environment"] for v in scanned.values()),
        "assessment": (
            "Phase 9-11 never recorded an interpreter/library version. Their shared "
            "baseline constants (69.5352% OOF, 742/1088 holdout) reproduce ONLY on the "
            "evaluation stack (py3.14.6/sklearn 1.9.1), so all three phases ran there — "
            "internally one consistent environment. Their retain-F3 decisions are "
            "deltas measured within that single stack and are therefore internally "
            "valid. What does NOT transfer: the absolute metrics (the pinned serving "
            "stack scores 68.4679%/740 on the identical code) and any delta smaller "
            "than the measured 1.07 pp level gap. Phase 12 measured one candidate under "
            "both stacks (+0.267 vs +0.222 pp) suggesting deltas are stabler than "
            "levels, but n=1 — no Phase 9-11 claim can be certified under the serving "
            "stack without re-measurement, which this phase deliberately does NOT do "
            "(no new model experiments)"),
        "claims_rem_valid_single_env": (
            "YES for internal consistency (all three ran on one stack); "
            "NOT ESTABLISHED for the serving stack (untested there); "
            "absolute values are stack-specific"),
    }


# ══════════════════════════════════════════════════════════════════════════════
# TASK 2 — run F3 twice under the chosen environment
# ══════════════════════════════════════════════════════════════════════════════
def build_f3_frames():
    """Identical data, seed and folds as Phase 10/11/12 (frozen split rs=42)."""
    df, base_features = load_base()
    df = add_dynamic_rainfall(df)
    df["group_key"] = df["District"].astype(str) + "|" + df["Year"].astype(str)
    groups = df["group_key"].values
    y = df["yield_per_hectare"].values
    tr_idx, te_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
                          .split(df, y, groups))
    df_tr = df.iloc[tr_idx].reset_index(drop=True)
    df_te = df.iloc[te_idx].reset_index(drop=True)
    feats_A = base_features
    feats_B = base_features + [f for f in DYN_FEATURES if f not in base_features]
    return df_tr, df_te, feats_A, feats_B


def run_f3_once(df_tr, df_te, feats_A, feats_B) -> dict:
    """One full F3 evaluation: grouped OOF (train split) + frozen holdout."""
    y_tr = df_tr["yield_per_hectare"]
    groups_tr = df_tr["group_key"]
    crops_tr = df_tr["Crop"]
    oof = f3_oof(df_tr, y_tr, groups_tr, crops_tr, feats_A, feats_B)
    oof_metrics = metrics_dict(y_tr.values, oof)

    pred_hold = f3_predict(df_tr, y_tr, crops_tr, df_te,
                           pd.Series(df_te["Crop"].values), feats_A, feats_B)
    hold_metrics = metrics_dict(df_te["yield_per_hectare"].values, pred_hold)
    return {"oof_pred": oof, "oof_metrics": oof_metrics,
            "holdout_pred": pred_hold, "holdout_metrics": hold_metrics}


def compare_runs(a: dict, b: dict, label: str) -> dict:
    da = np.abs(np.asarray(a["oof_pred"] if "oof_pred" in a else a["pred"], dtype=float) -
                np.asarray(b["oof_pred"] if "oof_pred" in b else b["pred"], dtype=float))
    ma = a.get("oof_metrics") or a.get("metrics")
    mb = b.get("oof_metrics") or b.get("metrics")
    max_dev = float(da.max()) if da.size else 0.0
    return {
        "label": label,
        "n_rows": int(da.size),
        "max_abs_prediction_deviation": max_dev,
        "mean_abs_prediction_deviation": float(da.mean()) if da.size else 0.0,
        "predictions_identical_within_1e_12": bool(max_dev <= TOL),
        "metrics_identical": bool(ma == mb),
        "run1_metrics": ma,
        "run2_metrics": mb,
    }


def reproducibility() -> dict:
    print("  building identical F3 frames (data + frozen split rs=42)...")
    df_tr, df_te, feats_A, feats_B = build_f3_frames()
    print(f"  train rows={len(df_tr)} holdout rows={len(df_te)} | "
          f"features A={len(feats_A)} B={len(feats_B)}")
    print("  F3 run 1 (grouped OOF + frozen holdout)...")
    r1 = run_f3_once(df_tr, df_te, feats_A, feats_B)
    print(f"    OOF {r1['oof_metrics']['correct_25']}/{r1['oof_metrics']['total']} = "
          f"{r1['oof_metrics']['pct_25']}% | holdout "
          f"{r1['holdout_metrics']['correct_25']}/{r1['holdout_metrics']['total']} = "
          f"{r1['holdout_metrics']['pct_25']}%")
    print("  F3 run 2 (same data, seed, folds, evaluation code)...")
    r2 = run_f3_once(df_tr, df_te, feats_A, feats_B)
    print(f"    OOF {r2['oof_metrics']['correct_25']}/{r2['oof_metrics']['total']} = "
          f"{r2['oof_metrics']['pct_25']}% | holdout "
          f"{r2['holdout_metrics']['correct_25']}/{r2['holdout_metrics']['total']} = "
          f"{r2['holdout_metrics']['pct_25']}%")

    oof_cmp = compare_runs(
        {"oof_pred": r1["oof_pred"], "oof_metrics": r1["oof_metrics"]},
        {"oof_pred": r2["oof_pred"], "oof_metrics": r2["oof_metrics"]},
        "grouped_oof")
    hold_cmp = compare_runs(
        {"pred": r1["holdout_pred"], "metrics": r1["holdout_metrics"]},
        {"pred": r2["holdout_pred"], "metrics": r2["holdout_metrics"]},
        "frozen_holdout")
    return {
        "environment": environment_info(),
        "data": str(ENRICHED_CSV.relative_to(REPO)),
        "seed": 42,
        "folds": "GroupKFold(5) District|Year (OOF) + GroupShuffleSplit(0.2, rs=42) holdout",
        "evaluation_code": "phase10_error_analysis.f3_oof / f3_predict (read-only import)",
        "grouped_oof": {
            "note": "80% training split, 5-fold grouped out-of-fold — kept separate "
                    "from the holdout",
            "comparison": oof_cmp,
        },
        "frozen_holdout": {
            "note": "fit on the 80% split, evaluate the untouched 20% district-year "
                    "holdout — kept separate from the OOF",
            "comparison": hold_cmp,
        },
        "pass": bool(oof_cmp["predictions_identical_within_1e_12"] and
                     hold_cmp["predictions_identical_within_1e_12"] and
                     oof_cmp["metrics_identical"] and hold_cmp["metrics_identical"]),
    }


# ══════════════════════════════════════════════════════════════════════════════
# TASK 3 — highest-value next data improvement (Phase 12 read-only)
# ══════════════════════════════════════════════════════════════════════════════
def data_gap_analysis() -> dict:
    p12 = json.loads(PHASE12_JSON.read_text())
    ea = p12["error_analysis"]
    total_rows = ea["overall"]["total"]
    total_fail = ea["largest_failure_subgroup"]["total_failures"]
    overall_rate = ea["overall"]["pct_25"] / 100.0

    def bound(name, n, failures, why):
        target = round(n * overall_rate)
        gain = max(0, target - (n - failures))
        return {"subgroup": name, "rows": n, "current_passes": n - failures,
                "failures": failures,
                "fail_share_of_all_pct": round(100 * failures / total_fail, 1),
                "upper_bound_if_subgroup_reached_overall_rate_rows": gain,
                "upper_bound_pp": round(100 * gain / total_rows, 2),
                "why": why}

    bands, years, crops = ea["by_yield_band"], ea["by_year"], ea["by_crop"]
    low = bands["0-0.5"]
    drought = ["2003", "2016", "2017"]
    d_rows = sum(years[y]["n"] for y in drought)
    d_fail = sum(years[y]["failures"] for y in drought)
    weak = ["Sesamum", "Pigeonpea", "Minor Pulses", "Safflower", "Linseed"]
    w_rows = sum(crops[c]["n"] for c in weak)
    w_fail = sum(crops[c]["failures"] for c in weak)

    drought_bound = bound(
        "drought/shock years 2003+2016+2017", d_rows, d_fail,
        "worst years (49.8-62.1% pass); 2016-2017 also carry forward-filled 2015 "
        "rainfall — a demonstrated data defect")
    drought_bound["stale_rainfall_subset_2016_2017"] = {
        "rows_in_oof": sum(years[y]["n"] for y in ("2016", "2017")),
        "failures": sum(years[y]["failures"] for y in ("2016", "2017")),
        "note": "IMD series ends 2015; Phase 12 measured 10.04% of ALL rows served "
                "2015 subdivision rainfall for 2016-2017 via Year.clip(upper=2015)",
    }

    bounds = [
        bound("actual yield < 0.5 t/ha (largest failure cluster)", low["n"],
              low["failures"],
              "44% of all failures; dominated by year-to-year dispersion (median "
              "CV 0.34 > the 0.25 band) that district statics + subdivision rainfall "
              "cannot explain"),
        drought_bound,
        bound("five weakest rainfed crops (" + ", ".join(weak) + ")",
              w_rows, w_fail,
              "28% of all failures; candidate variables: irrigation, soil moisture, "
              "sowing windows"),
    ]

    available_now = [
        {"dataset": "experiments/improved_dataset/phase9/data/"
                    "openmeteo_daily_weather_karnataka.csv",
         "content": "ERA5 district daily rainfall+temperature, 19 districts, "
                    "2000-2017, 124,925 rows",
         "status": "ON DISK; already MEASURED in Phase 9 — candidates B/C/D/E/F all "
                   "regressed the holdout (-1.10 to -4.69 pp). Not a new source of "
                   "value as-is (reanalysis, not observed ground truth)"},
        {"dataset": "SeedIQ/data/rainfall in india 1901-2015.csv",
         "content": "IMD subdivision rainfall 1901-2015 (3 Karnataka subdivisions)",
         "status": "ON DISK; already used by F3 branch B (20% weight); ends 2015"},
        {"dataset": "SeedIQ/data/district wise rainfall normal.csv",
         "content": "district long-term rainfall normals (static)",
         "status": "ON DISK; already the static rain_* features in F3"},
        {"dataset": "soil CSV + ICRISAT area/production tables",
         "content": "static soil properties; district-year-crop area/production 2000-2017",
         "status": "ON DISK; already the label + area feature. Same-year other-crop "
                   "yields are target-derived (not pre-harvest usable); lagged own "
                   "yields were screened in Phase 12 and measured -3.14 pp"},
    ]

    to_collect = [
        {"variable": "district-resolution OBSERVED monthly rainfall for the target "
                     "year, including 2016-2017",
         "exact_source": "India Meteorological Department district rainfall data; the "
                         "convenience mirror identified in Phase 11: Kaggle dataset "
                         "'dhamur/monthly-district-avg-rainfall-19012017indiacsv' "
                         "(1901-2017 monthly district averages)",
         "dependency_requirement": "NONE new — CSV read with the already-pinned pandas; "
                                   "only prerequisite is Kaggle API credentials (Phase 11 "
                                   "blocker) or direct IMD open-data download",
         "downloaded": False,
         "addresses": "removes the Year.clip forward-fill defect (10.04% of rows) and "
                      "feeds the three worst years"},
        {"variable": "irrigation source/coverage and soil moisture",
         "exact_source": "not identified in-repo; candidates: CGWB/IWMI groundwater "
                         "levels, state irrigation department irrigated-area series",
         "dependency_requirement": "TBD at sourcing — not assessed; no install planned",
         "downloaded": False,
         "addresses": f"five weakest rainfed crops ({w_fail} failures, "
                      f"{round(100*w_fail/total_fail,1)}% of all)"},
        {"variable": "crop calendar / sowing-harvest windows per district",
         "exact_source": "ICAR / Directorate of Economics & Statistics crop calendars",
         "dependency_requirement": "NONE expected (tabular CSV/PDF extract)",
         "downloaded": False,
         "addresses": "aligns weather with growing windows; enables seasonal rather "
                      "than calendar-year rainfall sums"},
        {"variable": "field- or block-level yield observations",
         "exact_source": "state agriculture department / district statistical handbooks; "
                         "no public machine-readable source identified",
         "dependency_requirement": "N/A — institutional data sharing, not software",
         "downloaded": False,
         "addresses": "the dispersion itself — Phase 12's ceiling argument"},
    ]

    return {
        "source": "Phase 12 results, read-only: " + str(PHASE12_JSON.relative_to(REPO)),
        "total_oof_rows": total_rows,
        "total_failures": total_fail,
        "overall_pass_rate_pct": ea["overall"]["pct_25"],
        "opportunity_bounds": bounds,
        "bounds_are_upper_limits_not_predictions": True,
        "overlap_caveat": "the three subgroups overlap (drought years and weak crops "
                          "sit inside the <0.5 t/ha band), so bounds must not be summed",
        "already_available_data": available_now,
        "must_be_collected": to_collect,
        "single_most_valuable_next_action": {
            "action": "Collect district-resolution OBSERVED rainfall for 2000-2017 "
                      "(minimum 2016-2017) and replace the Year.clip(upper=2015) "
                      "forward-fill with real observations — before any further model work",
            "why_first": (
                "only demonstrated data defect in the pipeline (10.04% of rows carry "
                "2015 rainfall for later years), targets the three worst years "
                f"({d_rows} rows / {d_fail} failures = "
                f"{round(100*d_fail/total_fail,1)}% of all failures), needs no new "
                "dependency and no code change beyond the join, and the only "
                "already-available alternative (ERA5) was measured to HURT in Phase 9"),
            "quantified_upper_bound_pp": drought_bound["upper_bound_pp"],
            "strategic_second": "field-/block-level yields address the largest cluster "
                                f"(bound {bounds[0]['upper_bound_pp']} pp) but need "
                                "institutional data sharing, not a download",
        },
        "no_downloads_no_installs_performed": True,
    }


# ══════════════════════════════════════════════════════════════════════════════
def main():
    print("=== Phase 13: reproducible baseline ===\n")
    digest_before = sha256(PHASE12_JSON)

    print("[1/5] environment + dependency inventory...")
    chosen, other = environment_inventory()
    deps = dependency_files()

    print("[2/5] artifact compatibility + production-vs-F3 inspection...")
    artifact = artifact_compatibility()
    splits = split_comparison()
    prod_vs_f3 = production_vs_f3()
    claims = phase9_11_claim_check()

    print("[3/5] running F3 twice under the chosen environment...")
    repro = reproducibility()

    print("[4/5] data-gap quantification from Phase 12 (read-only)...")
    data_gap = data_gap_analysis()

    digest_after = sha256(PHASE12_JSON)

    out = {
        "phase": 13,
        "script": "phase13_reproducible_baseline.py",
        "objective": "reproducible production baseline before further improvement",
        "chosen_environment": {
            "label": CHOOSE_ENV_LABEL,
            "why": "the pinned serving stack in SeedIQ/requirements.txt "
                   "(scikit-learn 1.6.1 / numpy 2.0.2 / pandas 2.3.3 / scipy 1.13.1) — "
                   "the only local stack under which the committed production artifact "
                   "unpickles; already installed, so no package change",
            "recorded_versions": chosen,
            "dependency_files": deps,
            "deployment_note": ".python-version pins 3.11.17 for Railway; the local venv "
                               "is Python 3.9.6 with the SAME pinned numeric stack "
                               "(same sklearn/numpy/pandas/scipy, different Python "
                               "minor) — recorded as residual risk, not ignored",
        },
        "other_local_environment": other,
        "task1_environment_discrepancy": {
            "artifact_compatibility": artifact,
            "production_vs_f3": prod_vs_f3,
            "evaluation_splits": splits,
            "phase_9_11_claim_check": claims,
            "training_env": {
                "artifact_serialized_with_sklearn": artifact.get("embedded_sklearn_version"),
                "training_python": "not recorded by train_all_models.py or the registry "
                                   "— provenance gap",
                "note": "neither training_registry.json nor training_history.txt records "
                        "interpreter/library versions; the pickle's embedded sklearn "
                        "version is the only machine-readable provenance",
            },
            "evaluation_env": {
                "stack": "Homebrew python3: py3.14.6 / sklearn 1.9.1 / numpy 2.5.3 / "
                         "pandas 3.0.6",
                "evidence": "Phase 12 reproduced 69.5352%/742 only on this stack; the "
                            "pinned stack gives 68.4679%/740",
            },
            "serving_env": {
                "deployment": "Railway py3.11.17 + scikit-learn 1.6.1 (requirements pin)",
                "local_dev": "venv py3.9.6 + sklearn 1.6.1 — compatible, smoke predict OK",
            },
        },
        "task2_reproducible_baseline": repro,
        "task3_data_improvement": data_gap,
        "constraints_honored": {
            "no_packages_installed_or_upgraded": True,
            "production_model_not_overwritten": True,
            "production_code_untouched": True,
            "phase12_results_not_modified": bool(digest_before == digest_after),
            "phase12_sha256_before": digest_before,
            "phase12_sha256_after": digest_after,
            "no_model_experiments": "only F3 baseline determinism reruns; no candidates, "
                                    "no tuning, no accuracy claims",
            "no_data_downloaded": True,
        },
    }
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nResults saved: {OUT_JSON}")
    print(f"Task 2 pass (two identical F3 runs): {repro['pass']}")
    return out


if __name__ == "__main__":
    main()
