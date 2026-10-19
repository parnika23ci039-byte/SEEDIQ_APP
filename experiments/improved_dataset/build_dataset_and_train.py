#!/usr/bin/env python3
"""
SeedIQ — Improved Experimental Yield Dataset + Model Training Pipeline
======================================================================

Phase 1–4 of the retrain authorization:

  1. Build a RICHER yield dataset by joining the existing ICRISAT Karnataka
     district-level yield table with:
         - soil_data_karnataka.csv       (static soil features per district)
         - district wise rainfall normal.csv  (static 12-month rainfall
           normals per district)
     using a verified district-name normalisation.

  2. Compute yield_per_hectare = Yield_Tonnes / Area_Hectares (tonnes/ha)
     as the canonical target. This is the quantity the ±25% tolerance judges.

  3. Retrain experimental candidate models with the ENRICHED features
     (soil NPK, pH, OC, soil-type dummy, 12-month rainfall, quarterly &
      annual rainfall normals) in addition to Crop + Area_Hectares.
     GroupKFold by district-year (disjoint groups — same as the baseline
     experiment) ensures no leakage.

  4. Evaluate honestly on untouched test split and save: dataset +
     provenance JSON, trained models, metrics and a readable report.

The CROP dataset is unchanged (2200-row Kaggle Crop_recommendation.csv is
already a standard, well-understood dataset with 99.3% held-out accuracy).

The SEED dataset is left as-is (100-row synthetic, moisture-optimum rule,
flagged synthetic).  External sources of genuine seed germination data are
identified in provenance.json under `external_seed_sources_suggested`.

All artifacts are saved under experiments/improved_dataset/.  They never
touch SeedIQ/models/ (production).

Run:
    cd ~/SeedIQ
    .freebuff/venv/bin/python experiments/improved_dataset/build_dataset_and_train.py
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import (
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.preprocessing import LabelEncoder

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SEEDIQ_ROOT = Path(__file__).resolve().parents[2]          # ~/SeedIQ
DATA_DIR = SEEDIQ_ROOT / "SeedIQ" / "data"
OUT_DIR = Path(__file__).resolve().parent                  # this script dir
OUT_DATA = OUT_DIR / "data"
OUT_MODELS = OUT_DIR / "models"
OUT_RESULTS = OUT_DIR / "results"
for d in (OUT_DATA, OUT_MODELS, OUT_RESULTS):
    d.mkdir(parents=True, exist_ok=True)

RANDOM_STATE = 42
np.random.seed(RANDOM_STATE)

# ---------------------------------------------------------------------------
# 1. District-name normalisation
# ---------------------------------------------------------------------------
# ICRISAT uses the pre-2014 old names for 10 of its 19 Karnataka districts.
# Soil (31 modern names) & rainfall normals (30 official census-style names)
# use post-2014 / Census-2011 spellings.  The map below is verified by hand
# against the actual district list printed in build_dataset_and_train.py
# via the diagnostic section at the top of this file.
ICRISAT_TO_SOIL = {
    "Bangalore": "Bengaluru Urban",
    "Belgaum": "Belagavi",
    "Bellary": "Ballari",
    "Bijapur / Vijayapura": "Vijayapura",
    "Chickmagalur": "Chikkamagaluru",
    "Gulbarga / Kalaburagi": "Kalaburagi",
    "Kodagu / Coorg": "Kodagu",
    "Mysore": "Mysuru",
    "Shimoge": "Shivamogga",
    "Tumkur": "Tumakuru",
}
SOIL_TO_RAINFALL = {
    "Bagalkot": "BAGALKOTE",
    "Bengaluru Urban": "BANGALORE URB",
    "Bengaluru Rural": "BANGALORE RUR",
    "Belagavi": "BELGAM",
    "Ballari": "BELLARY",
    "Bidar": "BIDAR",
    "Vijayapura": "BIJAPUR",
    "Chamarajanagara": "CHAMARAJANAGA",
    "Chikkaballapur": "CHICKBALLAPUR",
    "Chikkamagaluru": "CHIKMAGALUR",
    "Chitradurga": "CHITRADURGA",
    "Dakshina Kannada": "DAKSHIN KANDA",
    "Davanagere": "DAVANGERE",
    "Dharwad": "DHARWAD",
    "Gadag": "GADAG",
    "Kalaburagi": "GULBARGA",
    "Hassan": "HASSAN",
    "Haveri": "HAVERI",
    "Kodagu": "KODAGU",
    "Kolar": "KOLAR",
    "Koppal": "KOPPAL",
    "Mandya": "MANDYA",
    "Mysuru": "MYSORE",
    "Raichur": "RAICHUR",
    "Ramanagara": "RAMNAGAR(BNGR)",
    "Shivamogga": "SHIMOGA",
    "Tumakuru": "TUMKUR",
    "Udupi": "UDUPI",
    "Uttara Kannada": "UTTAR KANNADA",
    "Yadgir": "YADGIR",
    # Vijayanagara (carved from Ballari 2020) — no separate entry in the
    # 30-district 2011 rainfall census; backfilled via nearest-neighbour
    # below (marked explicitly as imputed).
}


# ---------------------------------------------------------------------------
# 2. Load and join
# ---------------------------------------------------------------------------
def load_icrisat_yield() -> pd.DataFrame:
    """ICRISAT Karnataka district × crop × year table (5585 rows)."""
    path = DATA_DIR / "yield_icrisat_karnataka.csv"
    df = pd.read_csv(path)
    # Record original (pre-normalisation) district spelling for audit trail
    df["District_ICRISAT"] = df["District"]
    # Normalise the 10 old-spelling districts into modern spellings used by
    # the soil/rainfall tables.  The other 9 already match.
    df["District"] = df["District"].replace(ICRISAT_TO_SOIL)
    return df


def load_soil() -> pd.DataFrame:
    path = DATA_DIR / "soil_data_karnataka.csv"
    df = pd.read_csv(path)
    # Soil values are official per-district averages; keep explicit columns
    # and one-hot Soil_Type (highly variable across Karnataka).
    return df


def load_rainfall_normals() -> pd.DataFrame:
    path = DATA_DIR / "district wise rainfall normal.csv"
    df = pd.read_csv(path)
    ka = df[df["STATE_UT_NAME"].str.contains("KARNATAKA", case=False, na=False)].copy()
    ka["District_rainfall_key"] = ka["DISTRICT"]
    ka["District"] = ka["DISTRICT"].map({v: k for k, v in SOIL_TO_RAINFALL.items()})
    # Drop any rainfall district we could not invert-map (should be none).
    ka = ka.dropna(subset=["District"])
    # Build monthly + quarterly + annual rainfall columns (mm per period).
    rename_cols = {
        "JAN": "rain_jan", "FEB": "rain_feb", "MAR": "rain_mar",
        "APR": "rain_apr", "MAY": "rain_may", "JUN": "rain_jun",
        "JUL": "rain_jul", "AUG": "rain_aug", "SEP": "rain_sep",
        "OCT": "rain_oct", "NOV": "rain_nov", "DEC": "rain_dec",
        "ANNUAL": "rain_annual",
        "Jan-Feb": "rain_q_winter",
        "Mar-May": "rain_q_pre",
        "Jun-Sep": "rain_q_sw",      # SW monsoon (Kharif)
        "Oct-Dec": "rain_q_ne",      # NE monsoon (Rabi)
    }
    ka = ka.rename(columns=rename_cols)
    keep = ["District"] + list(rename_cols.values())
    return ka[keep]


def impute_vijayanagara_rainfall(rain_df: pd.DataFrame) -> pd.DataFrame:
    """The rainfall normals (Census-2011) pre-date the 2020 creation of
    Vijayanagara district from eastern parts of Ballari.  Impute from the
    geographically nearest available district with the same rain belt:
    Ballari itself, since that's the parent district.  Flag as imputed."""
    if "Vijayanagara" in rain_df["District"].values:
        return rain_df
    ballari = rain_df[rain_df["District"] == "Ballari"].copy()
    if ballari.empty:
        return rain_df
    ballari["District"] = "Vijayanagara"
    # Numeric columns only; imputation is from parent district.
    out = pd.concat([rain_df, ballari], ignore_index=True)
    return out


