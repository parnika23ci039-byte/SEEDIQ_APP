"""Experimental district-level yield model (Crop + District -> tonnes/hectare).

Why this exists
---------------
The served yield model's contract is ``Crop + Area_Hectares -> Yield_Tonnes``
where ``Area_Hectares`` comes from the ICRISAT **district-level annual
statistics**. Two consequences follow, and both are measured here rather than
asserted:

1. *The training inputs cannot distinguish outcomes.* ``Crop + Area`` carries no
   location and no season, so the retraining experiment found a hard ceiling on
   the +/-25% rate. ``District`` is the one extra real input the source table
   actually contains.
2. *The area is a district aggregate used as model input.* The served per-hectare
   figure is ``exp(inner.predict(X))`` after dividing out the requested area, so
   the reported t/ha still moves with whatever area the client sends — including
   a farmer's 2 ha field. This script quantifies that sensitivity instead of
   assuming it away.

What it trains
--------------
``PerHectareRegressor``: HistGradientBoostingRegressor fitted on
``log(yield per hectare)`` using **Crop + District** one-hot features. Area is
NOT a feature, so the per-hectare estimate is area-independent by construction;
total tonnes is then the honest arithmetic product ``t/ha x field area`` from
``yield_semantics.py``.

Evaluation is grouped (no district-year straddles the split) and reported for two
generalisation regimes, because they answer different questions:

* ``unseen_district_years`` — new (district, year) pairs of districts the model
  has already seen: the everyday case.
* ``unseen_districts`` — districts held out entirely: what happens in a district
  the model never trained on. Reported so a district-level claim cannot be read
  as a field-level guarantee.

Outputs (all experimental, none replaces a production artifact):
    models/experimental/district_yield_model.pkl
    models/experimental/district_yield_manifest.json
    ../experiments/district_yield/district_yield_metrics.json

Run from SeedIQ/:
    /Users/apple/SeedIQ/.freebuff/venv/bin/python train_district_yield_model.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupShuffleSplit

# This script lives in SeedIQ/, so the analysis modules import cleanly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yield_semantics import (  # noqa: E402
    BASIS_DISTRICT_AGGREGATE,
    UNIT_YIELD_PER_HECTARE as UNIT_YIELD_PER_HA,
    per_hectare_from_total,
)
# The estimator lives in its own module so the artifact unpickles outside this
# script (a class defined in __main__ does not).
from yield_model_experimental import make_per_hectare_model  # noqa: E402

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
DATA_PATH = os.path.join(SCRIPT_DIR, "data", "yield_icrisat_karnataka.csv")
ARTIFACT_DIR = os.path.join(SCRIPT_DIR, "models", "experimental")
RESULT_DIR = os.path.join(REPO_DIR, "experiments", "district_yield")
PRODUCTION_MODEL_PATH = os.path.join(SCRIPT_DIR, "models", "yield_prediction",
                                     "randomforest_model.pkl")
PRODUCTION_MANIFEST_PATH = os.path.join(SCRIPT_DIR, "models", "yield_feature_manifest.json")

RANDOM_STATE = 42
TEST_SPLIT = 0.20
TOLERANCE = 0.25


def make_model():
    return make_per_hectare_model(RANDOM_STATE)


# --------------------------------------------------------------------------- #
# Features
# --------------------------------------------------------------------------- #
def one_hot(frame: pd.DataFrame, column: str, vocabulary: List[str], prefix: str) -> pd.DataFrame:
    values = frame[column].astype(str)
    out = pd.DataFrame(
        {f"{prefix}_{value}": (values == value).astype(float) for value in vocabulary},
        index=frame.index,
    )
    unknown = ~values.isin(vocabulary)
    if unknown.any():
        raise ValueError(
            f"{int(unknown.sum())} row(s) carry a {column} value outside the vocabulary "
            f"({sorted(set(values[unknown]))[:5]}). The experimental contract requires "
            f"crop and district to come from the training vocabulary."
        )
    return out


def build_features(frame: pd.DataFrame, crops: List[str], districts: List[str]) -> pd.DataFrame:
    features = pd.concat(
        [one_hot(frame, "Crop", crops, "Crop"), one_hot(frame, "District", districts, "District")],
        axis=1,
    )
    return features.astype(float)


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def hit_rate_within(pred_per_ha, true_per_ha, tolerance=TOLERANCE) -> float:
    pred = np.asarray(pred_per_ha, dtype=float)
    true = np.asarray(true_per_ha, dtype=float)
    ok = np.abs(pred - true) <= tolerance * np.abs(true)
    return float(ok.mean())


def regression_report(y_true_per_ha, y_pred_per_ha) -> Dict[str, Any]:
    return {
        "n": int(len(y_true_per_ha)),
        "r2": round(float(r2_score(y_true_per_ha, y_pred_per_ha)), 6),
        "mae_per_ha": round(float(mean_absolute_error(y_true_per_ha, y_pred_per_ha)), 6),
        "within_25pct": round(hit_rate_within(y_pred_per_ha, y_true_per_ha), 6),
    }


def crop_constant_report(frame: pd.DataFrame, train_idx, test_idx) -> Dict[str, Any]:
    """Median-per-hectare-per-crop baseline: the floor any model must beat."""
    per_ha = frame["Yield_Tonnes"].to_numpy(dtype=float) / frame["Area_Hectares"].to_numpy(dtype=float)
    train = frame.iloc[train_idx].copy()
    train["_per_ha"] = per_ha[train_idx]
    medians = train.groupby("Crop")["_per_ha"].median()
    test = frame.iloc[test_idx]
    pred = test["Crop"].map(medians).to_numpy(dtype=float)
    true = per_ha[test_idx]
    if np.isnan(pred).any():
        pred = np.where(np.isnan(pred), float(np.median(medians)), pred)
    return regression_report(true, pred)


# --------------------------------------------------------------------------- #
# Production-model baselines on the SAME rows
# --------------------------------------------------------------------------- #
def load_production_model():
    import joblib
    if not os.path.exists(PRODUCTION_MODEL_PATH):
        return None, None
    model = joblib.load(PRODUCTION_MODEL_PATH)
    manifest = None
    if os.path.exists(PRODUCTION_MANIFEST_PATH):
        with open(PRODUCTION_MANIFEST_PATH, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    return model, manifest


def production_features(frame: pd.DataFrame, manifest: Dict[str, Any]) -> pd.DataFrame:
    columns = list(manifest["feature_columns"])
    crops = list(manifest.get("crop_options") or [])
    matrix = pd.DataFrame(0.0, index=frame.index, columns=columns)
    matrix["Area_Hectares"] = frame["Area_Hectares"].to_numpy(dtype=float)
    for crop in crops:
        name = f"Crop_{crop}"
        if name in matrix.columns:
            matrix[name] = (frame["Crop"].astype(str) == crop).astype(float)
    return matrix[columns].astype(float)


def area_sensitivity_probe(model, manifest) -> Dict[str, Any]:
    """Measure how much the served per-hectare figure moves with the input area.

    The served artifact predicts ``exp(inner)*area`` and the API divides by the
    requested area, so the reported t/ha is ``exp(inner.predict(X))`` while the
    area remains a model *feature*. This probe feeds the same crop at areas
    spanning the recorded district range and records the per-hectare spread.
    """
    crops = list(manifest.get("crop_options") or [])
    areas = [10.0, 100.0, 1000.0, 9100.0, 100000.0, 612300.0]
    probe_columns = list(manifest["feature_columns"])
    results: Dict[str, Any] = {}
    for crop in crops:
        per_ha = []
        for area in areas:
            row = {column: 0.0 for column in probe_columns}
            row["Area_Hectares"] = area
            if f"Crop_{crop}" in row:
                row[f"Crop_{crop}"] = 1.0
            frame = pd.DataFrame([[row[column] for column in probe_columns]],
                                 columns=probe_columns)
            total = float(model.predict(frame)[0])
            per_ha.append(per_hectare_from_total(total, area))
        lo, hi = min(per_ha), max(per_ha)
        results[crop] = {
            "areas_hectares": areas,
            "per_hectare": [round(v, 6) for v in per_ha],
            "min": round(lo, 6),
            "max": round(hi, 6),
            "relative_spread": round((hi - lo) / hi, 6) if hi else None,
        }
    worst = max(results.items(), key=lambda kv: kv[1]["relative_spread"] or 0.0)
    return {
        "question": (
            "Does the served per-hectare figure depend on the area the client sends?"
        ),
        "areas_hectares": areas,
        "per_crop": results,
        "max_relative_spread": worst[1]["relative_spread"],
        "max_relative_spread_crop": worst[0],
        "interpretation": (
            "The served contract treats the area as a model feature trained on district "
            "aggregates, so the reported tonnes/hectare moves with the requested area for "
            "the same crop. The experimental district model fixes this: its per-hectare "
            "estimate is a function of Crop + District only."
        ),
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    started = time.time()
    print("=" * 78)
    print("SEEDIQ EXPERIMENTAL DISTRICT-LEVEL YIELD MODEL")
    print("=" * 78)

    if not os.path.exists(DATA_PATH):
        print(f"[FATAL] dataset missing: {DATA_PATH}")
        return 1

    frame = pd.read_csv(DATA_PATH)
    required = ["Crop", "District", "Year", "Area_Hectares", "Yield_Tonnes"]
    missing = [c for c in required if c not in frame.columns]
    if missing:
        print(f"[FATAL] dataset is missing {missing}")
        return 1
    frame = frame.dropna(subset=required).reset_index(drop=True)
    per_ha_all = (frame["Yield_Tonnes"].to_numpy(dtype=float)
                  / frame["Area_Hectares"].to_numpy(dtype=float))

    crops = sorted(frame["Crop"].astype(str).unique())
    districts = sorted(frame["District"].astype(str).unique())
    features = build_features(frame, crops, districts)
    features["Crop_str"] = frame["Crop"].astype(str)
    features["District_str"] = frame["District"].astype(str)
    feature_matrix = features.drop(columns=["Crop_str", "District_str"])

    print(f"dataset            : {os.path.relpath(DATA_PATH, SCRIPT_DIR)}")
    print(f"rows               : {len(frame)} | crops {len(crops)} | districts {len(districts)}")
    print(f"per-hectare yield  : median {np.median(per_ha_all):.4f} t/ha "
          f"(min {per_ha_all.min():.4f}, max {per_ha_all.max():.4f})")
    print(f"input features     : {feature_matrix.shape[1]} (Crop + District one-hot; no area)")

    results: Dict[str, Any] = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dataset": os.path.relpath(DATA_PATH, REPO_DIR),
        "dataset_provenance": "real ICRISAT Karnataka district-level annual statistics",
        "dataset_synthetic": False,
        "contract": {
            "inputs": ["crop", "district"],
            "target": "yield per hectare (tonnes/hectare)",
            "area_is_a_feature": False,
            "season_supported": False,
            "basis": BASIS_DISTRICT_AGGREGATE,
            "units": UNIT_YIELD_PER_HA,
        },
        "rows": int(len(frame)),
        "crops": crops,
        "districts": districts,
        "feature_count": int(feature_matrix.shape[1]),
        "tolerance": TOLERANCE,
        "regimes": {},
    }

    regimes = [
        ("unseen_district_years", frame["District"].astype(str) + "|" + frame["Year"].astype(str)),
        ("unseen_districts", frame["District"].astype(str)),
    ]

    fitted_models: Dict[str, Any] = {}
    for name, groups in regimes:
        splitter = GroupShuffleSplit(n_splits=1, test_size=TEST_SPLIT, random_state=RANDOM_STATE)
        train_idx, test_idx = next(splitter.split(frame, per_ha_all, groups))
        train_groups, test_groups = set(groups[train_idx]), set(groups[test_idx])
        assert not (train_groups & test_groups), f"{name}: grouped split leaked a group"

        X_train = feature_matrix.iloc[train_idx].to_numpy(dtype=float)
        X_test = feature_matrix.iloc[test_idx].to_numpy(dtype=float)
        y_train, y_test = per_ha_all[train_idx], per_ha_all[test_idx]

        model = make_model().fit(X_train, y_train)
        pred_test = model.predict(X_test)
        pred_train = model.predict(X_train)

        entry = {
            "groups_total": int(len(set(groups))),
            "groups_train": int(len(train_groups)),
            "groups_test": int(len(test_groups)),
            "rows_train": int(len(train_idx)),
            "rows_test": int(len(test_idx)),
            "test": regression_report(y_test, pred_test),
            "train_fit": regression_report(y_train, pred_train),
            "crop_constant_median_baseline_test": crop_constant_report(frame, train_idx, test_idx),
            "split_disjoint": True,
        }

        if name == "unseen_district_years":
            prod_model, prod_manifest = load_production_model()
            if prod_model is not None and prod_manifest is not None:
                prod_frame = production_features(frame, prod_manifest)
                prod_pred_total = prod_model.predict(prod_frame.iloc[test_idx])
                prod_per_ha = (np.asarray(prod_pred_total, dtype=float)
                               / frame["Area_Hectares"].to_numpy(dtype=float)[test_idx])
                entry["served_model_test"] = regression_report(y_test, prod_per_ha)
                entry["served_model_contract"] = {
                    "inputs": prod_manifest.get("input_schema"),
                    "area_is_a_feature": True,
                    "artifact": os.path.relpath(PRODUCTION_MODEL_PATH, SCRIPT_DIR),
                }
            # Crop-only (no area, no district): isolates the district gain from
            # the removal of the area feature.
            crop_only = pd.DataFrame(
                {f"Crop_{c}": (frame["Crop"].astype(str) == c).astype(float) for c in crops}
            ).to_numpy(dtype=float)
            crop_only_model = make_model().fit(crop_only[train_idx], y_train)
            entry["crop_only_no_area_test"] = regression_report(
                y_test, crop_only_model.predict(crop_only[test_idx]))

        results["regimes"][name] = entry
        fitted_models[name] = model

        print(f"\n[{name}] groups {entry['groups_train']} train / {entry['groups_test']} test | "
              f"rows {entry['rows_train']}/{entry['rows_test']}")
        print(f"  district model test     : R2 {entry['test']['r2']:.4f} | "
              f"MAE {entry['test']['mae_per_ha']:.4f} t/ha | "
              f"within +/-25% {entry['test']['within_25pct'] * 100:.2f}%")
        print(f"  district model train-fit: within +/-25% "
              f"{entry['train_fit']['within_25pct'] * 100:.2f}% (R2 {entry['train_fit']['r2']:.4f})")
        print(f"  crop-median baseline    : within +/-25% "
              f"{entry['crop_constant_median_baseline_test']['within_25pct'] * 100:.2f}%")
        if "served_model_test" in entry:
            served = entry["served_model_test"]
            print(f"  served Crop+Area model  : within +/-25% "
                  f"{served['within_25pct'] * 100:.2f}% (R2 {served['r2']:.4f})")
            print(f"  crop-only (no area)     : within +/-25% "
                  f"{entry['crop_only_no_area_test']['within_25pct'] * 100:.2f}%")

    prod_model, prod_manifest = load_production_model()
    if prod_model is not None and prod_manifest is not None:
        probe = area_sensitivity_probe(prod_model, prod_manifest)
        results["served_model_area_sensitivity"] = probe
        print(f"\narea-sensitivity of the served model: max relative spread "
              f"{probe['max_relative_spread'] * 100:.2f}% "
              f"({probe['max_relative_spread_crop']}) across "
              f"{probe['areas_hectares']} ha")

    # ---- persistence (experimental namespace only) ------------------------- #
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    os.makedirs(RESULT_DIR, exist_ok=True)

    import joblib
    artifact_path = os.path.join(ARTIFACT_DIR, "district_yield_model.pkl")
    joblib.dump(fitted_models["unseen_district_years"], artifact_path)
    manifest = {
        "generated": results["generated"],
        "contract": results["contract"],
        "input_schema": ["crop", "district"],
        "target": "yield per hectare",
        "units": UNIT_YIELD_PER_HA,
        "crop_options": crops,
        "district_options": districts,
        "crop_feature_prefix": "Crop",
        "district_feature_prefix": "District",
        "feature_count": results["feature_count"],
        "feature_columns": list(feature_matrix.columns),
        "area_is_a_feature": False,
        "season_supported": False,
        "dataset": results["dataset"],
        "dataset_provenance": results["dataset_provenance"],
        "dataset_synthetic": False,
        "semantics": (
            "District-level estimate. Inputs are crop and district only; there is no "
            "area term, no season term and no year term. Predictions are tonnes per "
            "hectare for a district-level annual average, NOT field-level measurements "
            "and NOT live data."
        ),
        "validation": {
            name: {
                "test_within_25pct": entry["test"]["within_25pct"],
                "test_r2": entry["test"]["r2"],
                "rows_test": entry["rows_test"],
            }
            for name, entry in results["regimes"].items()
        },
        "artifact": os.path.relpath(artifact_path, SCRIPT_DIR),
    }
    manifest_path = os.path.join(ARTIFACT_DIR, "district_yield_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=False)

    results["artifact"] = os.path.relpath(artifact_path, REPO_DIR)
    results["manifest"] = os.path.relpath(manifest_path, REPO_DIR)
    metrics_path = os.path.join(RESULT_DIR, "district_yield_metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2, sort_keys=False)

    print(f"\nartifact : {os.path.relpath(artifact_path, REPO_DIR)}")
    print(f"manifest : {os.path.relpath(manifest_path, REPO_DIR)}")
    print(f"metrics  : {os.path.relpath(metrics_path, REPO_DIR)}")
    print(f"done in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