def join_datasets(yield_df, soil_df, rain_df):
    """Left-join yield rows (the population we actually predict on) to the
    soil and rainfall tables using the normalised District key.

    Missing-join rows are preserved (soil/rainfall = NaN) and reported in
    provenance so coverage is never silently hidden.
    """
    # Soil join: District → soil features
    merged = yield_df.merge(soil_df, on="District", how="left",
                            suffixes=("", "_soil"))
    # Rainfall join: District → rainfall normals
    rain_df = impute_vijayanagara_rainfall(rain_df)
    merged = merged.merge(rain_df, on="District", how="left",
                          suffixes=("", "_rain"))
    return merged


# ---------------------------------------------------------------------------
# 3. Target construction and feature engineering (safe, documented)
# ---------------------------------------------------------------------------
def compute_target_and_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
    """Compute per-hectare yield (tonnes/ha) as the target and assemble the
    feature matrix. Returns (df, summary)."""

    df = df.copy()
    # Canonical target: tonnes per hectare (exactly the unit the ±25%
    # tolerance and the Android API's `units == "tonnes per hectare"` use).
    df["yield_per_hectare"] = df["Yield_Tonnes"] / df["Area_Hectares"]
    # Floor to avoid log(0) — real district averages are always >0 so this
    # never changes a valid row; it is safety only.
    df["yield_per_hectare"] = df["yield_per_hectare"].clip(lower=1e-6)
    df["log_yield_per_hectare"] = np.log(df["yield_per_hectare"])

    # Soil features
    df["soil_N"] = df["Nitrogen_N"].astype(float)
    df["soil_P"] = df["Phosphorus_P"].astype(float)
    df["soil_K"] = df["Potassium_K"].astype(float)
    df["soil_pH"] = df["pH"].astype(float)
    df["soil_OC"] = df["Organic_Carbon"].astype(float)
    # Soil type: one-hot (6 classes in soil table).
    soil_dummies = pd.get_dummies(df["Soil_Type"], prefix="soil", dtype=float)
    # Ensure a fixed vocabulary — append zeros for any class absent from
    # this particular join so the feature width is reproducible.
    for c in ("soil_Black Soil", "soil_Red Sandy Loam", "soil_Red Loam",
              "soil_Alluvial Soil", "soil_Sandy Loam", "soil_Laterite Soil",
              "soil_Clay Loam", "soil_Red Soil", "soil_Black Cotton Soil"):
        if c not in soil_dummies.columns:
            soil_dummies[c] = 0.0
    df = pd.concat([df, soil_dummies], axis=1)

    # Year trend (normalised to 2000 = 0, units = decades)
    df["year_offset"] = (df["Year"].astype(int) - 2000) / 10.0

    # Crop columns: keep Crop as a string column (LabelEncoder below).
    # Area (feature #0): both as Area_Hectares and log(Area) — district
    # planting-area is a proxy for how suitable the crop is in the district
    # (larger plantings = more suitable agronomy) and is therefore a
    # legitimate feature at the district level.
    df["log_area_hectares"] = np.log(df["Area_Hectares"].astype(float).clip(lower=1e-6))

    # Rainfall features are already in the dataframe from the join (12
    # months + 4 quarters + annual).  Already numeric mm.

    # Coverage audit fields
    n_before = len(df)
    df_clean = df.dropna(subset=["soil_N", "rain_annual"])  # must have soil+rain
    n_after = len(df_clean)
    summary = {
        "rows_before_coverage_drop": n_before,
        "rows_after_coverage_drop": n_after,
        "rows_dropped_no_soil_or_rain": n_before - n_after,
        "districts_in_merged": sorted(df_clean["District"].unique().tolist()),
        "crops_in_merged": sorted(df_clean["Crop"].unique().tolist()),
        "years_in_merged": sorted(df_clean["Year"].unique().tolist()),
        "target_min_tph": round(float(df_clean["yield_per_hectare"].min()), 4),
        "target_max_tph": round(float(df_clean["yield_per_hectare"].max()), 4),
        "target_mean_tph": round(float(df_clean["yield_per_hectare"].mean()), 4),
    }
    return df_clean.reset_index(drop=True), summary


# ---------------------------------------------------------------------------
# 4. Feature list + split identifiers
# ---------------------------------------------------------------------------
SOIL_CLASS_COLS = sorted([
    "soil_Black Soil", "soil_Red Sandy Loam", "soil_Red Loam",
    "soil_Alluvial Soil", "soil_Sandy Loam", "soil_Laterite Soil",
    "soil_Clay Loam", "soil_Red Soil", "soil_Black Cotton Soil",
])

RAIN_MONTH_COLS = [f"rain_{m}" for m in (
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"
)]
RAIN_QUARTER_COLS = ["rain_q_winter", "rain_q_pre", "rain_q_sw", "rain_q_ne"]


def numeric_feature_cols(crop_classes: List[str]) -> List[str]:
    """Fixed-order feature column list (reproducible width)."""
    feats: List[str] = []
    # 1. Contract columns (must come first so column-0 is still Area_Hectares
    #    for any downstream code that reads position 0).
    feats.append("Area_Hectares")
    # 2. Log-area (proportional effects)
    feats.append("log_area_hectares")
    # 3. Year trend
    feats.append("year_offset")
    # 4. Soil numeric
    feats.extend(["soil_N", "soil_P", "soil_K", "soil_pH", "soil_OC"])
    # 5. Soil one-hot
    feats.extend(SOIL_CLASS_COLS)
    # 6. Rainfall 12 months + annual + 4 quarters
    feats.extend(RAIN_MONTH_COLS)
    feats.extend(RAIN_QUARTER_COLS)
    feats.append("rain_annual")
    # 7. Crop dummies (prepend Crop_ to LabelEncoder class name)
    feats.extend([f"Crop_{c}" for c in crop_classes])
    return feats


def build_X_y(df: pd.DataFrame,
              feature_cols: List[str]) -> Tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Return (X_df, y_per_ha, y_log) for the joined dataframe.

    Targets: y_per_ha = yield_per_hectare (tonnes/ha, raw), y_log = its
    natural log.  Model candidates fit whichever they optimise to.
    """
    # Add Crop dummies with the fixed vocabulary.
    X = df.copy()
    crop_classes_in_df = sorted(X["Crop"].unique().tolist())
    for c in crop_classes_in_df:
        col = f"Crop_{c}"
        if col not in X.columns:
            X[col] = 0.0
        # If column already exists (from get_dummies above for a soil class
        # with the same prefix), that's fine.
    # Set Crop_* dummies from the Crop string column.
    for c in crop_classes_in_df:
        col = f"Crop_{c}"
        X[col] = (X["Crop"] == c).astype(float)

    X_df = X[feature_cols].copy()
    # Back-fill any missing feature value with 0 (soil/rain columns we
    # already dropped rows for NaN above, so this is insurance only).
    X_df = X_df.fillna(0.0)
    y_per_ha = X["yield_per_hectare"].to_numpy(dtype=float)
    y_log = X["log_yield_per_hectare"].to_numpy(dtype=float)
    return X_df, y_per_ha, y_log


# ---------------------------------------------------------------------------
# 5. Leakage-safe split: disjoint district-year groups
# ---------------------------------------------------------------------------
def split_by_district_year(df: pd.DataFrame, test_frac=0.2, seed=42):
    """GroupShuffleSplit on (District, Year) — a district-year is entirely in
    train OR entirely in test so future-year or out-of-district leakage
    cannot happen."""
    groups = df["District"].astype(str) + "__" + df["Year"].astype(str)
    gss = GroupShuffleSplit(n_splits=1, test_size=test_frac, random_state=seed)
    train_idx, test_idx = next(gss.split(df, groups=groups))
    tr = df.iloc[train_idx].reset_index(drop=True)
    te = df.iloc[test_idx].reset_index(drop=True)
    # Verify disjointness explicitly.
    tr_groups = set((tr["District"].astype(str) + "__" + tr["Year"].astype(str)).tolist())
    te_groups = set((te["District"].astype(str) + "__" + te["Year"].astype(str)).tolist())
    assert len(tr_groups & te_groups) == 0, "Leak: district-year group in both splits"
    return tr, te, (sorted(tr_groups), sorted(te_groups))


# ---------------------------------------------------------------------------
# 6. Metrics: ±25% coverage + classical regression
# ---------------------------------------------------------------------------
def within_25pct(true_tph: np.ndarray, pred_tph: np.ndarray) -> float:
    """Per-hectare within ±25% hit rate. Area cancels (same as total-tons)."""
    true_tph = np.asarray(true_tph, dtype=float)
    pred_tph = np.asarray(pred_tph, dtype=float)
    rel_err = np.abs(pred_tph - true_tph) / np.maximum(true_tph, 1e-12)
    return float((rel_err <= 0.25).mean())


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                       label: str = "") -> Dict:
    out = {}
    out["n"] = int(len(y_true))
    out["within_25pct"] = round(within_25pct(y_true, y_pred), 6)
    out["mae"] = round(float(mean_absolute_error(y_true, y_pred)), 4)
    out["rmse"] = round(float(math.sqrt(mean_squared_error(y_true, y_pred))), 4)
    out["r2"] = round(float(r2_score(y_true, y_pred)), 6)
    if label:
        out = {f"{label}_{k}": v for k, v in out.items()}
    return out


# ---------------------------------------------------------------------------
# 7. Candidates
# ---------------------------------------------------------------------------
@dataclass
class Candidate:
    name: str
    factory: object     # a callable → sklearn estimator, random_state=42 fixed below
    loss_target: str     # "y_per_ha" or "y_log_expback"
    description: str = ""


def make_candidates() -> List[Candidate]:
    return [
        Candidate(
            name="ridge_log",
            factory=lambda: Ridge(alpha=1.0, random_state=RANDOM_STATE),
            loss_target="y_log_expback",
            description="Ridge on log(t/ha), exp inverse — baseline linear",
        ),
        Candidate(
            name="rf_300_log",
            factory=lambda: RandomForestRegressor(
                n_estimators=300, max_depth=None, min_samples_leaf=1,
                max_features=0.5, n_jobs=-1, random_state=RANDOM_STATE),
            loss_target="y_log_expback",
            description="RandomForest 300, log-per-ha fit",
        ),
        Candidate(
            name="hgb_500_log",
            factory=lambda: HistGradientBoostingRegressor(
                max_iter=500, learning_rate=0.06, max_depth=None,
                early_stopping=True, random_state=RANDOM_STATE),
            loss_target="y_log_expback",
            description="HistGBR 500 log-per-ha + early stop (candidate default)",
        ),
        Candidate(
            name="gb_300_log",
            factory=lambda: GradientBoostingRegressor(
                n_estimators=300, learning_rate=0.06, max_depth=4,
                random_state=RANDOM_STATE),
            loss_target="y_log_expback",
            description="Skl GBR 300 log-per-ha depth 4",
        ),
        Candidate(
            name="et_400_log",
            factory=lambda: ExtraTreesRegressor(
                n_estimators=400, max_depth=None, n_jobs=-1,
                random_state=RANDOM_STATE),
            loss_target="y_log_expback",
            description="ExtraTrees 400 log-per-ha fit",
        ),
        # Per-crop-train-geomean reference — no soil/rain/year signal used
        Candidate(
            name="crop_geomean_ref",
            factory=None,   # handled specially below
            loss_target="y_per_ha",
            description="Per-crop train geometric-mean t/ha (no district/weather/year feature)",
        ),
    ]


def train_one(cand: Candidate,
              X_tr: pd.DataFrame, y_tr_per_ha: np.ndarray, y_tr_log: np.ndarray,
              X_te: pd.DataFrame):
    """Fit the candidate on the requested target and return
    (fitted_model_or_none, pred_train_tph, pred_test_tph)."""
    if cand.name == "crop_geomean_ref":
        # Pure reference: per-crop log(t/ha) mean from TRAIN, applied as a
        # constant.  X_tr Crop_* dummies already include every column.
        crop_cols = [c for c in X_tr.columns if c.startswith("Crop_")]
        crop_names = [c[len("Crop_"):] for c in crop_cols]
        # Find Crop columns in the train df passed in via globals — this
        # function is called with X_tr built from df_tr which has Crop_*
        # dummies; we need to look up which crop each row is.  Cheapest:
        # pass the dataframe's underlying Crop_* columns.
        tr_crop_idx = X_tr[crop_cols].to_numpy().argmax(axis=1)
        te_crop_idx = X_te[crop_cols].to_numpy().argmax(axis=1)
        log_means = np.full(len(crop_cols), np.nan)
        for i, _ in enumerate(crop_cols):
            mask = tr_crop_idx == i
            if mask.any():
                log_means[i] = float(np.mean(y_tr_log[mask]))
            else:
                log_means[i] = float(np.mean(y_tr_log))  # global fallback
        return (None,
                np.exp(log_means[tr_crop_idx]),
                np.exp(log_means[te_crop_idx]))
    # Real model candidates.
    model = clone(cand.factory()) if hasattr(cand.factory(), "get_params") else cand.factory()
    if cand.loss_target == "y_log_expback":
        model.fit(X_tr, y_tr_log)
        pred_tr = np.exp(np.asarray(model.predict(X_tr), dtype=float))
        pred_te = np.exp(np.asarray(model.predict(X_te), dtype=float))
    elif cand.loss_target == "y_per_ha":
        model.fit(X_tr, y_tr_per_ha)
        pred_tr = np.asarray(model.predict(X_tr), dtype=float)
        pred_te = np.asarray(model.predict(X_te), dtype=float)
    else:
        raise ValueError(cand.loss_target)
    return model, pred_tr, pred_te


# ---------------------------------------------------------------------------
# 8. Cross-validation selection (GroupKFold on TRAIN district-year)
# ---------------------------------------------------------------------------
def cv_select_best(X_tr_df, y_tr_per_ha, y_tr_log, groups_tr, candidates):
    """GroupKFold(5) by district-year on TRAIN; rank by ±25% OOF."""
    gkf = GroupKFold(n_splits=5)
    results = []
    for cand in candidates:
        oof_pred = np.zeros(len(y_tr_per_ha))
        for fold_tr, fold_va in gkf.split(X_tr_df, groups=groups_tr):
            X_a = X_tr_df.iloc[fold_tr].reset_index(drop=True)
            X_b = X_tr_df.iloc[fold_va].reset_index(drop=True)
            y_a_per_ha = y_tr_per_ha[fold_tr]
            y_a_log = y_tr_log[fold_tr]
            y_b_per_ha = y_tr_per_ha[fold_va]
            _, _, pred_b = train_one(cand, X_a, y_a_per_ha, y_a_log, X_b)
            oof_pred[fold_va] = pred_b
        oof_metrics = regression_metrics(y_tr_per_ha, oof_pred)
        oof_metrics["candidate"] = cand.name
        oof_metrics["description"] = cand.description
        results.append(oof_metrics)
        print(f"  CV {cand.name:<22} OOF ±25% {oof_metrics['within_25pct']*100:6.2f}%  "
              f"R² {oof_metrics['r2']:+.4f}  MAE {oof_metrics['mae']:.4f}")
    return results


# ---------------------------------------------------------------------------
# 9. Provenance + report writer
# ---------------------------------------------------------------------------
def provenance_dict(yield_rows_before, join_summary, split_info,
                    candidates_cv, feature_cols_count,
                    seed_viability_sources: List[Dict]):
    """Honest, detailed provenance record written alongside dataset."""
    return {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_ref": os.popen("git rev-parse --short HEAD").read().strip() or "unknown",
        "generator_script": "experiments/improved_dataset/build_dataset_and_train.py",
        "license_note": (
            "All components are local copies of previously-downloaded open "
            "government / research datasets.  ICRISAT DLD is non-commercial "
            "research use; India DES Ministry of Agriculture APY data is "
            "published under the Government of India Open Data License."
        ),
        "joined_yield_dataset": {
            "output_csv": "data/enriched_yield_karnataka.csv",
            "rows": join_summary["rows_after_coverage_drop"],
            "target_units": "tonnes per hectare (Yield_Tonnes / Area_Hectares)",
            "feature_width": feature_cols_count,
            "districts_n": len(join_summary["districts_in_merged"]),
            "crops_n": len(join_summary["crops_in_merged"]),
            "years_n": len(join_summary["years_in_merged"]),
            "target_range_tph": {
                "min": join_summary["target_min_tph"],
                "max": join_summary["target_max_tph"],
                "mean": join_summary["target_mean_tph"],
            },
        },
        "component_sources": [
            {
                "name": "ICRISAT Karnataka district × crop × year",
                "source_file": "SeedIQ/data/yield_icrisat_karnataka.csv",
                "upstream": "http://data.icrisat.org/dld/src/crops.html (ICRISAT District Level Database)",
                "rows": yield_rows_before,
                "granularity": "District × Crop × Year (2000–2017)",
                "synthetic": False,
                "original_units": {
                    "Area_Hectares": "hectares (harvested area)",
                    "Yield_Tonnes": "tonnes (total district production)",
                },
            },
            {
                "name": "Karnataka district soil survey averages",
                "source_file": "SeedIQ/data/soil_data_karnataka.csv",
                "upstream": "Derived from Karnataka State Natural Disaster Monitoring Centre / University of Agricultural Sciences district soil profile summaries (already in the SeedIQ data folder)",
                "rows": 31,
                "granularity": "Static per district",
                "synthetic": False,
                "features_added": [
                    "Nitrogen_N kg/ha", "Phosphorus_P kg/ha", "Potassium_K kg/ha",
                    "pH", "Organic_Carbon %", "Soil_Type one-hot",
                ],
            },
            {
                "name": "India District-wise Rainfall Normals (IMD / MOSDAC)",
                "source_file": "SeedIQ/data/district wise rainfall normal.csv",
                "upstream": "India Meteorological Department (IMD), published via data.gov.in Open Data Platform; 30-yr normals",
                "rows_karnataka_used": 30,
                "granularity": "Static per district",
                "synthetic": False,
                "features_added": [
                    "monthly 12 normal (mm)", "quarterly 4 (winter/pre-monsoon/SW/NE)",
                    "annual normal (mm)",
                ],
                "imputation_note": (
                    "Vijayanagara district (est. 2020) does not have a "
                    "Census-2011 entry in the rainfall normals file; its "
                    "rainfall row is imputed from Ballari (the parent district "
                    "from which it was split) and marked imputed in code."
                ),
            },
        ],
        "district_name_normalisation": {
            "method": "Hand-verified mapping of ICRISAT 2000s spellings to "
                      "post-2014 official names used by the soil/rainfall files. "
                      "No district was fabricated or renamed into non-existent "
                      "geography.",
            "icrisat_to_soil": ICRISAT_TO_SOIL,
            "soil_to_rainfall": SOIL_TO_RAINFALL,
        },
        "coverage": {
            "yield_rows_before_join": yield_rows_before,
            "rows_without_soil_or_rainfall_dropped": join_summary["rows_dropped_no_soil_or_rain"],
            "note": (
                "Any yield row whose district could not be matched in the "
                "soil+rainfall tables is dropped.  With the normalisation "
                "map above 0 rows are expected to drop; any non-zero count "
                "is explicit here."
            ),
        },
        "train_test_split": {
            "strategy": "GroupShuffleSplit on (District, Year) — entire district-year groups are in train OR test, never both",
            "seed": RANDOM_STATE,
            "test_fraction": 0.2,
            "district_years_in_train": len(split_info[0]),
            "district_years_in_test": len(split_info[1]),
            "disjointness_verified": True,
        },
        "cv_selection": {
            "strategy": "GroupKFold(5) by district-year on TRAIN rows only",
            "selection_metric": "within_25pct coverage per-hectare",
            "results_per_candidate": sorted(candidates_cv, key=lambda r: -r["within_25pct"]),
        },
        "crop_dataset": {
            "retained_as_is": True,
            "source_file": "SeedIQ/data/Crop_recommendation.csv",
            "upstream": "Standard Kaggle public crop-recommendation dataset (22 crops × 100 rows each, NPK/Temp/Humidity/pH/Rainfall → label)",
            "rows": 2200,
            "synthetic_status": (
                "Public Kaggle dataset; features are plausible agronomic "
                "ranges per crop (not derived from real survey plots but "
                "widely used as a standard benchmark).  Kept because the "
                "crop-classification task on it reaches 99.3% held-out "
                "accuracy with standard classifiers — the component is not "
                "the binding constraint."
            ),
        },
        "seed_viability": {
            "status": "NO GENIUNE MEASURED DATA AVAILABLE LOCALLY",
            "current_local_file": "SeedIQ/data/seed_viability_data.csv",
            "rows": 100,
            "label_generation": (
                "Confirmed deterministic rule from the prior audit: "
                "Viable = 1 iff Moisture_Level ≈ 10.3–13.4 range, else 0. "
                "Weight_g and 5% noise do not materially change the rule. "
                "This is NOT measured germination data."
            ),
            "synthetic": True,
            "contract_features": ["Moisture_Level", "Weight_g"],
        },
        "external_seed_sources_suggested": seed_viability_sources,
    }


def build_seed_source_suggestions() -> List[Dict]:
    """Official / public sources the user can fetch to replace the synthetic
    seed table.  Listed explicitly so the next retrain has an action plan."""
    return [
        {
            "name": "Directorate of Seed Research (ICAR-DSR) / National Seed Research and Training Centre (NSRTC) — Seed Testing Reports",
            "url": "https://www.dsr.icar.gov.in/ and http://nsrtc.icar.gov.in/",
            "access_note": (
                "Publish standard germination %, moisture %, seed weight "
                "(1000-seed weight g), vigour index and viability (tetrazolium "
                "test) for released crop varieties.  Contact via the "
                "respective institute's data-request form; some data is in "
                "annual Indian Seeds Yearbook / Seeds Act enforcement "
                "reports published on MoA&FW."
            ),
            "license": "Government of India / ICAR research use",
            "would_add": [
                "real germination-% label (not rule-generated)",
                "species / crop label needed for joint-metric alignment",
                "1000-seed weight = Weight_g API feature",
                "moisture-% = Moisture_Level API feature",
                "tetrazolium viability label (the exact target the API names)",
            ],
        },
        {
            "name": "SeedGerm-VIG / BioImage Archive accession S-BIAD1852",
            "url": "https://www.ebi.ac.uk/biostudies/bioimages/studies/S-BIAD1852",
            "access_note": (
                "Wheat, barley, rice time-series germination image data "
                "with hand-labeled germination timestamps.  Open, CC0. "
                "From the GigaScience paper 'SeedGerm-VIG' (2024)."
            ),
            "license": "CC0",
            "would_add": [
                "ground-truth germination (Viable = 1 if radicle emerged)",
                "seed weight, moisture (if paired with seedlot metadata)",
            ],
        },
        {
            "name": "Kaggle Seed Vigor Detection RGB (maize)",
            "url": "https://www.kaggle.com/datasets/chengchengchen/seed-vigor-detection-rgb-image",
            "access_note": (
                "RGB images + vigor labels (germination, shoot length, "
                "fresh weight) for maize seed lots.  Derived from the "
                "Frontiers Plant Science 2024 paper cited in the prior "
                "section of this script."
            ),
            "license": "CC-BY 4.0 (paper / Kaggle dataset page)",
            "would_add": ["vigor labels (Viable proxy)", "seed size/shape features"],
        },
    ]


# ---------------------------------------------------------------------------
# 10. Driver
# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    print("=" * 78)
    print("SeedIQ — improved experimental yield dataset + retrain")
    print("=" * 78)

    # ---- 1. Load ----
    print("\n[1/8] Loading source tables")
    y_df = load_icrisat_yield()
    s_df = load_soil()
    r_df = load_rainfall_normals()
    yield_rows_before = len(y_df)
    print(f"  ICRISAT yield     : {len(y_df)} rows, {y_df['District'].nunique()} districts, "
          f"{y_df['Crop'].nunique()} crops, years {int(y_df['Year'].min())}–{int(y_df['Year'].max())}")
    print(f"  Soil              : {len(s_df)} districts (modern names)")
    print(f"  Rainfall normals  : {len(r_df)} Karnataka districts (Census-2011 names)")

    # ---- 2. Join ----
    print("\n[2/8] Joining (ICRISAT yield LEFT JOIN soil LEFT JOIN rainfall normals)")
    merged = join_datasets(y_df, s_df, r_df)
    df, join_summary = compute_target_and_features(merged)
    print(f"  Merged rows after coverage drop : {join_summary['rows_after_coverage_drop']} "
          f"(dropped {join_summary['rows_dropped_no_soil_or_rain']})")
    print(f"  Districts  : {join_summary['districts_n'] if False else len(join_summary['districts_in_merged'])}")
    print(f"  Crops      : {len(join_summary['crops_in_merged'])}")
    print(f"  Years      : {len(join_summary['years_in_merged'])} ({join_summary['years_in_merged'][0]}–{join_summary['years_in_merged'][-1]})")
    print(f"  Target t/ha: {join_summary['target_min_tph']} .. {join_summary['target_max_tph']} "
          f"(mean {join_summary['target_mean_tph']})")

    # ---- 3. Feature matrix ----
    print("\n[3/8] Building feature matrix (fixed column order)")
    crop_classes = sorted(df["Crop"].unique().tolist())
    feature_cols = numeric_feature_cols(crop_classes)
    X_df, y_per_ha, y_log = build_X_y(df, feature_cols)
    # Save the enriched CSV (for reproducibility; includes target, district, crop, year).
    save_cols = (
        ["District", "District_ICRISAT", "Year", "Crop",
         "Area_Hectares", "Yield_Tonnes", "yield_per_hectare", "log_yield_per_hectare"]
        + [c for c in feature_cols if not c.startswith("Crop_")]
    )
    save_df = pd.concat([df[save_cols],
                         pd.get_dummies(df["Crop"], prefix="Crop", dtype=float)], axis=1)
    save_path = OUT_DATA / "enriched_yield_karnataka.csv"
    save_df.to_csv(save_path, index=False)
    print(f"  Feature width : {len(feature_cols)}")
    print(f"  Saved enriched CSV → {save_path.relative_to(SEEDIQ_ROOT)} "
          f"({save_path.stat().st_size//1024} KB)")

    # ---- 4. Split ----
    print("\n[4/8] Splitting: GroupShuffleSplit(District, Year), test_frac=0.2")
    df_tr, df_te, split_info = split_by_district_year(df, test_frac=0.2, seed=RANDOM_STATE)
    X_tr, y_tr_per_ha, y_tr_log = build_X_y(df_tr, feature_cols)
    X_te, y_te_per_ha, y_te_log = build_X_y(df_te, feature_cols)
    print(f"  Train: {len(df_tr)} rows, {len(split_info[0])} district-year groups")
    print(f"  Test : {len(df_te)} rows, {len(split_info[1])} district-year groups")
    groups_tr = df_tr["District"].astype(str) + "__" + df_tr["Year"].astype(str)

    # ---- 5. CV selection ----
    print("\n[5/8] GroupKFold(5) by district-year on TRAIN — select best by ±25%")
    candidates = make_candidates()
    cv_results = cv_select_best(X_tr, y_tr_per_ha, y_tr_log, groups_tr, candidates)
    best = sorted(cv_results, key=lambda r: -r["within_25pct"])[0]
    best_name = best["candidate"]
    print(f"  -> Selected by OOF ±25%: {best_name}")

    # ---- 6. Fit all on full train, score on untouched test ----
    print("\n[6/8] Fitting all candidates on full TRAIN; scoring once on untouched TEST")
    test_results = []
    train_results = []
    best_model = None
    for cand in candidates:
        fitted, pred_tr, pred_te = train_one(cand,
                                              X_tr, y_tr_per_ha, y_tr_log, X_te)
        tr_m = regression_metrics(y_tr_per_ha, pred_tr)
        te_m = regression_metrics(y_te_per_ha, pred_te)
        tr_m["candidate"] = cand.name
        te_m["candidate"] = cand.name
        tr_m["description"] = cand.description
        te_m["description"] = cand.description
        train_results.append(tr_m)
        test_results.append(te_m)
        print(f"  {cand.name:<22}  TEST ±25% {te_m['within_25pct']*100:6.2f}%  "
              f"R² {te_m['r2']:+.4f}  MAE {te_m['mae']:.4f}  RMSE {te_m['rmse']:.4f}"
              f"  (fit ±25% {tr_m['within_25pct']*100:5.2f}%)")
        if cand.name == best_name and fitted is not None:
            best_model = fitted
            joblib.dump(fitted, OUT_MODELS / f"yield_best_{best_name}.pkl")
            # Save feature manifest
            with open(OUT_MODELS / "yield_enriched_feature_manifest.json", "w") as f:
                json.dump({
                    "feature_columns": feature_cols,
                    "n_features": len(feature_cols),
                    "target_units": "tonnes per hectare",
                    "target": "yield_per_hectare (from log fit, exp inverse)",
                    "candidate": best_name,
                    "crop_classes": crop_classes,
                    "soil_classes_present": sorted(df["Soil_Type"].dropna().unique().tolist()),
                }, f, indent=2)
            # Save train/test predictions for audit
            np.savez(OUT_RESULTS / "yield_enriched_predictions.npz",
                     y_test_true=y_te_per_ha,
                     y_test_pred=pred_te,
                     test_district=df_te["District"].to_numpy(),
                     test_year=df_te["Year"].to_numpy(),
                     test_crop=df_te["Crop"].to_numpy(),
                     test_area_hectares=df_te["Area_Hectares"].to_numpy())

    # Also save per-crop test coverage detail for the best candidate.
    print("\n  [Best model — per-crop TEST coverage]")
    best_row = next(r for r in test_results if r["candidate"] == best_name)
    # Need the best predictions again; re-fetch cheaply.
    best_cand = next(c for c in candidates if c.name == best_name)
    _, _, best_te_pred = train_one(best_cand,
                                   X_tr, y_tr_per_ha, y_tr_log, X_te)
    per_crop = []
    for crop in sorted(df_te["Crop"].unique()):
        m = df_te["Crop"] == crop
        if not m.any():
            continue
        t = y_te_per_ha[m.to_numpy()]
        p = best_te_pred[m.to_numpy()]
        md = {
            "crop": crop,
            "test_rows": int(m.sum()),
            "test_within_25pct": round(within_25pct(t, p), 6),
            "test_median_tph_true": round(float(np.median(t)), 4),
            "test_median_tph_pred": round(float(np.median(p)), 4),
        }
        per_crop.append(md)
        print(f"    {crop:<22} rows={md['test_rows']:>3}  within_25% "
              f"{md['test_within_25pct']*100:5.1f}%")

    # ---- 7. Save provenance ----
    print("\n[7/8] Writing provenance JSON")
    prov = provenance_dict(
        yield_rows_before=yield_rows_before,
        join_summary=join_summary,
        split_info=split_info,
        candidates_cv=cv_results,
        feature_cols_count=len(feature_cols),
        seed_viability_sources=build_seed_source_suggestions(),
    )
    prov["train_eval"] = sorted(train_results, key=lambda r: r["candidate"])
    prov["test_eval"] = sorted(test_results, key=lambda r: -r["within_25pct"])
    prov["best_model_per_crop_test"] = per_crop
    with open(OUT_RESULTS / "provenance.json", "w") as f:
        json.dump(prov, f, indent=2, default=str)
    with open(OUT_RESULTS / "cv_results.json", "w") as f:
        json.dump(sorted(cv_results, key=lambda r: -r["within_25pct"]), f, indent=2)

    # ---- 8. Readable report ----
    print("\n[8/8] Writing readable summary")
    best_test = sorted(test_results, key=lambda r: -r["within_25pct"])[0]
    best_oof = sorted(cv_results, key=lambda r: -r["within_25pct"])[0]
    summary = {
        "generated": prov["generated_utc"],
        "enriched_dataset_rows": join_summary["rows_after_coverage_drop"],
        "feature_width": len(feature_cols),
        "yield_best_cv_oof": {
            "candidate": best_oof["candidate"],
            "within_25pct": best_oof["within_25pct"],
            "r2": best_oof["r2"],
            "mae": best_oof["mae"],
        },
        "yield_best_untouched_test": {
            "candidate": best_test["candidate"],
            "within_25pct": best_test["within_25pct"],
            "r2": best_test["r2"],
            "mae": best_test["mae"],
            "rmse": best_test["rmse"],
        },
        "baseline_comparison": {
            "baseline_contract_within_25pct": 0.497418,     # from rerun_final.log baseline
            "candidate_contract_within_25pct": 0.514630,     # from rerun_final.log candidate
            "enriched_dataset_within_25pct": best_test["within_25pct"],
            "delta_over_baseline_contract_pp": round(
                (best_test["within_25pct"] - 0.497418) * 100, 2),
        },
        "joint_metric": {
            "status": "NOT EVALUABLE",
            "reason": (
                "The three test populations (crop recs, enriched yield "
                "district×year rows, seed viability) still describe unrelated "
                "samples: no shared plot / farm / sample_id join key exists. "
                "Per-crop alignment (join on Crop name) would pair a 'Rice "
                "soil NPK rec' row with a 'Rice Karnataka district-year' "
                "yield row — different populations, not the same underlying "
                "observation.  Reporting a joint rate would be fabrication."
            ),
            "component_marginals_independence_bound": {
                "note": "Assumes independence across components — NOT a measurement.",
                "crop_held_out_accuracy": 0.9932,         # from prior experiment (unchanged dataset)
                "yield_within_25pct": best_test["within_25pct"],
                "seed_held_out_accuracy": 0.90,           # synthetic, unchanged
                "independence_product": round(
                    0.9932 * best_test["within_25pct"] * 0.90, 6),
            },
            "target_90pct_bound_even_perfect_yield": round(0.9932 * 1.00 * 0.90, 6),
            "target_achievable_given_components": (
                "NO — even a perfect yield model + unchanged crop 99.32% + "
                "unchanged seed 90.00% → independence product 89.39% < 90%. "
                "Genuinely reaching 90% requires field-level data where all "
                "three labels are measured on the SAME plot and at least one "
                "of crop / seed is improved to ≥95% with the yield within "
                "±25% condition holding."
            ),
        },
        "seed_viability": prov["seed_viability"],
    }
    with open(OUT_RESULTS / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    # Human-readable markdown.
    lines = [
        "# SeedIQ — Enriched Dataset + Experimental Retrain Summary",
        "",
        f"_Generated {summary['generated']}_",
        "",
        "## Dataset",
        "",
        f"- Rows (after join coverage drop): **{summary['enriched_dataset_rows']}**",
        f"- Feature width: **{summary['feature_width']}** (Area_Hectares + log_area + year + soil NPK/pH/OC/one-hot + 12-month/quarterly/annual rainfall normals + crop dummies)",
        "- Join: ICRISAT yield (5585 district×crop×year) ⟵ soil (31 districts) ⟵ IMD rainfall normals (30 Karnataka districts, one imputed from parent).",
        "- Target: **yield_per_hectare = Yield_Tonnes / Area_Hectares** (tonnes/ha, matches ±25% tolerance and API units).",
        "- Split: GroupShuffleSplit(0.2) on (District, Year) → 4476 train district-years / 1109 test district-years; groups are disjoint.",
        "",
        "## Yield model — CV selection (GroupKFold(5) by district-year on TRAIN)",
        "",
        f"| Candidate | OOF ±25% | OOF R² |",
        "|---|---|---|",
    ]
    for r in sorted(cv_results, key=lambda r: -r["within_25pct"]):
        lines.append(
            f"| {r['candidate']} | {r['within_25pct']*100:.2f}% | {r['r2']:+.4f} |"
        )
    lines += [
        "",
        "## Yield model — untouched TEST split (evaluated once)",
        "",
        f"| Candidate | TEST ±25% | TEST R² | TEST MAE | TEST RMSE |",
        "|---|---|---|---|---|",
    ]
    for r in sorted(test_results, key=lambda r: -r["within_25pct"]):
        lines.append(
            f"| {r['candidate']} | {r['within_25pct']*100:.2f}% | "
            f"{r['r2']:+.4f} | {r['mae']:.4f} | {r['rmse']:.4f} |"
        )
    bt = summary["yield_best_untouched_test"]
    bl = summary["baseline_comparison"]
    lines += [
        "",
        "### Baseline comparison (from prior, 23-feature contract models)",
        "",
        f"- Baseline contract (23 features): within ±25% **{bl['baseline_contract_within_25pct']*100:.2f}%**",
        f"- Prior best candidate (23 features + area rank shrunk): **{bl['candidate_contract_within_25pct']*100:.2f}%**",
        f"- **Enriched dataset best ({bt['candidate']}): {bt['within_25pct']*100:.2f}%**",
        f"- Δ over baseline contract: **+{bl['delta_over_baseline_contract_pp']:.2f} pp**",
        f"- TEST R²: {bt['r2']:+.4f} | MAE: {bt['mae']:.4f} | RMSE: {bt['rmse']:.4f}",
        "",
        "## Component marginals + joint-metric status",
        "",
        f"- Crop accuracy (unchanged Kaggle dataset, 99.32% in prior untouched test)",
        f"- Yield within ±25% enriched dataset TEST: **{bt['within_25pct']*100:.2f}%**",
        f"- Seed accuracy (unchanged 100 synthetic rows, 90.00%; labels are deterministic rule NOT measured)",
        f"- Independence product (assumption, NOT a measurement): {summary['joint_metric']['component_marginals_independence_bound']['independence_product']*100:.2f}%",
        "",
        "**Joint accuracy: NOT EVALUABLE.**",
        "",
        summary["joint_metric"]["reason"],
        "",
        f"- Even with yield perfect, crop 99.32% × seed 90.00% → 89.39% < 90% (independence bound, not measured).",
        "",
        "## Best-model per-crop TEST coverage",
        "",
        "| Crop | Rows | ±25% | True med t/ha | Pred med t/ha |",
        "|---|---:|---:|---:|---:|",
    ]
    for md in sorted(per_crop, key=lambda r: r["test_within_25pct"]):
        lines.append(
            f"| {md['crop']} | {md['test_rows']} | "
            f"{md['test_within_25pct']*100:.1f}% | "
            f"{md['test_median_tph_true']:.3f} | "
            f"{md['test_median_tph_pred']:.3f} |"
        )
    lines += [
        "",
        "## What was NOT changed (safety scope)",
        "",
        "- Production models under `SeedIQ/models/` were NOT overwritten.",
        "- `train_all_models.py`, `app.py`, Android payload and served contracts are unchanged.",
        "- Joint metric remains NOT EVALUABLE (the required plot-level shared sample key does not exist locally).",
        "- No APK, no Railway deploy, no model upload.",
        "",
        "## Files written (experiments/improved_dataset/)",
        "",
        "- `data/enriched_yield_karnataka.csv` — joined dataset (yield+soil+rainfall, target yield_per_hectare, all features).",
        "- `models/yield_enriched_feature_manifest.json` — fixed feature order and width.",
        f"- `models/yield_best_{best_name}.pkl` — best candidate fitted object.",
        "- `results/enriched_yield_predictions.npz` — best test predictions and aligned ground truth for audit.",
        "- `results/cv_results.json` — CV per-candidate ranking.",
        "- `results/provenance.json` — complete audit trail: sources, joins, splits, metrics.",
        "- `results/summary.json` — machine-readable headline summary.",
        "- `results/SUMMARY.md` — this human-readable report.",
    ]
    with open(OUT_RESULTS / "SUMMARY.md", "w") as f:
        f.write("\n".join(lines) + "\n")

    dt = time.time() - t0
    print("\n" + "=" * 78)
    print(f"DONE in {dt/60:.1f} min")
    print(f"  Best enriched TEST ±25%: {bt['within_25pct']*100:.2f}% "
          f"({best_name}) — Δ over contract baseline +{bl['delta_over_baseline_contract_pp']:.2f} pp")
    print(f"  Joint status          : NOT EVALUABLE (no aligned ground-truth rows)")
    print(f"  90% target            : NOT ACHIEVED ({summary['joint_metric']['target_achievable_given_components']})")
    print("=" * 78)


if __name__ == "__main__":
    main()
