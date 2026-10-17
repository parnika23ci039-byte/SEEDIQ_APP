#!/usr/bin/env python3
"""
SeedIQ — Model Retraining & Honest Evaluation Pipeline (v2)
===========================================================
This script is the implementation behind ``POST /api/retrain`` (Admin only) and
can also be run directly:

    python train_all_models.py [--report reports/retrain_report.json]

What it trains (the same artifacts the Flask API serves):
    * Crop   : Random Forest            -> models/rf_model.pkl
               Simulated VQC classifier -> models/vqc_crop_model.pkl
    * Yield  : Random Forest pipeline   -> models/yield_prediction/randomforest_model.pkl
               XGBoost (comparison)     -> models/xgb_model.pkl
               Simulated VQR regressor  -> models/vqc_yield_model.pkl
    * Seed   : Random Forest            -> models/seed_viability/randomforest_model.pkl
               Support Vector Machine   -> models/svm_model.pkl
               Simulated VQC classifier -> models/vqc_seed_model.pkl
    * Meta   : CV-selected learner (regularized linear / shallow tree) on
               out-of-fold base predictions -> models/meta_model.pkl

Evaluation contract (this is what changed in v2):
    1. Every dataset is split ONCE into TRAIN / TEST (random_state=42; stratified
       for classification). The TEST split is not used for any fitting, tuning or
       model selection.
    2. Preprocessing (scalers, encoders) is fitted on TRAIN only.
    3. Cross-validation is computed on the TRAIN split only.
    4. The meta-model is trained on OUT-OF-FOLD predictions of the TRAIN split and
       evaluated on predictions the base models make for the untouched TEST split
       (classic stacking protocol — no test-set leakage).
    5. Datasets that had to be generated locally are flagged ``synthetic`` in the
       report and in ``training_registry.json``. Metrics measured on generated
       data describe the pipeline, not real-world agronomic performance.
    6. The quantum models are simulated classical stand-ins (a recorded-feature
       projection + linear/tree learner) whenever a quantum runtime (Qiskit) is
       unavailable. They are flagged ``simulated_quantum: true`` everywhere.

Machine-readable output: ``reports/retrain_report.json`` (consumed by
``/api/retrain`` and the Android admin screen). Human-readable output goes to
stdout and ``training_history.txt``.
"""

import argparse
import datetime
import hashlib
import json
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
    r2_score,
)
from sklearn.model_selection import (
    GridSearchCV,
    GroupKFold,
    GroupShuffleSplit,
    KFold,
    StratifiedGroupKFold,
    StratifiedKFold,
    cross_val_predict,
    cross_val_score,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from qml_model import SimulatedQuantumClassifier, SimulatedQuantumRegressor
# Canonical seed-verdict encoding. Serving (app.py) imports the same module, so the
# meta feature cannot be a class index on one side and a 0/1 verdict on the other.
from seed_viability_semantics import viable_flag_from_index
from yield_model import APPROVED_HYPERPARAMS, make_yield_model

try:
    from xgboost import XGBRegressor  # type: ignore
    XGBOOST_AVAILABLE = True
except Exception:  # ImportError or shared-library failure (missing libomp, ...)
    XGBRegressor = None  # type: ignore
    XGBOOST_AVAILABLE = False

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODELS_DIR = os.path.join(BASE_DIR, "models")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
HISTORY_FILE = os.path.join(BASE_DIR, "training_history.txt")
REGISTRY_FILE = os.path.join(BASE_DIR, "training_registry.json")
DEFAULT_REPORT_FILE = os.path.join(REPORTS_DIR, "retrain_report.json")

RANDOM_STATE = 42
TEST_SPLIT = 0.20
CV_FOLDS = 5
RUN_ID = f"RUN-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"

# Yield generator noise (coefficient of variation) for FUTURE fallback data only.
# History: the legacy generator removed all noise, which made R2 print as exactly
# 1.0. A CV of 0.10 was a partial fix, but it was still too tidy — with a single
# multiplier per (Crop, Season) cell, ~15 constants explained ~99% of the
# variance, so the target stayed effectively encoded by the categorical columns.
# 0.25 is a realistic rainfed plot-to-plot / season-to-season spread for cereals
# and is deliberately NOT tuned to any accuracy target.
YIELD_NOISE_CV = 0.25

CROP_FEATURES = [
    "Nitrogen", "Phosphorus", "Potassium", "Temperature", "Humidity", "pH", "Rainfall",
]
SEED_FEATURES = ["Moisture_Level", "Weight_g"]
# LEGACY one-hot layout of the pre-ICRISAT synthetic contract
# ((crop, season, area) -> plot-total tonnes). The ACTIVE layout is computed
# from the routed yield dataset by yield_feature_columns() and published to
# models/yield_feature_manifest.json, which app.py reads at inference time so
# training and serving can never disagree. This constant remains only as the
# fallback for a server started before the first manifest exists (i.e. while an
# older, 7-feature artifact is still the one on disk).
YIELD_FEATURE_COLUMNS = [
    "Area_Hectares",
    "Crop_Maize", "Crop_Rice", "Crop_Sugarcane", "Crop_Wheat",
    "Season_Rabi", "Season_Zaid",
]

# Real ICRISAT district-level source table and the contract-shaped yield table
# derived from it (never the other way round: the source file is read-only and
# the derived file is written once, then preserved).
ICRISAT_SOURCE_FILENAME = "ICRISAT-District Level Data.csv"
YIELD_DERIVED_FILENAME = "yield_icrisat_karnataka.csv"

# The one-hot layout the served yield model is fitted on is published here by
# training and read by app.py at inference time, so the two can never disagree
# about the column order or the crop vocabulary (the crop list is data-driven
# now that the real ICRISAT table supplies 22 crops).
YIELD_MANIFEST_FILE = os.path.join(MODELS_DIR, "yield_feature_manifest.json")

# Minimum |train - test| gap (percentage points on the headline metric) before a
# model is reported as overfitting.
GAP_GOOD = 0.05
GAP_MODERATE = 0.15

REPORT = {
    "run_id": RUN_ID,
    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "success": False,
    "error": None,
    "quantum_mode": "simulated",
    "datasets": [],
    "data_integrity": {},
    "models": [],
    "generalization": {},
    "registry_entries_added": 0,
    "notes": [],
}

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)


def log(message):
    print(message)
    with open(HISTORY_FILE, "a", encoding="utf-8") as log_file:
        log_file.write(
            f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"
        )


# ---------------------------------------------------------------------------
# Dataset provisioning (never overwrite existing data)
# ---------------------------------------------------------------------------
def _sha256_short(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except OSError:
        return None


def generate_crop_fallback(path):
    """Legacy 5-class crop generator. Only used when no crop dataset exists."""
    rng = np.random.default_rng(RANDOM_STATE)
    rows = []
    specs = {
        "Rice":      dict(n=(80, 120), p=(40, 60), k=(35, 45), t=(25, 33), h=(80, 95), ph=(6.0, 7.0), r=(180, 260)),
        "Wheat":     dict(n=(60, 90),  p=(50, 70), k=(30, 45), t=(15, 23), h=(50, 65), ph=(6.2, 7.2), r=(60, 100)),
        "Maize":     dict(n=(70, 100), p=(40, 55), k=(30, 40), t=(20, 28), h=(60, 75), ph=(5.8, 6.8), r=(90, 140)),
        "Sugarcane": dict(n=(90, 130), p=(45, 60), k=(50, 75), t=(26, 34), h=(70, 85), ph=(6.5, 7.5), r=(150, 220)),
        "Cotton":    dict(n=(50, 80),  p=(30, 50), k=(20, 35), t=(22, 30), h=(40, 55), ph=(5.5, 6.5), r=(50, 85)),
    }
    for crop, s in specs.items():
        for _ in range(20):
            # Wider sampling spreads than the legacy generator so the classes
            # overlap instead of being trivially separable.
            rows.append({
                "Nitrogen": rng.uniform(*s["n"]), "Phosphorus": rng.uniform(*s["p"]),
                "Potassium": rng.uniform(*s["k"]), "Temperature": rng.uniform(*s["t"]),
                "Humidity": rng.uniform(*s["h"]), "pH": rng.uniform(*s["ph"]),
                "Rainfall": rng.uniform(*s["r"]),
                "Crop": crop,
            })
    pd.DataFrame(rows).to_csv(path, index=False)


def generate_yield_dataset(path):
    """Synthetic yield dataset for the (crop, season, area) API contract.

    The per-crop, per-season multiplier sets the *expected* yield for a cell; the
    realised target carries a multiplicative log-normal term (YIELD_NOISE_CV)
    standing in for the weather/soil/pest variation that the four contract
    columns cannot express. That term is what stops the target being a pure
    function of (Crop, Season, Area); without it the file is a look-up table.

    NOTE — this generator is only reached when the dataset file is absent and
    SEEDIQ_ALLOW_SYNTHETIC_FALLBACK=1. The owned file data/crop_production_
    karnataka.csv is NOT regenerated by the pipeline (see ensure_datasets) and
    is the older, *noise-free* variant: its yield-per-hectare is exactly constant
    within every (Crop, Season) cell. The report's dataset-quality probe measures
    that from the data itself (target_exactly_determined_by_inputs), so the
    shipped metrics are labelled as generator artifacts rather than real skill.
    """
    rng = np.random.default_rng(RANDOM_STATE)
    crop_multipliers = {"Rice": 4.0, "Wheat": 3.2, "Maize": 3.8, "Sugarcane": 75.0, "Cotton": 2.2}
    season_multipliers = {"Kharif": 1.1, "Rabi": 0.95, "Zaid": 0.8}
    crops = list(crop_multipliers.keys())
    seasons = list(season_multipliers.keys())
    rows = []
    for _ in range(100):
        crop = str(rng.choice(crops))
        season = str(rng.choice(seasons))
        area = float(rng.uniform(1.0, 10.0))
        base = area * crop_multipliers[crop] * season_multipliers[season]
        noisy = base * float(rng.lognormal(mean=-0.5 * YIELD_NOISE_CV ** 2, sigma=YIELD_NOISE_CV))
        rows.append({"Crop": crop, "Season": season, "Area_Hectares": area,
                     "Yield_Tonnes": max(noisy, 0.1)})
    pd.DataFrame(rows).to_csv(path, index=False)


def generate_seed_dataset(path):
    """Synthetic seed viability dataset for the (moisture, weight) API contract.

    The label is *drawn* from a documented logistic relation around the
    safe-storage moisture optimum (~12% fresh weight) with a seed-weight term,
    so no single threshold rule reproduces it. The previous version used a hard
    AND rule (moisture in 10-13.5 and weight >= 45) plus a 5% flip, which made
    the label an almost deterministic function of the two inputs — a shallow
    tree already reached ~0.90 CV accuracy, i.e. the generator's own ceiling.
    Feature values are drawn from normal distributions rather than uniform
    ranges, which is closer to how stored seed lots actually vary.

    This is future fallback generation only: the owned file
    data/seed_viability_data.csv is NOT regenerated by the pipeline (see
    ensure_datasets), and the report's quality probe reports the property of
    whichever file is actually on disk.
    """
    rng = np.random.default_rng(RANDOM_STATE)
    optimum_moisture, moisture_sigma = 12.0, 2.0
    weight_reference = 45.0
    rows = []
    for _ in range(100):
        moisture = float(np.clip(rng.normal(optimum_moisture, moisture_sigma), 8.0, 16.0))
        weight = float(np.clip(rng.normal(52.0, 10.0), 25.0, 80.0))
        # Viability falls off as moisture deviates from the safe storage optimum
        # and as seeds get lighter than the reference weight.
        logit = (-0.9 * ((moisture - optimum_moisture) / moisture_sigma) ** 2
                 + 0.05 * (weight - weight_reference))
        p_viable = 1.0 / (1.0 + np.exp(-logit))
        rows.append({"Moisture_Level": moisture, "Weight_g": weight,
                     "Viable": int(rng.random() < p_viable)})
    pd.DataFrame(rows).to_csv(path, index=False)


def build_icrisat_yield_dataset(source_path=None, dest_path=None, force=False):
    """Derive the contract-shaped yield table from the real ICRISAT source.

    ICRISAT-District Level Data.csv is REAL published district/year/crop
    statistics for Karnataka (19 districts, 2000-2017) in wide format:
    ``<CROP> AREA (1000 ha)``, ``<CROP> PRODUCTION (1000 tons)`` and
    ``<CROP> YIELD (Kg per ha)``. This melts the complete AREA/PRODUCTION/YIELD
    triples into the API contract columns using plain arithmetic:

        Area_Hectares  = AREA(1000 ha)     x 1000
        Yield_Tonnes   = PRODUCTION(1000 t) x 1000   (plot/district TOTAL)

    The published YIELD column (kg/ha) is converted to t/ha and used to
    cross-check production/area; it is recorded as validation evidence, never
    written over the production figure. Crop names are only case-normalized
    (RICE -> Rice) so they match the API's presentation; no row, no value and
    NO Season column is ever invented — ICRISAT has no season field, and the
    yield contract drops Season because of it.

    Safety: the source is never modified, an existing derived file is never
    overwritten (force=False by default), and a failed validation raises
    instead of writing a bad table. District and Year are carried as grouping
    metadata for the district-year-aware evaluation; they are NOT model
    features.
    """
    source_path = source_path or os.path.join(DATA_DIR, ICRISAT_SOURCE_FILENAME)
    dest_path = dest_path or os.path.join(DATA_DIR, YIELD_DERIVED_FILENAME)
    if not os.path.exists(source_path):
        return {"status": "source_missing", "source": os.path.relpath(source_path, BASE_DIR)}
    if os.path.exists(dest_path) and not force:
        return {"status": "exists", "path": os.path.relpath(dest_path, BASE_DIR)}

    raw = pd.read_csv(source_path)
    triples = {}
    for col in raw.columns:
        for suffix, key in ((" AREA (1000 ha)", "area"),
                            (" PRODUCTION (1000 tons)", "production"),
                            (" YIELD (Kg per ha)", "yield")):
            if col.endswith(suffix):
                triples.setdefault(col[:-len(suffix)], {})[key] = col
    complete = {c: v for c, v in triples.items()
                if {"area", "production", "yield"} <= set(v)}

    rows = []
    for crop_upper, cols in complete.items():
        sub = raw[["Dist Name", "Year", cols["area"], cols["production"],
                   cols["yield"]]].dropna()
        for _, r in sub.iterrows():
            area_ha = float(r[cols["area"]]) * 1000.0        # 1000 ha -> ha
            prod_t = float(r[cols["production"]]) * 1000.0    # 1000 tons -> tonnes
            rate_tha = float(r[cols["yield"]]) / 1000.0       # kg/ha -> t/ha
            if area_ha <= 0 or prod_t <= 0 or rate_tha <= 0:
                continue  # unusable/invalid source cell — never repaired
            rows.append({
                "Crop": crop_upper.title().replace(" And ", " and "),
                "District": str(r["Dist Name"]).strip(),
                "Year": int(r["Year"]),
                "Area_Hectares": area_ha,
                "Yield_Tonnes": prod_t,
                "_published_rate_t_ha": rate_tha,   # validation only, not written
            })
    out = pd.DataFrame(rows)

    problems = []
    if out.empty:
        problems.append("no usable (area, production, yield) rows")
    elif int(out.duplicated(subset=["District", "Crop", "Year"]).sum()):
        problems.append("duplicate district/crop/year rows")
    if any("season" in c.lower() for c in out.columns):
        problems.append("Season column present")
    if not out.empty and out[["Area_Hectares", "Yield_Tonnes"]].isna().any().any():
        problems.append("missing area/production values")
    if problems:
        raise RuntimeError("ICRISAT derivation validation failed: " + "; ".join(problems))

    # Unit cross-check: production/area must reproduce the published kg/ha rate.
    implied = out["Yield_Tonnes"] / out["Area_Hectares"]
    rel = ((implied - out["_published_rate_t_ha"]) / out["_published_rate_t_ha"]).abs()
    consistency = {
        "median_abs_relative_error": round(float(rel.median()), 8),
        "p99_abs_relative_error": round(float(rel.quantile(0.99)), 6),
        "max_abs_relative_error": round(float(rel.max()), 6),
        "rows_over_1pct": int((rel > 0.01).sum()),
        "note": ("Residuals are source rounding in the published YIELD column "
                 "(kg/ha is published rounded); both figures are kept as published."),
    }

    out = out[["Crop", "District", "Year", "Area_Hectares", "Yield_Tonnes"]]
    out.to_csv(dest_path, index=False)
    return {
        "status": "derived",
        "source": os.path.relpath(source_path, BASE_DIR),
        "source_sha256_16": _sha256_short(source_path),
        "path": os.path.relpath(dest_path, BASE_DIR),
        "sha256_16": _sha256_short(dest_path),
        "rows": int(len(out)),
        "crops": int(out["Crop"].nunique()),
        "districts": int(out["District"].nunique()),
        "years": int(out["Year"].nunique()),
        "year_range": [int(out["Year"].min()), int(out["Year"].max())],
        "duplicate_district_crop_year": 0,
        "season_column": False,
        "unit_conversions": {
            "Area_Hectares": "AREA (1000 ha) x 1000",
            "Yield_Tonnes": "PRODUCTION (1000 tons) x 1000 (district/crop/year total)",
            "published_rate_check": "YIELD (Kg per ha) / 1000 = t/ha vs production/area",
        },
        "unit_consistency": consistency,
        "semantics": ("REAL district-level annual crop aggregates for Karnataka, "
                      "2000-2017 — NOT field-level, NOT season-resolved, NOT live data."),
        "provenance": "provided (ICRISAT-District Level Data.csv)",
    }


def _synthetic_fallback_allowed():
    """Whether generating synthetic stand-in data is explicitly enabled.

    Fabricating training rows must never happen implicitly: a missing dataset is
    reported as missing (training is then marked incomplete) unless the operator
    opts in with SEEDIQ_ALLOW_SYNTHETIC_FALLBACK=1. Anything generated that way
    is tagged ``synthetic`` / ``provenance=synthetic-generated`` and can never be
    reported as real-world agricultural performance.
    """
    value = str(os.environ.get("SEEDIQ_ALLOW_SYNTHETIC_FALLBACK", "")).strip().lower()
    return value in ("1", "true", "yes", "on")


def ensure_datasets():
    """Return ``(datasets, generated, missing)``; never silently fabricate data.

    The previous version called the generator unconditionally, which silently
    REPLACED the training data on every retrain. Files that already exist are
    never touched here, and a missing file is only regenerated when the
    synthetic fallback has been explicitly enabled by configuration.
    """
    from data_preprocessing import discover_and_route_datasets

    # Real data first: derive the contract-shaped yield table from the real
    # ICRISAT source if it does not exist yet. This is arithmetic on published
    # statistics, not fabrication, so it needs no opt-in flag; an existing
    # derived file and the source file itself are never touched.
    icrisat_stats = build_icrisat_yield_dataset()
    REPORT["yield_derivation"] = icrisat_stats
    if icrisat_stats.get("status") == "derived":
        log(f"  -> Derived data/{YIELD_DERIVED_FILENAME} from "
            f"{ICRISAT_SOURCE_FILENAME}: {icrisat_stats['rows']} REAL rows "
            f"({icrisat_stats['crops']} crops x {icrisat_stats['districts']} districts x "
            f"{icrisat_stats['years']} years), no Season column.")
    elif icrisat_stats.get("status") == "exists":
        log(f"  -> Using existing data/{YIELD_DERIVED_FILENAME} (ICRISAT-derived, preserved).")
    else:
        log(f"  -> ICRISAT derivation unavailable: {icrisat_stats}")

    generated, missing = [], []
    allow_synthetic = _synthetic_fallback_allowed()
    fallback = {
        "crop": (os.path.join(DATA_DIR, "merged_ml_dataset.csv"), generate_crop_fallback),
        "yield": (os.path.join(DATA_DIR, "crop_production_karnataka.csv"), generate_yield_dataset),
        "seed": (os.path.join(DATA_DIR, "seed_viability_data.csv"), generate_seed_dataset),
    }
    for domain, (path, generator) in fallback.items():
        if os.path.exists(path):
            continue  # existing data is preserved untouched
        if not allow_synthetic:
            missing.append(domain)
            continue
        generator(path)
        generated.append(domain)
    datasets = discover_and_route_datasets(DATA_DIR)
    # discover_and_route_datasets prefers canonical files, then scans sorted CSVs.
    return datasets, generated, missing


TARGET_COLUMNS = {"crop": ("label", "Crop"), "yield": ("Yield_Tonnes",),
                  "seed": ("Viable",)}


def _generic_target_audit(domain, df):
    """Task-style dataset audit: cardinality, correlation, rule recoverability,
    duplicated feature vectors and constant-target groups.

    These are measurements, not quality gates: they are recorded so a metric can
    always be read next to how recoverable its target is from the inputs. Nothing
    here modifies data or thresholds.
    """
    audit = {
        "target_cardinality": None,
        "max_abs_target_input_correlation": None,
        "best_simple_rule_agreement": None,
        "duplicate_feature_vectors": None,
        "constant_target_group_fraction": None,
        "majority_class_rate": None,
    }
    target_col = next((c for c in TARGET_COLUMNS.get(domain, ()) if c in df.columns), None)
    if target_col is None:
        return audit
    try:
        y = df[target_col]
        audit["target_cardinality"] = int(y.nunique())
        numeric = df.select_dtypes(include=[np.number]).drop(columns=[target_col],
                                                            errors="ignore")
        # Correlation is only meaningful against a numeric (regression or binary)
        # target. For a nominal multi-class label the numeric encoding is arbitrary,
        # so no figure is published rather than a meaningless one.
        if pd.api.types.is_numeric_dtype(y):
            y_num = y.astype(float)
            corrs = []
            for col in numeric.columns:
                values = numeric[col].astype(float)
                if values.notna().all() and float(np.std(values)) > 0:
                    corrs.append(abs(float(np.corrcoef(values, y_num)[0, 1])))
            audit["max_abs_target_input_correlation"] = round(max(corrs), 6) if corrs else None
        else:
            audit["majority_class_rate"] = round(
                float(y.value_counts(normalize=True).iloc[0]), 6)
        audit["duplicate_feature_vectors"] = int(numeric.round(6).duplicated().sum())

        cats = [c for c in df.columns
                if c != target_col and (df[c].dtype == object or df[c].nunique() <= 15)][:4]
        group_keys = [[c] for c in cats] + [[cats[i], cats[j]]
                                            for i in range(len(cats))
                                            for j in range(i + 1, len(cats))]
        best = None
        for keys in group_keys:
            fraction = float((y.groupby([df[k] for k in keys]).nunique() <= 1).mean())
            best = fraction if best is None else max(best, fraction)
        audit["constant_target_group_fraction"] = round(best, 6) if best is not None else None

        # Binary target: can a simple axis-aligned box rule reproduce the labels?
        # This is the "is the label just a threshold rule?" check.
        if pd.api.types.is_numeric_dtype(y) and y.nunique() == 2 and len(numeric.columns):
            labels = y.astype(int).to_numpy()
            best_rule = 0.0
            for c1 in numeric.columns:
                v1 = numeric[c1].to_numpy(dtype=float)
                for c2 in numeric.columns:
                    v2 = numeric[c2].to_numpy(dtype=float)
                    for lo1 in np.quantile(v1, [0.1, 0.25, 0.4, 0.5]):
                        for hi1 in np.quantile(v1, [0.5, 0.6, 0.75, 0.9]):
                            for lo2 in np.quantile(v2, [0.1, 0.25, 0.4, 0.5]):
                                rule = ((v1 >= lo1) & (v1 <= hi1) & (v2 >= lo2)).astype(int)
                                best_rule = max(best_rule, float((rule == labels).mean()))
            audit["best_simple_rule_agreement"] = round(best_rule, 6)
    except Exception as exc:  # an audit must never break training
        audit["audit_error"] = f"{type(exc).__name__}: {exc}"
    return audit


def _resolve_columns(df, wanted, aliases):
    """Map canonical column names onto the dataset's actual (possibly short) ones."""
    options = {want: (aliases.get(want, ()) + (want,)) for want in wanted}
    resolved = []
    for want, names in options.items():
        match = next((name for name in names if name in df.columns), None)
        if match is None:
            raise KeyError(f"{want} not found in {list(df.columns)}")
        resolved.append(match)
    return resolved


# The shipped crop CSV uses the short N/P/K/ph/rainfall header, while the
# trainers rename them. The probe accepts either spelling.
CROP_FEATURE_ALIASES = {
    "Nitrogen": ("N", "n"), "Phosphorus": ("P", "p"), "Potassium": ("K", "k"),
    "Temperature": ("temperature",), "Humidity": ("humidity",),
    "pH": ("ph",), "Rainfall": ("rainfall",),
}


def _dataset_quality_probe(domain, df, synthetic):
    """How much of the target a SHALLOW model can already recover from the inputs.

    A near-perfect score here means the target is effectively a deterministic
    function of the dataset's own input columns, so a high headline metric
    describes the data source rather than real-world generalization. For a
    synthetic table that source is the generator; for a published table it is
    the (agronomically derived) input ranges. The probe is computed from the
    data itself and recorded next to every dataset.
    """
    probe = {
        "input_only_cv": None,
        "input_only_cv_metric": None,
        "target_largely_derivable_from_inputs": None,
        "derivation_kind": None,
        "target_exactly_determined_by_inputs": None,
        "within_cell_yield_per_ha_std_max": None,
        "distinct_yield_per_ha_values": None,
        "quality_note": None,
    }
    try:
        if domain == "crop":
            cols = _resolve_columns(df, CROP_FEATURES, CROP_FEATURE_ALIASES)
            X = df[cols].astype(float).to_numpy()
            label_col = "label" if "label" in df.columns else "Crop"
            y = LabelEncoder().fit_transform(df[label_col].astype(str))
            metric, threshold = "accuracy", 0.95
            estimator = DecisionTreeClassifier(max_depth=6, random_state=RANDOM_STATE)
        elif domain == "yield":
            cats = [c for c in ("Crop", "Season") if c in df.columns]
            dummies = pd.get_dummies(df[cats].astype(str), columns=cats)
            dummies["Area_Hectares"] = df["Area_Hectares"].astype(float).to_numpy()
            X = dummies.to_numpy(dtype=float)
            y = df["Yield_Tonnes"].astype(float).to_numpy()
            metric, threshold = "r2", 0.95
            estimator = DecisionTreeRegressor(max_depth=6, random_state=RANDOM_STATE)
            # Exactness probe: is the target literally area x a per-(Crop[, Season])
            # constant? Zero within-cell spread means a noise-free deterministic
            # encoding of the inputs, which is a much stronger statement than a
            # high CV score and must be reported as such. Published tables such as
            # ICRISAT have real within-cell variation and fail this probe.
            _area = df["Area_Hectares"].astype(float).replace(0.0, np.nan)
            _ratio = df["Yield_Tonnes"].astype(float) / _area
            _key = [df[c] for c in cats]
            _counts = _ratio.groupby(_key).size()
            _cells = _ratio.groupby(_key).std(ddof=0)
            _cells = _cells[_counts >= 2].fillna(0.0)
            _worst = float(np.nanmax(_cells.to_numpy())) if len(_cells) else None
            probe["within_cell_yield_per_ha_std_max"] = _worst
            probe["distinct_yield_per_ha_values"] = int(_ratio.round(6).nunique())
            probe["target_exactly_determined_by_inputs"] = bool(
                _worst is not None and _worst <= 1e-9)
        elif domain == "seed":
            X = df[SEED_FEATURES].astype(float).to_numpy()
            y = df["Viable"].astype(int).to_numpy()
            metric, threshold = "accuracy", 0.90
            estimator = DecisionTreeClassifier(max_depth=3, random_state=RANDOM_STATE)
        else:
            return probe
        scores = cross_val_score(
            estimator, X, y,
            cv=KFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE),
            scoring=metric)
        mean = float(np.mean(scores))
        derived = bool(mean >= threshold)
        probe["input_only_cv"] = round(mean, 6)
        probe["input_only_cv_metric"] = metric
        probe["target_largely_derivable_from_inputs"] = derived
        if derived:
            probe["derivation_kind"] = "generator_derivable" if synthetic else "input_range_determined"
            probe["quality_note"] = (
                f"A shallow tree using only this dataset's own input columns already reaches "
                f"{mean:.3f} CV {metric} on the target. The target is therefore effectively a "
                f"deterministic function of the inputs, so this score is a property of the "
                + ("synthetic generator that produced the rows, not of real-world "
                   "agricultural outcomes."
                   if synthetic else
                   "dataset's own input ranges (as in this published table), not evidence of "
                   "field generalization.")
            )
        else:
            probe["derivation_kind"] = None
            probe["quality_note"] = (
                f"A shallow tree using only the inputs reaches {mean:.3f} CV {metric}, clearly "
                f"below a perfect score: the target is not recoverable from the inputs alone, "
                f"so model scores reflect genuine input-to-target structure."
            )
        if probe.get("target_exactly_determined_by_inputs"):
            probe["quality_note"] += (
                f" It is stronger than that: the target is EXACTLY area x a per-(Crop) "
                f"constant — only {probe['distinct_yield_per_ha_values']} distinct "
                f"yield-per-hectare values exist (%d rows) and the within-cell spread is 0, "
                f"i.e. a noise-free deterministic encoding of the inputs with no row-to-row "
                f"variation at all." % len(df)
            )
    except Exception as exc:  # never let a quality probe break training
        probe["quality_note"] = f"quality probe unavailable: {type(exc).__name__}: {exc}"
    return probe


def dataset_meta(domain, path, generated):
    if not path or not os.path.exists(path):
        return {"domain": domain, "path": None, "records": 0, "features": 0,
                "classes": None, "synthetic": True, "sha256_16": None,
                "provenance": "missing"}
    df = pd.read_csv(path)
    base = os.path.basename(path)
    synthetic = domain in generated
    provenance = "synthetic-generated" if synthetic else "provided"
    # Provenance is decided by the FILE's identity, not by the domain name: the
    # ICRISAT-derived table is real published statistics, while the legacy
    # generator output stays synthetic even when the file predates this run.
    if base == YIELD_DERIVED_FILENAME:
        synthetic = False
        provenance = f"provided (ICRISAT — {ICRISAT_SOURCE_FILENAME})"
    elif domain == "yield" and base == "crop_production_karnataka.csv":
        synthetic, provenance = True, "synthetic-generated"
    elif domain == "seed" and base == "seed_viability_data.csv":
        synthetic, provenance = True, "synthetic-generated"
    extra = {}
    if domain == "yield":
        extra = {
            "crops": int(df["Crop"].nunique()) if "Crop" in df.columns else None,
            "districts": int(df["District"].nunique()) if "District" in df.columns else None,
            "year_range": ([int(df["Year"].min()), int(df["Year"].max())]
                           if "Year" in df.columns else None),
            "season_column": bool("Season" in df.columns),
            "season_is_feature": False,
            "feature_columns": ["Crop", "Area_Hectares"],
            "target_column": "Yield_Tonnes",
        }
    classes = None
    label_col = "Crop" if "Crop" in df.columns else ("label" if "label" in df.columns else None)
    if domain == "crop" and label_col:
        classes = int(df[label_col].nunique())
    elif domain == "seed" and "Viable" in df.columns:
        classes = int(df["Viable"].nunique())
    quality = _dataset_quality_probe(domain, df, synthetic)
    audit = _generic_target_audit(domain, df)
    return {
        "domain": domain,
        "path": os.path.relpath(path, BASE_DIR),
        "records": int(len(df)),
        "features": int(len(df.columns) - 1),
        "classes": classes,
        "synthetic": synthetic,
        "sha256_16": _sha256_short(path),
        "provenance": provenance,
        "missing_values": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
        **extra,
        **quality,
        **audit,
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def register_model(*, model_name, dataset_path, algorithm, task, features, target,
                   records, features_count, classes, hyper_params, metrics,
                   generalization, output_path, simulated_quantum=False,
                   notes=None, sample_counts=None, provenance=None, domain=None,
                   artifact_written=True, dataset_composition=None):
    entry = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "run_id": RUN_ID,
        "model_name": model_name,
        "domain": domain,
        "dataset_path": dataset_path,
        "algorithm": algorithm,
        "task": task,
        "features": features,
        "target": target,
        "records": records,
        "features_count": features_count,
        "classes": classes,
        "hyperparameters": hyper_params,
        "metrics": metrics,
        "generalization": generalization,
        "random_state": RANDOM_STATE,
        "simulated_quantum": bool(simulated_quantum),
        "sample_counts": sample_counts or {},
        "dataset_provenance": provenance,
        # Explicit boolean form of the provenance for downstream consumers that
        # must not present synthetic-derived metrics as real. Derived from the
        # recorded provenance string (a composite meta provenance containing
        # "synthetic-generated" is correctly flagged True).
        "dataset_synthetic": bool(isinstance(provenance, str)
                                  and "synthetic" in provenance.lower()),
        # Per-leg breakdown for composite (stacked) models. A single boolean
        # cannot express "partly real", so the meta entry records which of its
        # input legs are real and which are synthetic instead of letting the
        # boolean above imply the whole input is synthetic.
        "dataset_composition": dataset_composition,
        "output_path": output_path,
        "artifact_written": bool(artifact_written),
        "notes": notes or "",
        "status": "Trained & Saved" if artifact_written else "Trained (artifact not written)",
    }

    registry = []
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                registry = json.load(f)
        except Exception as e:
            log(f"⚠️ Error reading registry ({e}); starting a fresh list.")
            registry = []

    registry.append(entry)
    try:
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=4)
        log(f"Registered {model_name} in {os.path.relpath(REGISTRY_FILE, BASE_DIR)}")
    except Exception as e:
        log(f"⚠️ Error saving model registry: {e}")
    return entry


def safe_pickle_save(obj, filepath):
    try:
        absolute = os.path.join(BASE_DIR, filepath)
        os.makedirs(os.path.dirname(absolute), exist_ok=True)
        with open(absolute, "wb") as f:
            pickle.dump(obj, f)
        return True
    except Exception as e:
        log(f"⚠️ Error pickling {filepath}: {e}")
        return False


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------
def classification_metrics(y_true, y_pred):
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 6),
        "precision_macro": round(float(precision_score(y_true, y_pred, average="macro", zero_division=0)), 6),
        "recall_macro": round(float(recall_score(y_true, y_pred, average="macro", zero_division=0)), 6),
        "f1_macro": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 6),
    }


def regression_metrics(y_true, y_pred):
    mse = float(mean_squared_error(y_true, y_pred))
    return {
        "r2": round(float(r2_score(y_true, y_pred)), 6),
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 6),
        "rmse": round(float(np.sqrt(mse)), 6),
    }


def gap_status(gap):
    gap = abs(float(gap))
    if gap <= GAP_GOOD:
        return "good"
    if gap <= GAP_MODERATE:
        return "moderate"
    return "high"


def cv_classifier(cv, X, y):
    scores = cross_val_score(cv, X, y, cv=StratifiedKFold(
        n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE), scoring="accuracy")
    return {"accuracy_mean": round(float(np.mean(scores)), 6),
            "accuracy_std": round(float(np.std(scores)), 6),
            "folds": [round(float(s), 6) for s in scores]}


def cv_regressor(cv, X, y):
    scores = cross_val_score(cv, X, y, cv=KFold(
        n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE), scoring="r2")
    return {"r2_mean": round(float(np.mean(scores)), 6),
            "r2_std": round(float(np.std(scores)), 6),
            "folds": [round(float(s), 6) for s in scores]}


def cv_regressor_grouped(est, X, y, groups):
    """CV for the yield leg: folds are whole district-years, never rows.

    The ICRISAT table is district/year aggregate data, so rows from the same
    district-year share their weather/soil context. Splitting them across folds
    would let the model see the same evidence on both sides and inflate the
    score. Grouped folds keep every district-year wholly inside one fold.
    """
    scores = cross_val_score(est, X, y, groups=groups,
                             cv=GroupKFold(n_splits=CV_FOLDS), scoring="r2")
    return {"r2_mean": round(float(np.mean(scores)), 6),
            "r2_std": round(float(np.std(scores)), 6),
            "folds": [round(float(s), 6) for s in scores],
            "scheme": f"GroupKFold({CV_FOLDS}) grouped by district-year (TRAIN only)"}


def format_cls(m):
    return (f"Accuracy {m['accuracy'] * 100:.2f}% | "
            f"Precision {m['precision_macro'] * 100:.2f}% | "
            f"Recall {m['recall_macro'] * 100:.2f}% | "
            f"F1 {m['f1_macro'] * 100:.2f}%")


def format_reg(m):
    return f"R² {m['r2']:.4f} | MAE {m['mae']:.4f} | RMSE {m['rmse']:.4f}"


# ---------------------------------------------------------------------------
# Data loaders (raw features; scalers are fitted on the train split only)
# ---------------------------------------------------------------------------
CROP_RENAME = {
    "n": "Nitrogen", "p": "Phosphorus", "k": "Potassium",
    "temperature": "Temperature", "humidity": "Humidity",
    "ph": "pH", "rainfall": "Rainfall", "label": "Crop", "crops": "Crop",
}


def load_crop_frame(path):
    df = pd.read_csv(path).dropna()
    df = df.rename(columns={c: CROP_RENAME[c.lower()] for c in df.columns if c.lower() in CROP_RENAME})
    missing = [c for c in CROP_FEATURES if c not in df.columns]
    if missing or "Crop" not in df.columns:
        raise ValueError(f"Crop dataset {path!r} is missing {missing or ['Crop']} (found {list(df.columns)}).")
    return df[CROP_FEATURES].astype(float), df["Crop"].astype(str)


def load_yield_frame(path):
    """Features, target and evaluation groups for the ACTIVE yield contract.

    The contract is ``Crop + Area_Hectares -> Yield_Tonnes``. Season is not a
    feature: the real ICRISAT source table has no season column, and the old
    Season_* dummies only existed because the synthetic generator emitted them.
    A legacy dataset that still carries a Season column is still accepted, but
    that column is never used — it is reported as ignored so nobody can mistake
    it for model input.

    ``groups`` identifies one unit of evidence (a district-year). Rows that share
    a district-year must never be split across train/test or across CV folds.
    """
    df = pd.read_csv(path)
    if "Area_Hectares" not in df.columns and "Area" in df.columns:
        df = df.rename(columns={"Area": "Area_Hectares"})
    required = ["Crop", "Area_Hectares", "Yield_Tonnes"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Yield dataset {path!r} is missing {missing} (found {list(df.columns)}). "
            "The active yield contract is Crop + Area_Hectares -> Yield_Tonnes."
        )
    df = df.dropna(subset=required)
    if "Season" in df.columns:
        log(f"  -> Note: {os.path.basename(path)} still carries a Season column; it is "
            f"IGNORED (deprecated contract field, never a fabricated input).")
    if {"District", "Year"} <= set(df.columns):
        groups = (df["District"].astype(str) + "|" + df["Year"].astype(str)).to_numpy()
    else:
        groups = np.asarray([f"row{i}" for i in range(len(df))])
    info = {
        "records": int(len(df)),
        "crops": int(df["Crop"].nunique()),
        "districts": int(df["District"].nunique()) if "District" in df.columns else None,
        "years": int(df["Year"].nunique()) if "Year" in df.columns else None,
        "year_range": ([int(df["Year"].min()), int(df["Year"].max())]
                       if "Year" in df.columns else None),
        "groups": int(len(np.unique(groups))),
        "season_ignored": bool("Season" in df.columns),
        "feature_columns": ["Crop", "Area_Hectares"],
        "target": "Yield_Tonnes",
    }
    return df[["Crop", "Area_Hectares"]].copy(), df["Yield_Tonnes"].astype(float), groups, info


def load_seed_frame(path):
    df = pd.read_csv(path).dropna()
    missing = [c for c in SEED_FEATURES if c not in df.columns]
    if missing or "Viable" not in df.columns:
        raise ValueError(
            f"Seed dataset {path!r} is missing {missing or ['Viable']} (found {list(df.columns)}). "
            "Refusing to train on a schema the seed-viability API does not accept."
        )
    return df[SEED_FEATURES].astype(float), df["Viable"].astype(int)


def yield_feature_columns(frame):
    """ACTIVE one-hot layout for the routed yield dataset (Crop + Area only)."""
    crops = sorted({str(c) for c in frame["Crop"].astype(str).unique()}, key=str.lower)
    return ["Area_Hectares"] + [f"Crop_{c}" for c in crops], crops


def yield_one_hot(frame, columns):
    """One-hot layout identical to app.py's yield_feature_frame() and the manifest."""
    encoded = pd.get_dummies(frame[["Crop"]].astype(str), prefix="Crop")
    encoded["Area_Hectares"] = frame["Area_Hectares"].astype(float).to_numpy()
    return encoded.reindex(columns=columns, fill_value=0.0).astype(float)


def publish_yield_manifest(columns, crops, dataset, info):
    """Publish the served feature contract so training and inference cannot disagree."""
    manifest = {
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "run_id": RUN_ID,
        "feature_columns": columns,
        "crop_options": crops,
        "input_schema": ["Crop", "Area_Hectares"],
        "target": "Yield_Tonnes",
        "season_required": False,
        "season_deprecated": True,
        "dataset": dataset.get("path"),
        "dataset_provenance": dataset.get("provenance"),
        "dataset_synthetic": bool(dataset.get("synthetic")),
        "records": info.get("records"),
        "districts": info.get("districts"),
        "years": info.get("years"),
        "semantics": ("Model inputs are crop and field area only. When the ICRISAT-derived "
                      "table is routed this is trained on REAL historical district-level "
                      "annual crop statistics (Karnataka, 2000-2017) — NOT field-level, NOT "
                      "season-resolved and NOT live data."),
    }
    os.makedirs(os.path.dirname(YIELD_MANIFEST_FILE), exist_ok=True)
    with open(YIELD_MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    log(f"  -> Published {os.path.relpath(YIELD_MANIFEST_FILE, BASE_DIR)} "
        f"({len(columns)} columns, {len(crops)} crops).")
    return manifest


# ---------------------------------------------------------------------------
# Domain training
# ---------------------------------------------------------------------------
def train_crop(path, dataset):
    """Returns (models_dict, oof_features, test_features, y_train, y_test, split)."""
    log("\n--- DATASET 1: Crop Recommendation ---")
    X_raw, y_str = load_crop_frame(path)
    encoder = LabelEncoder().fit(y_str)
    y = encoder.transform(y_str)
    n_classes = len(encoder.classes_)
    idx_train, idx_test = train_test_split(
        np.arange(len(X_raw)), test_size=TEST_SPLIT, random_state=RANDOM_STATE, stratify=y)
    X_train_raw = X_raw.iloc[idx_train]
    X_test_raw = X_raw.iloc[idx_test]
    y_train, y_test = y[idx_train], y[idx_test]

    scaler = StandardScaler().fit(X_train_raw)  # fitted on TRAIN only
    X_train = scaler.transform(X_train_raw)
    X_test = scaler.transform(X_test_raw)

    log(f"  -> Records: {len(X_raw)} | Features: {X_raw.shape[1]} | Classes: {n_classes} | "
        f"Train/Test: {len(idx_train)}/{len(idx_test)}")

    # ---- Random Forest (candidate selection by CV on TRAIN) ----
    log("  -> Training Random Forest (compact CV search on the train split)...")
    search = GridSearchCV(
        RandomForestClassifier(class_weight="balanced", random_state=RANDOM_STATE, n_jobs=-1),
        {"n_estimators": [200], "max_depth": [None, 15], "min_samples_leaf": [1, 2]},
        cv=StratifiedKFold(n_splits=3, shuffle=True, random_state=RANDOM_STATE),
        scoring="accuracy", n_jobs=-1,
    )
    search.fit(X_train, y_train)
    rf_model = search.best_estimator_
    log(f"     best params: {search.best_params_} | search CV: {search.best_score_ * 100:.2f}%")

    rf_train = classification_metrics(y_train, rf_model.predict(X_train))
    rf_cv = cv_classifier(rf_model, X_train, y_train)
    rf_test = classification_metrics(y_test, rf_model.predict(X_test))
    rf_oof = cross_val_predict(
        rf_model, X_train, y_train,
        cv=StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE))
    oof_crop = np.asarray(rf_oof)

    safe_pickle_save(rf_model, "models/rf_model.pkl")
    safe_pickle_save(scaler, "models/crop_scaler.pkl")
    safe_pickle_save(encoder, "models/crop_encoder.pkl")

    register_model(
        model_name="rf_model.pkl", domain="crop", dataset_path=dataset["path"],
        algorithm="Random Forest Classifier",
        task="classification", features=CROP_FEATURES, target="Crop",
        records=dataset["records"], features_count=dataset["features"], classes=n_classes,
        hyper_params=search.best_params_, metrics={
            "train": rf_train, "cv": rf_cv, "test": rf_test,
        },
        generalization={"train_test_gap": round(rf_train["accuracy"] - rf_test["accuracy"], 6),
                        "status": gap_status(rf_train["accuracy"] - rf_test["accuracy"])},
        output_path="models/rf_model.pkl", sample_counts={"train": len(idx_train), "test": len(idx_test)},
        provenance=dataset["provenance"],
    )
    log(f"  -> Random Forest: {format_cls(rf_train)} (train) | {format_cls(rf_test)} (test)")

    # ---- Simulated / real quantum crop classifier ----
    log("  -> Training Quantum Crop model (simulated recorded-feature VQC)...")
    vqc_crop = SimulatedQuantumClassifier(n_components=12, alpha=0.001, epochs=150)
    vqc_crop.fit(X_train, y_train)
    vqc_train = classification_metrics(y_train, vqc_crop.predict(X_train))
    vqc_cv = cv_classifier(vqc_crop, X_train, y_train)
    vqc_test = classification_metrics(y_test, vqc_crop.predict(X_test))
    vqc_oof = np.asarray(cross_val_predict(
        vqc_crop, X_train, y_train,
        cv=StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)))
    safe_pickle_save(vqc_crop, "models/vqc_crop_model.pkl")
    safe_pickle_save(vqc_crop, "models/vqc_model.pkl")

    register_model(
        model_name="vqc_crop_model.pkl", domain="crop", dataset_path=dataset["path"],
        algorithm="Simulated Quantum Classifier (recorded-feature projection + linear learner)",
        task="classification", features=CROP_FEATURES, target="Crop",
        records=dataset["records"], features_count=dataset["features"], classes=n_classes,
        hyper_params={"n_components": 12, "alpha": 0.001, "epochs": 150},
        metrics={"train": vqc_train, "cv": vqc_cv, "test": vqc_test},
        generalization={"train_test_gap": round(vqc_train["accuracy"] - vqc_test["accuracy"], 6),
                        "status": gap_status(vqc_train["accuracy"] - vqc_test["accuracy"])},
        output_path="models/vqc_crop_model.pkl", simulated_quantum=True,
        sample_counts={"train": len(idx_train), "test": len(idx_test)},
        notes="Simulated quantum circuit stand-in; NOT quantum hardware execution.",
        provenance=dataset["provenance"],
    )
    log(f"  -> Simulated VQC: {format_cls(vqc_train)} (train) | {format_cls(vqc_test)} (test)")

    models = {
        "rf_model": rf_model, "crop_scaler": scaler, "crop_encoder": encoder,
        "vqc_crop_model": vqc_crop,
    }
    oof = {"rf": oof_crop, "vqc": vqc_oof}
    test_pred = {"rf": rf_model.predict(X_test), "vqc": vqc_crop.predict(X_test)}
    return models, oof, test_pred, y_train, y_test, n_classes


def train_yield(path, dataset):
    log("\n--- DATASET 2: Yield Prediction ---")
    X_raw, y_total, groups, info = load_yield_frame(path)
    area = X_raw["Area_Hectares"].astype(float)

    # Grouped split: a district-year is one unit of evidence, so whole
    # district-years go to train or test — never both.
    splitter = GroupShuffleSplit(n_splits=1, test_size=TEST_SPLIT, random_state=RANDOM_STATE)
    idx_train, idx_test = next(splitter.split(X_raw, y_total, groups))
    y_train, y_test = y_total.iloc[idx_train], y_total.iloc[idx_test]
    area_train, area_test = area.iloc[idx_train].to_numpy(), area.iloc[idx_test].to_numpy()
    g_train = groups[idx_train]
    if set(groups[idx_train]) & set(groups[idx_test]):
        raise RuntimeError("Yield split leaked district-year groups across train/test.")

    columns, crops = yield_feature_columns(X_raw)
    X_oh = yield_one_hot(X_raw, columns)
    X_train, X_test = X_oh.iloc[idx_train], X_oh.iloc[idx_test]

    log(f"  -> Records: {info['records']} | Features: {X_oh.shape[1]} (area + {len(crops)} "
        f"crop dummies; no Season) | Crops: {info['crops']} | Districts: {info['districts']} | "
        f"Years: {info['years']} {info['year_range']}")
    log(f"  -> Grouped split by district-year: {len(set(g_train))} train groups / "
        f"{len(set(groups[idx_test]))} test groups | rows {len(idx_train)}/{len(idx_test)}")
    publish_yield_manifest(columns, crops, dataset, info)

    # ---- Served classical yield model (Model M) ----
    #
    # HistGradientBoostingRegressor fitted on log(Yield_Tonnes / Area_Hectares)
    # and returned as exp(pred) * area, so the output is still the district total
    # in tonnes and app.py can keep dividing by area.
    #
    # WHY: the yield model is judged by a ±25% RELATIVE tolerance (the meta label
    # and the app's per-hectare display). Squared error on district totals is
    # dominated by the largest districts, so low-yield rows (<1 t/ha, the majority
    # of this table) drift outside the tolerance. Squared error in log-per-hectare
    # approximates relative error, which is exactly what the ±25% threshold
    # measures. Relative error is algebraically identical on the total or per
    # hectare (the area cancels), so this changes the loss geometry, not the
    # quantity being predicted.
    #
    # The features are UNCHANGED: the same 23 columns, no Season/Year/District.
    # Hyper-parameters are the approved fixed configuration (yield_model.py); the
    # grouped CV below is the honest quality estimate and the test split is not
    # touched until it is reported.
    log("  -> Training served Yield model (HistGB on log(yield per hectare))...")
    yield_model = make_yield_model(RANDOM_STATE)
    yield_model.fit(X_train, y_train)
    log(f"     estimator: HistGradientBoostingRegressor({APPROVED_HYPERPARAMS}) "
        f"on log(Yield_Tonnes / Area_Hectares)")
    yp_train = regression_metrics(y_train, yield_model.predict(X_train))
    yp_cv = cv_regressor_grouped(yield_model, X_train, y_train, g_train)
    yp_test = regression_metrics(y_test, yield_model.predict(X_test))
    yp_oof = np.asarray(cross_val_predict(
        yield_model, X_train, y_train, groups=g_train,
        cv=GroupKFold(n_splits=CV_FOLDS)))
    # Honest reference point: predicting the TRAIN mean for every row.
    baseline = DummyRegressor(strategy="mean").fit(X_train, y_train)
    baseline_r2 = round(float(r2_score(y_test, baseline.predict(X_test))), 6)
    safe_pickle_save(yield_model, "models/yield_prediction/randomforest_model.pkl")
    log(f"  -> Yield classical (Model M): {format_reg(yp_train)} (train) | "
        f"CV(grouped) R2 {yp_cv['r2_mean']:.4f} | {format_reg(yp_test)} (test) | "
        f"mean-baseline test R2 {baseline_r2:.4f}")

    register_model(
        model_name="yield_prediction/randomforest_model.pkl", domain="yield", dataset_path=dataset["path"],
        algorithm="HistGradientBoostingRegressor on log(Yield_Tonnes / Area_Hectares) "
                  "(Model M; exp(pred) * area)",
        task="regression", features=columns, target="Yield_Tonnes (district total)",
        records=dataset["records"], features_count=int(X_oh.shape[1]), classes=None,
        hyper_params={**APPROVED_HYPERPARAMS,
                      "fit_target": "log(Yield_Tonnes / Area_Hectares)",
                      "inverse": "exp(pred) * Area_Hectares",
                      "selection": "fixed approved config; grouped CV by district-year "
                                   "(5-fold) on TRAIN only"},
        metrics={"train": yp_train, "cv": yp_cv, "test": yp_test,
                 "baseline_test": {"r2": baseline_r2, "strategy": "train-mean"}},
        generalization={"train_test_gap": round(yp_train["r2"] - yp_test["r2"], 6),
                        "status": gap_status(yp_train["r2"] - yp_test["r2"])},
        output_path="models/yield_prediction/randomforest_model.pkl",
        sample_counts={"train": len(idx_train), "test": len(idx_test),
                       "train_groups": int(len(set(g_train))),
                       "test_groups": int(len(set(groups[idx_test])))},
        notes=("Contract: Crop + Area_Hectares -> Yield_Tonnes; Season is NOT a feature "
               "(deprecated, never fabricated). Split and CV are grouped by district-year "
               "so the same evidence never appears on both sides. "
               f"Dataset: {info['records']} rows, {info['crops']} crops, "
               f"{info['districts']} districts, {info['years']} years."),
        provenance=dataset["provenance"],
    )

    # ---- XGBoost comparison model (or regularized GBR fallback) ----
    if XGBOOST_AVAILABLE:
        log("  -> Training XGBoost regressor (comparison model)...")
        xgb_model = XGBRegressor(n_estimators=150, max_depth=3, learning_rate=0.08,
                                 subsample=0.9, colsample_bytree=0.9, reg_lambda=1.0,
                                 random_state=RANDOM_STATE, n_jobs=-1)
        xgb_algorithm = "XGBoost Regressor"
    else:
        log("  -> XGBoost unavailable; training Gradient Boosting Regressor (logged fallback)...")
        xgb_model = GradientBoostingRegressor(n_estimators=150, max_depth=3, learning_rate=0.08,
                                              subsample=0.9, random_state=RANDOM_STATE)
        xgb_algorithm = "Gradient Boosting Regressor (XGBoost unavailable on this host)"
    xgb_model.fit(X_train, y_train)
    xgb_train = regression_metrics(y_train, xgb_model.predict(X_train))
    xgb_cv = cv_regressor_grouped(xgb_model, X_train, y_train, g_train)
    xgb_test = regression_metrics(y_test, xgb_model.predict(X_test))

    # Never downgrade a real XGBoost artifact to the sklearn fallback: on hosts
    # without libomp the existing models/xgb_model.pkl (trained with real
    # XGBoost elsewhere) is kept and only the registry entry records the
    # fallback's numbers.
    xgb_artifact_path = os.path.join(MODELS_DIR, "xgb_model.pkl")
    if XGBOOST_AVAILABLE or not os.path.exists(xgb_artifact_path):
        xgb_artifact_written = safe_pickle_save(xgb_model, "models/xgb_model.pkl")
        xgb_artifact_note = "" if xgb_artifact_written else " Artifact could not be written."
    else:
        xgb_artifact_written = False
        xgb_artifact_note = (" Existing models/xgb_model.pkl (real XGBoost) preserved — "
                             "this run's fallback numbers describe a different estimator "
                             "and were NOT written over it, so the registry marks this "
                             "entry artifact_written=false.")
        log("  -> Kept the existing models/xgb_model.pkl (real XGBoost artifact).")

    register_model(
        model_name="xgb_model.pkl", domain="yield", dataset_path=dataset["path"], algorithm=xgb_algorithm,
        task="regression", features=columns, target="Yield_Tonnes (district total)",
        records=dataset["records"], features_count=int(X_oh.shape[1]), classes=None,
        hyper_params={"n_estimators": 150, "max_depth": 3, "learning_rate": 0.08,
                      "cv": "GroupKFold(5) by district-year on TRAIN only"},
        metrics={"train": xgb_train, "cv": xgb_cv, "test": xgb_test},
        generalization={"train_test_gap": round(xgb_train["r2"] - xgb_test["r2"], 6),
                        "status": gap_status(xgb_train["r2"] - xgb_test["r2"])},
        output_path="models/xgb_model.pkl",
        sample_counts={"train": len(idx_train), "test": len(idx_test)},
        notes="Comparison model; /api/yield-prediction serves yield_prediction/randomforest_model.pkl."
              + xgb_artifact_note,
        provenance=dataset["provenance"],
        artifact_written=xgb_artifact_written,
    )
    log(f"  -> {xgb_algorithm}: {format_reg(xgb_train)} (train) | {format_reg(xgb_test)} (test)")

    # ---- Simulated quantum regressor ----
    log("  -> Training Quantum Yield model (simulated VQR)...")
    # Keeping the simulated regressor at a lower complexity than its default
    # (80 trees instead of 200) measurably narrows the train/test gap; the
    # parameters are chosen from the CV numbers, never from the test set.
    vqc_yield = SimulatedQuantumRegressor(n_components=8, alpha=0.01, epochs=40)
    vqc_yield.fit(X_train.to_numpy(dtype=float), y_train.to_numpy(dtype=float))
    vqr_train = regression_metrics(y_train, vqc_yield.predict(X_train.to_numpy(dtype=float)))
    vqr_cv = cv_regressor_grouped(vqc_yield, X_train.to_numpy(dtype=float),
                                  y_train.to_numpy(dtype=float), g_train)
    vqr_test = regression_metrics(y_test, vqc_yield.predict(X_test.to_numpy(dtype=float)))
    vqr_oof = np.asarray(cross_val_predict(
        vqc_yield, X_train.to_numpy(dtype=float), y_train.to_numpy(dtype=float),
        groups=g_train, cv=GroupKFold(n_splits=CV_FOLDS)))
    safe_pickle_save(vqc_yield, "models/vqc_yield_model.pkl")

    register_model(
        model_name="vqc_yield_model.pkl", domain="yield", dataset_path=dataset["path"],
        algorithm="Simulated Quantum Regressor (recorded-feature projection + gradient boosting)",
        task="regression", features=columns, target="Yield_Tonnes (district total)",
        records=dataset["records"], features_count=int(X_oh.shape[1]), classes=None,
        hyper_params={"n_components": 8, "alpha": 0.01, "epochs": 40},
        metrics={"train": vqr_train, "cv": vqr_cv, "test": vqr_test},
        generalization={"train_test_gap": round(vqr_train["r2"] - vqr_test["r2"], 6),
                        "status": gap_status(vqr_train["r2"] - vqr_test["r2"])},
        output_path="models/vqc_yield_model.pkl", simulated_quantum=True,
        sample_counts={"train": len(idx_train), "test": len(idx_test)},
        notes="Simulated quantum circuit stand-in; NOT quantum hardware execution.",
        provenance=dataset["provenance"],
    )
    log(f"  -> Simulated VQR: {format_reg(vqr_train)} (train) | {format_reg(vqr_test)} (test)")

    # Scalers / encoders kept for the legacy callers; no leakage (train fit only).
    safe_pickle_save(StandardScaler().fit(X_train), "models/yield_scaler.pkl")
    crop_enc = LabelEncoder().fit(X_raw["Crop"].iloc[idx_train].astype(str))
    safe_pickle_save(crop_enc, "models/yield_crop_encoder.pkl")
    # No Season encoder is written any more: Season is not part of the contract.
    # models/yield_season_encoder.pkl is a stale legacy artifact that nothing
    # serves from; it is left on disk rather than silently deleted, and no code
    # reads it (`app.py` only declares the name).
    log("  -> Season is not a model input; no yield_season_encoder is written.")

    # Key kept as "yield_pipe" for existing consumers; the value is now Model M.
    models = {"yield_pipe": yield_model, "xgb_model": xgb_model, "vqc_yield_model": vqc_yield}
    oof = {"classical": yp_oof, "vqc": vqr_oof}
    test_pred = {
        "classical": yield_model.predict(X_test),
        "vqc": vqc_yield.predict(X_test.to_numpy(dtype=float)),
    }
    return models, oof, test_pred, {
        "y_train": y_train.to_numpy(), "y_test": y_test.to_numpy(),
        "area_train": area_train, "area_test": area_test,
        "feature_columns": columns, "crops": crops, "dataset_info": info,
        "groups_train": g_train, "groups_test": groups[idx_test],
        "baseline_test_r2": baseline_r2,
    }


def train_seed(path, dataset):
    log("\n--- DATASET 3: Seed Viability ---")
    X_raw, y = load_seed_frame(path)
    idx_train, idx_test = train_test_split(
        np.arange(len(X_raw)), test_size=TEST_SPLIT, random_state=RANDOM_STATE, stratify=y)
    X_train_raw, X_test_raw = X_raw.iloc[idx_train], X_raw.iloc[idx_test]
    y_train, y_test = y.iloc[idx_train], y.iloc[idx_test]

    scaler = StandardScaler().fit(X_train_raw)  # fitted on TRAIN only
    X_train = scaler.transform(X_train_raw)
    X_test = scaler.transform(X_test_raw)
    n_classes = int(y.nunique())

    log(f"  -> Records: {len(X_raw)} | Features: {X_raw.shape[1]} | Classes: {n_classes} | "
        f"Train/Test: {len(idx_train)}/{len(idx_test)}")

    # ---- Served classical seed model: Random Forest on RAW (moisture, weight) ----
    log("  -> Training served Seed model (Random Forest on raw moisture / weight)...")
    seed_search = GridSearchCV(
        RandomForestClassifier(n_estimators=200, class_weight="balanced",
                               random_state=RANDOM_STATE, n_jobs=-1),
        {"max_depth": [4, 6, None], "min_samples_leaf": [1, 2]},
        cv=StratifiedKFold(n_splits=3, shuffle=True, random_state=RANDOM_STATE),
        scoring="accuracy", n_jobs=-1,
    )
    seed_search.fit(X_train_raw, y_train)
    seed_rf = seed_search.best_estimator_
    rf_train = classification_metrics(y_train, seed_rf.predict(X_train_raw))
    rf_cv = cv_classifier(seed_rf, X_train_raw, y_train)
    rf_test = classification_metrics(y_test, seed_rf.predict(X_test_raw))
    rf_oof = np.asarray(cross_val_predict(
        seed_rf, X_train_raw, y_train,
        cv=StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)))
    safe_pickle_save(seed_rf, "models/seed_viability/randomforest_model.pkl")

    register_model(
        model_name="seed_viability/randomforest_model.pkl", domain="seed", dataset_path=dataset["path"],
        algorithm="Random Forest Classifier (raw features)", task="classification",
        features=SEED_FEATURES, target="Viable",
        records=dataset["records"], features_count=2, classes=n_classes,
        hyper_params=seed_search.best_params_,
        metrics={"train": rf_train, "cv": rf_cv, "test": rf_test},
        generalization={"train_test_gap": round(rf_train["accuracy"] - rf_test["accuracy"], 6),
                        "status": gap_status(rf_train["accuracy"] - rf_test["accuracy"])},
        output_path="models/seed_viability/randomforest_model.pkl",
        sample_counts={"train": len(idx_train), "test": len(idx_test)},
        provenance=dataset["provenance"],
    )
    log(f"  -> Seed RF: {format_cls(rf_train)} (train) | {format_cls(rf_test)} (test)")

    # ---- SVM (comparison model, scaled features) ----
    log("  -> Training SVM (GridSearchCV on the train split)...")
    svm_search = GridSearchCV(
        SVC(probability=True, random_state=RANDOM_STATE),
        {"C": [0.1, 1, 10, 100],
         "gamma": ["scale", "auto", 0.01, 0.1],
         "kernel": ["rbf", "poly"]},
        cv=StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE),
        scoring="accuracy", n_jobs=-1,
    )
    svm_search.fit(X_train, y_train)
    svm_model = svm_search.best_estimator_
    svm_train = classification_metrics(y_train, svm_model.predict(X_train))
    svm_cv = {"accuracy_mean": round(float(svm_search.best_score_), 6),
              "accuracy_std": None, "folds": [], "best_params": svm_search.best_params_}
    svm_test = classification_metrics(y_test, svm_model.predict(X_test))
    safe_pickle_save(svm_model, "models/svm_model.pkl")
    safe_pickle_save(scaler, "models/seed_scaler.pkl")

    register_model(
        model_name="svm_model.pkl", domain="seed", dataset_path=dataset["path"], algorithm="Support Vector Classifier",
        task="classification", features=SEED_FEATURES, target="Viable",
        records=dataset["records"], features_count=2, classes=n_classes,
        hyper_params=svm_search.best_params_,
        metrics={"train": svm_train, "cv": svm_cv, "test": svm_test},
        generalization={"train_test_gap": round(svm_train["accuracy"] - svm_test["accuracy"], 6),
                        "status": gap_status(svm_train["accuracy"] - svm_test["accuracy"])},
        output_path="models/svm_model.pkl",
        sample_counts={"train": len(idx_train), "test": len(idx_test)},
        notes="Comparison model; /api/seed-viability serves seed_viability/randomforest_model.pkl.",
        provenance=dataset["provenance"],
    )
    log(f"  -> SVM: {format_cls(svm_train)} (train) | {format_cls(svm_test)} (test) "
        f"| best params: {svm_search.best_params_}")

    # ---- Simulated quantum seed classifier (scaled features) ----
    log("  -> Training Quantum Seed model (simulated VQC)...")
    vqc_seed = SimulatedQuantumClassifier()
    vqc_seed.fit(X_train, y_train)
    vqc_train = classification_metrics(y_train, vqc_seed.predict(X_train))
    vqc_cv = cv_classifier(vqc_seed, X_train, y_train)
    vqc_test = classification_metrics(y_test, vqc_seed.predict(X_test))
    vqc_oof = np.asarray(cross_val_predict(
        vqc_seed, X_train, y_train,
        cv=StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)))
    safe_pickle_save(vqc_seed, "models/vqc_seed_model.pkl")

    register_model(
        model_name="vqc_seed_model.pkl", domain="seed", dataset_path=dataset["path"],
        algorithm="Simulated Quantum Classifier (recorded-feature projection + linear learner)",
        task="classification", features=SEED_FEATURES, target="Viable",
        records=dataset["records"], features_count=2, classes=n_classes,
        hyper_params={"n_components": 12, "alpha": 0.001, "epochs": 100},
        metrics={"train": vqc_train, "cv": vqc_cv, "test": vqc_test},
        generalization={"train_test_gap": round(vqc_train["accuracy"] - vqc_test["accuracy"], 6),
                        "status": gap_status(vqc_train["accuracy"] - vqc_test["accuracy"])},
        output_path="models/vqc_seed_model.pkl", simulated_quantum=True,
        sample_counts={"train": len(idx_train), "test": len(idx_test)},
        notes="Simulated quantum circuit stand-in; NOT quantum hardware execution. "
              "Features are standardized with models/seed_scaler.pkl (train statistics).",
        provenance=dataset["provenance"],
    )
    log(f"  -> Simulated VQC (seed): {format_cls(vqc_train)} (train) | {format_cls(vqc_test)} (test)")

    models = {"seed_rf": seed_rf, "svm_model": svm_model, "vqc_seed_model": vqc_seed,
              "seed_scaler": scaler}
    oof = {"rf": rf_oof, "vqc": vqc_oof}
    test_pred = {"rf": seed_rf.predict(X_test_raw), "vqc": vqc_seed.predict(X_test)}
    return models, oof, test_pred, {"y_train": y_train.to_numpy(), "y_test": y_test.to_numpy(),
                                     "X_test_raw": X_test_raw}


# ---------------------------------------------------------------------------
# Meta model (out-of-fold stacking)
# ---------------------------------------------------------------------------
def train_meta(crop_oof, crop_test, crop_truth, yield_oof, yield_test, yield_truth,
               seed_oof, seed_test, seed_truth, n_crop_classes, feature_provenance=None,
               feature_composition=None):
    """Train the 6-feature success estimator with a strict stacking protocol.

    Features match exactly what /api/quantum-ml builds at inference time:
        [crop_rf/(K-1), crop_vqc/(K-1), yield_classical/50, yield_vqc/50,
         seed_classical(0/1), seed_vqc(0/1)]   (yield features clipped to [0, 1])

    Label (documented, computed from ground truth — never from the features):
        success = the three user-facing classical outputs are correct
                  (crop RF correct, yield classical within 25% per hectare,
                   seed RF correct). The quantum outputs stay as FEATURES: the
                  meta model learns how much a quantum opinion changes trust in
                  the classical answer. Requiring the simulated quantum models
                  to be correct as well would make the label mostly noise,
                  because their errors are close to independent of their output.
    """
    log("\n--- META-ENSEMBLE (out-of-fold stacking) ---")

    def build_triples(crop_p, crop_y, yield_p, yield_area, yield_true, seed_p, seed_y):
        """One meta row per crop row — full coverage, no duplicated triples.

        A meta row is one draw from the aggregate inference scenario: a crop
        prediction, a yield prediction and a seed prediction, each produced by a
        model that never saw that row (out-of-fold for TRAIN, fitted-on-TRAIN for
        TEST). Round-robin pairing keeps every crop row exactly once. The earlier
        version paired only ``min(len)`` rows and then replicated them 5x, which
        made every CV fold identical and hid the fact that the learner had
        collapsed to the majority class.

        ``groups`` is the yield row index, so the meta CV never treats the same
        yield row as independent evidence.
        """
        n_yield, n_seed = len(yield_p), len(seed_p)
        if n_yield == 0 or n_seed == 0 or len(crop_p) == 0:
            empty = np.empty((0, 6))
            return empty, np.empty((0,), dtype=int), np.empty((0,), dtype=int)
        rows, labels, groups = [], [], []
        for i in range(len(crop_p)):
            yi, si = i % n_yield, i % n_seed
            crop_rf_feat = crop_p[i][0] / (n_crop_classes - 1 + 1e-9)
            crop_vqc_feat = crop_p[i][1] / (n_crop_classes - 1 + 1e-9)
            y_class = float(yield_p[yi][0]) / max(float(yield_area[yi]), 1e-9)
            y_vqc = float(yield_p[yi][1]) / max(float(yield_area[yi]), 1e-9)
            rows.append([
                np.clip(crop_rf_feat, 0, 1), np.clip(crop_vqc_feat, 0, 1),
                np.clip(y_class / 50.0, 0, 1), np.clip(y_vqc / 50.0, 0, 1),
                # Encoded through the shared helper, matching app.py exactly.
                # For the current binary target this is identical to the previous
                # `float(seed_pred_index)`, so no existing meta feature changes.
                viable_flag_from_index(seed_p[si][0]),
                viable_flag_from_index(seed_p[si][1]),
            ])
            crop_ok = int(crop_p[i][0]) == int(crop_y[i])
            actual_per_ha = float(yield_true[yi]) / max(float(yield_area[yi]), 1e-9)
            tolerance = 0.25 * abs(actual_per_ha)
            yield_class_ok = abs(y_class - actual_per_ha) <= tolerance
            # Raw-index comparison: this is the CORRECTNESS test for the label, not a
            # feature encoding, so it deliberately does not go through the helper.
            seed_ok = int(seed_p[si][0]) == int(seed_y[si])
            labels.append(1 if (crop_ok and yield_class_ok and seed_ok) else 0)
            groups.append(yi)
        return (np.asarray(rows, dtype=float), np.asarray(labels, dtype=int),
                np.asarray(groups, dtype=int))

    X_meta_train, y_meta_train, groups_train = build_triples(
        crop_oof["predictions"], crop_truth["y_train"],
        yield_oof["predictions"], yield_truth["area_train"], yield_truth["y_true_train"],
        seed_oof["predictions"], seed_truth["y_train"])
    X_meta_test, y_meta_test, _ = build_triples(
        crop_test["predictions"], crop_truth["y_test"],
        yield_test["predictions"], yield_truth["area_test"], yield_truth["y_true_test"],
        seed_test["predictions"], seed_truth["y_test"])

    log(f"  -> Meta rows: {len(X_meta_train)} train (OOF) / {len(X_meta_test)} test | "
        f"features {X_meta_train.shape[1]} | unique train rows "
        f"{len(np.unique(X_meta_train, axis=0))}")
    log(f"  -> Success base rate: {y_meta_train.mean() * 100:.1f}% (train) / "
        f"{y_meta_test.mean() * 100:.1f}% (test) — a majority-class guess scores exactly this")

    if len(np.unique(y_meta_train)) < 2:
        raise RuntimeError(
            "Meta training cannot proceed honestly: only one success class is present "
            f"in the OOF training labels (success rate {y_meta_train.mean() * 100:.1f}%)."
        )

    # ---- Learner selection: grouped CV on TRAIN only (the TEST set is untouched) ----
    #
    # The numbers below are recorded here so the choice is not re-litigated later.
    # Every one of them was measured on TRAIN grouped CV only; the TEST set is never
    # touched during selection.
    #   Feature sets (candidate features built from base-model outputs, never from
    #   ground-truth columns or test labels):
    #       A = the 6 served features                               CV 0.7330  <- kept
    #       B = A + RF/VQC probability/confidence features           CV 0.7205  (lost)
    #       C = A + RF/VQC agreement indicators                      CV 0.7330  (tied)
    #       D = A + probability + agreement                          CV 0.7318  (lost)
    #   Agreement adds nothing measurable: crop RF is ~99% accurate whether or not
    #   the quantum crop model agrees, and seed failures show *more* RF/VQC agreement
    #   than successes (mean agreement 1.0000 vs 0.9306), so C only reproduces A.
    #   Probability/confidence features lose, so no extra feature is added.
    #   Learners on A:
    #       LogisticRegression(C=3.0, class_weight=None)              0.7330  <- selected
    #       class_weight="balanced" (any C)                           0.40-0.57 (much worse)
    #       DecisionTreeClassifier depth 2 / depth 3                  0.7080 / 0.6852
    #       RandomForestClassifier (conservative)                     0.7170
    #       GradientBoostingClassifier (conservative)                 0.6705
    #   Every non-linear / higher-capacity learner lands at or below the 0.7205
    #   majority base rate: with 1760 grouped rows they overfit. The mildly
    #   regularised linear model is both the simplest and the best honest option.
    candidates = []
    for _C in (0.05, 0.3, 1.0, 3.0):
        for _cw in (None, "balanced"):
            candidates.append((
                f"LogisticRegression(C={_C}, class_weight={_cw})",
                LogisticRegression(C=_C, max_iter=2000, random_state=RANDOM_STATE,
                                   class_weight=_cw),
            ))
    for _depth in (2, 3):
        candidates.append((
            f"DecisionTreeClassifier(max_depth={_depth})",
            DecisionTreeClassifier(max_depth=_depth, random_state=RANDOM_STATE),
        ))
    # Conservative ensembles, kept inside the selection loop so the Phase-5 learner
    # comparison is reproducible straight from the pipeline (not from a scratch script).
    candidates.append((
        "RandomForestClassifier(n_estimators=100, max_depth=3, min_samples_leaf=5)",
        RandomForestClassifier(n_estimators=100, max_depth=3, min_samples_leaf=5,
                               random_state=RANDOM_STATE),
    ))
    candidates.append((
        "GradientBoostingClassifier(n_estimators=60, max_depth=2, learning_rate=0.05)",
        GradientBoostingClassifier(n_estimators=60, max_depth=2, learning_rate=0.05,
                                   random_state=RANDOM_STATE),
    ))

    n_groups = len(np.unique(groups_train))
    n_splits = int(min(CV_FOLDS, n_groups))
    try:
        cv_split = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_STATE)
        cv_scheme = f"StratifiedGroupKFold({n_splits}) grouped by yield row (TRAIN only)"
    except Exception:  # infeasible stratification for tiny data
        cv_split = GroupKFold(n_splits=n_splits)
        cv_scheme = f"GroupKFold({n_splits}) grouped by yield row (TRAIN only)"

    scored = []
    for name, estimator in candidates:
        fold_scores = []
        for tr_idx, te_idx in cv_split.split(X_meta_train, y_meta_train, groups_train):
            estimator.fit(X_meta_train[tr_idx], y_meta_train[tr_idx])
            fold_scores.append(float(accuracy_score(
                y_meta_train[te_idx], estimator.predict(X_meta_train[te_idx]))))
        scored.append((float(np.mean(fold_scores)), float(np.std(fold_scores)), name,
                       estimator, fold_scores))
    # Ties keep the earlier (simpler) candidate: Python's sort is stable and the
    # candidate list is ordered simplest-first (mild LR before trees before ensembles).
    scored.sort(key=lambda item: item[0], reverse=True)
    best_mean, best_std, best_name, meta_model, best_folds = scored[0]
    base_rate_train = float(y_meta_train.mean())
    log(f"  -> Meta learner selected by CV on TRAIN: {best_name} "
        f"(CV {best_mean * 100:.2f}%, std {best_std * 100:.2f}, "
        f"lift {best_mean - base_rate_train:+.4f} over the base rate)")
    for _mean, _std, _name, _est, _folds in scored[:5]:
        log(f"     candidate {_name}: CV {_mean * 100:.2f}% (std {_std * 100:.2f})")
    log(f"     {len(scored)} learner candidates evaluated on TRAIN grouped CV; "
        f"majority base rate {base_rate_train * 100:.2f}%")

    meta_model.fit(X_meta_train, y_meta_train)

    meta_train = classification_metrics(y_meta_train, meta_model.predict(X_meta_train))
    meta_test_pred = meta_model.predict(X_meta_test)
    meta_test = classification_metrics(y_meta_test, meta_test_pred)
    meta_confusion = confusion_matrix(y_meta_test, meta_test_pred).tolist()
    meta_cv = {
        "accuracy_mean": round(best_mean, 6),
        "accuracy_std": round(best_std, 6),
        "folds": [round(s, 6) for s in best_folds],
        "scheme": cv_scheme,
        "base_rate": round(base_rate_train, 6),
        "lift_over_base_rate": round(best_mean - base_rate_train, 6),
    }
    meta_gap = meta_train["accuracy"] - meta_test["accuracy"]

    safe_pickle_save(meta_model, "models/meta_model.pkl")

    register_model(
        model_name="meta_model.pkl", domain="meta",
        dataset_path="Out-of-fold predictions from crop/yield/seed train splits",
        algorithm=f"Stacking meta model ({best_name})",
        task="classification",
        features=["rf_crop_pred", "qml_crop_pred", "yield_classical_pred", "yield_vqc_pred",
                  "svm_seed_pred", "qml_seed_pred"],
        target="Hybrid-stack success (three user-facing classical outputs correct)",
        records=int(len(X_meta_train) + len(X_meta_test)),
        features_count=6, classes=2,
        hyper_params={"selected": best_name, "cv_mean": round(best_mean, 6),
                      "cv_std": round(best_std, 6), "cv_scheme": cv_scheme,
                      "random_state": RANDOM_STATE,
                      "candidates_evaluated": len(scored),
                      "candidate_cv": {name: round(mean, 6)
                                       for mean, _std, name, _est, _folds in scored}},
        metrics={"train": meta_train, "cv": meta_cv, "test": meta_test,
                 "confusion_matrix": meta_confusion,
                 "base_rate_train": round(base_rate_train, 6),
                 "base_rate_test": round(float(y_meta_test.mean()), 6)},
        generalization={"train_test_gap": round(meta_gap, 6), "status": gap_status(meta_gap)},
        output_path="models/meta_model.pkl",
        # The meta row is a stack of base-model outputs, so its provenance is the
        # provenance of those base datasets — recorded explicitly because one of
        # the three legs is synthetic and this entry must never look real.
        # dataset_synthetic=true here follows the registry schema ("provenance
        # contains 'synthetic'"); dataset_composition records the per-leg detail
        # so the boolean is never read as "the whole stack is synthetic".
        provenance=feature_provenance,
        dataset_composition=feature_composition,
        sample_counts={"train": int(len(X_meta_train)), "test": int(len(X_meta_test))},
        notes=("Trained on out-of-fold TRAIN predictions only; evaluated on untouched TEST "
               "predictions. Label = crop RF, yield classical and seed RF all correct. "
               "Learner chosen by grouped CV on TRAIN; accuracy is always reported next to "
               "the majority-class base rate because this conjunction label is dominated by "
               "the small yield/seed test subsets. The served 6-feature set was compared "
               "against added RF/VQC probability-confidence and agreement features on TRAIN "
               "grouped CV: agreement merely ties it and probability features lose, so no "
               "candidate feature was adopted."),
    )
    log(f"  -> Meta: {format_cls(meta_train)} (train) | {format_cls(meta_test)} (test) | "
        f"confusion (test) {meta_confusion}")

    model_entry = {
        "domain": "meta", "key": "meta_model",
        "name": f"Meta Ensemble (OOF stacking, {best_name})",
        "task": "classification", "artifact": "models/meta_model.pkl",
        "simulated_quantum": False, "records": int(len(X_meta_train) + len(X_meta_test)),
        "features": 6, "classes": 2,
        "params": {"selected": best_name, "random_state": RANDOM_STATE,
                   "candidates_evaluated": len(scored)},
        "sample_counts": {"train": int(len(X_meta_train)), "test": int(len(X_meta_test))},
        "train": meta_train, "cv": meta_cv, "test": meta_test,
        "confusion_matrix": meta_confusion,
        "base_rate_train": round(base_rate_train, 6),
        "base_rate_test": round(float(y_meta_test.mean()), 6),
        "gap": round(meta_gap, 6),
        "gap_status": gap_status(meta_gap),
        "label_definition": (
            "the three user-facing classical outputs are correct: crop RF correct, "
            "yield classical within 25% per hectare, seed RF correct"),
    }
    return meta_model, model_entry, (X_meta_train, y_meta_train, X_meta_test, y_meta_test)


def cv_accuracy_kfold(est, X, y):
    """K-fold CV fallback when a stratified split is impossible (tiny minority)."""
    scores = cross_val_score(est, X, y, cv=KFold(n_splits=CV_FOLDS, shuffle=True,
                                                 random_state=RANDOM_STATE), scoring="accuracy")
    return {"accuracy_mean": round(float(np.mean(scores)), 6),
            "accuracy_std": round(float(np.std(scores)), 6),
            "folds": [round(float(s), 6) for s in scores]}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(report_path=DEFAULT_REPORT_FILE):
    started = time.time()
    log("=" * 58)
    log("🌱 SeedIQ — Retraining & Honest Evaluation Pipeline")
    log("=" * 58)
    log(f"Run ID: {RUN_ID} | random_state={RANDOM_STATE} | test_split={TEST_SPLIT:.0%} | cv={CV_FOLDS}-fold")
    if not XGBOOST_AVAILABLE:
        log("⚠️ XGBoost unavailable on this host — Gradient Boosting Regressor fallback is logged.")
    log("Quantum mode: SIMULATED classical stand-ins (no quantum hardware execution).")

    datasets, generated, missing = ensure_datasets()
    allow_synthetic = _synthetic_fallback_allowed()
    if generated:
        log(f"Generated missing fallback datasets for: {', '.join(generated)} (flagged synthetic).")
    if missing:
        log(f"⚠️ Missing dataset(s), NOT fabricated: {', '.join(missing)}. "
            f"Set SEEDIQ_ALLOW_SYNTHETIC_FALLBACK=1 to opt into clearly-flagged synthetic "
            f"stand-ins, or restore the real dataset files.")
    log("\n--- DATASET SCAN ---")
    ds_meta = {}
    for domain in ("crop", "yield", "seed"):
        meta = dataset_meta(domain, datasets.get(domain), generated)
        ds_meta[domain] = meta
        flag = "synthetic" if meta["synthetic"] else "provided"
        kind = meta.get("derivation_kind")
        deriv_txt = ("" if meta.get("target_largely_derivable_from_inputs") is None else
                     (" | target input-derivable"
                      if meta["target_largely_derivable_from_inputs"]
                      else " | target not input-derivable"))
        log(f"  ✓ {domain.title():5s}: {meta['path']} ({flag}, {meta['records']} records, "
            f"{meta['features']} features, {meta['classes']} classes{deriv_txt}; "
            f"missing {meta['missing_values']}, duplicates {meta['duplicate_rows']})")
        if kind == "generator_derivable":
            log(f"     ⚠️ {domain}: input-only CV "
                f"{meta['input_only_cv']:.3f} ({meta['input_only_cv_metric']}) — "
                f"target is generator-derivable; do not read this domain's metrics as "
                f"real-world performance.")
        log(f"     audit: target cardinality {meta['target_cardinality']} | "
            f"max |corr(input,target)| {meta['max_abs_target_input_correlation']} | "
            f"majority class rate {meta['majority_class_rate']} | "
            f"duplicate feature vectors {meta['duplicate_feature_vectors']} | "
            f"constant-target groups {meta['constant_target_group_fraction']}"
            + (f" | best simple rule agreement {meta['best_simple_rule_agreement']}"
               if meta.get("best_simple_rule_agreement") is not None else ""))
        if meta.get("target_exactly_determined_by_inputs"):
            log(f"     ⚠️ {domain}: EXACTLY determined by the inputs — only "
                f"{meta['distinct_yield_per_ha_values']} distinct yield-per-hectare values across "
                f"{meta['records']} rows with zero within-cell variance; row-to-row variation is "
                f"absent, so this target is a deterministic encoding of (Crop, Area).")
        if kind == "input_range_determined":
            log(f"     ℹ️ {domain}: input-only CV {meta['input_only_cv']:.3f} "
                f"({meta['input_only_cv_metric']}) — the label is largely determined by "
                f"this table's own input ranges; treat the score as within-dataset "
                f"separability rather than field generalization.")
        else:
            log(f"     ℹ️ {domain}: {meta.get('quality_note')}")
        REPORT["datasets"].append(meta)

    REPORT["data_integrity"] = {
        "synthetic_fallback_allowed": allow_synthetic,
        "synthetic_fallback_generated": generated,
        "datasets_missing": missing,
        "synthetic_domains": [m["domain"] for m in ds_meta.values() if m["synthetic"]],
        "targets_derivable_from_inputs": [
            m["domain"] for m in ds_meta.values()
            if m.get("target_largely_derivable_from_inputs")],
        "generator_derivable_domains": [
            m["domain"] for m in ds_meta.values()
            if m.get("derivation_kind") == "generator_derivable"],
        "real_data_domains": [m["domain"] for m in ds_meta.values() if not m["synthetic"]],
        "warning": (
            "Metrics for " + ", ".join(sorted(m["domain"] for m in ds_meta.values()
                                              if m["synthetic"])) +
            " are measured on synthetic, generator-derived data and must not be presented "
            "as real-world agricultural performance."
            if any(m["synthetic"] for m in ds_meta.values()) else
            "All three domains are backed by provided real data; no synthetic stand-ins "
            "were generated in this run."
        ),
    }

    if not all(datasets.get(d) for d in ("crop", "yield", "seed")):
        absent = [d for d in ("crop", "yield", "seed") if not datasets.get(d)]
        raise RuntimeError(
            "Missing required dataset(s): " + ", ".join(absent) + ". Training is reported "
            "as incomplete instead of being silently run on fabricated rows. Restore the "
            "dataset files, or set SEEDIQ_ALLOW_SYNTHETIC_FALLBACK=1 to opt into generating "
            "clearly-flagged synthetic stand-ins."
        )

    # --- Crop ---
    crop_models, crop_oof, crop_test_pred, crop_y_train, crop_y_test, n_crop_classes = \
        train_crop(datasets["crop"], ds_meta["crop"])

    # --- Yield ---
    yield_models, yield_oof, yield_test_pred, yield_truth = \
        train_yield(datasets["yield"], ds_meta["yield"])

    # --- Seed ---
    seed_models, seed_oof, seed_test_pred, seed_truth = \
        train_seed(datasets["seed"], ds_meta["seed"])

    # --- Meta (strict OOF stacking) ---
    # OOF vectors are (classical, quantum) pairs; area/truth arrays supply labels.
    yield_truth["y_true_train"] = np.asarray(yield_truth["y_train"], dtype=float)
    yield_truth["y_true_test"] = np.asarray(yield_truth["y_test"], dtype=float)
    meta_model, meta_entry, _ = train_meta(
        crop_oof={"predictions": np.column_stack([crop_oof["rf"], crop_oof["vqc"]])},
        crop_test={"predictions": np.column_stack([crop_test_pred["rf"], crop_test_pred["vqc"]])},
        crop_truth={"y_train": crop_y_train, "y_test": crop_y_test},
        yield_oof={"predictions": np.column_stack([yield_oof["classical"], yield_oof["vqc"]])},
        yield_test={"predictions": np.column_stack([yield_test_pred["classical"], yield_test_pred["vqc"]])},
        yield_truth=yield_truth,
        seed_oof={"predictions": np.column_stack([seed_oof["rf"], seed_oof["vqc"]])},
        seed_test={"predictions": np.column_stack([seed_test_pred["rf"], seed_test_pred["vqc"]])},
        seed_truth={"y_train": seed_truth["y_train"], "y_test": seed_truth["y_test"]},
        n_crop_classes=n_crop_classes,
        feature_provenance=(
            "Stacked OOF/TEST predictions from base models trained on: crop={}, "
            "yield={}, seed={}".format(ds_meta["crop"]["provenance"],
                                       ds_meta["yield"]["provenance"],
                                       ds_meta["seed"]["provenance"])),
        feature_composition={
            "crop": {"provenance": ds_meta["crop"]["provenance"],
                     "synthetic": bool(ds_meta["crop"].get("synthetic"))},
            "yield": {"provenance": ds_meta["yield"]["provenance"],
                      "synthetic": bool(ds_meta["yield"].get("synthetic"))},
            "seed": {"provenance": ds_meta["seed"]["provenance"],
                     "synthetic": bool(ds_meta["seed"].get("synthetic"))},
            "any_synthetic": True,
            "note": ("Meta input is a stack of base-model outputs. Only the seed leg is "
                     "synthetic; crop and yield are provided datasets. dataset_synthetic="
                     "true above means 'at least one input leg is synthetic', not that "
                     "the whole stack is synthetic."),
        },
    )

    # --- Assemble the structured report from the registry entries of this run ---
    with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
        registry = json.load(f)
    run_entries = [e for e in registry if e.get("run_id") == RUN_ID]
    REPORT["registry_entries_added"] = len(run_entries)
    for entry in run_entries:
        if entry["model_name"] == "meta_model.pkl":
            continue  # added below with the documented label definition
        REPORT["models"].append({
            "domain": entry.get("domain"),
            "name": entry["algorithm"], "artifact": "models/" + entry["model_name"],
            "task": entry["task"], "train": entry["metrics"].get("train"),
            "cv": entry["metrics"].get("cv"), "test": entry["metrics"].get("test"),
            "params": entry["hyperparameters"], "gap": entry["generalization"]["train_test_gap"],
            "gap_status": entry["generalization"]["status"],
            "simulated_quantum": entry["simulated_quantum"],
            "dataset_provenance": entry.get("dataset_provenance"),
            "features": entry.get("features_count"),
            "classes": entry.get("classes"),
            "sample_counts": entry.get("sample_counts"),
        })
    REPORT["meta"] = meta_entry
    REPORT["models"].append(meta_entry)

    biggest = max(REPORT["models"], key=lambda m: abs(m["gap"]))
    statuses = {m["gap_status"] for m in REPORT["models"]}
    overall = "high" if "high" in statuses else ("moderate" if "moderate" in statuses else "good")
    REPORT["generalization"] = {
        "status": overall,
        "max_gap_model": biggest["name"],
        "max_gap": biggest["gap"],
        "summary": ("All models generalize within the good band (train/test gap ≤ 5 points)."
                    if overall == "good" else
                    "Some models show a moderate train/test gap — inspect the per-model metrics."
                    if overall == "moderate" else
                    "At least one model shows a large train/test gap — inspect the per-model metrics."),
    }
    REPORT["success"] = True
    REPORT["duration_seconds"] = round(time.time() - started, 1)

    log("\n--- GENERALIZATION CHECK ---")
    log(f"  Largest train/test gap: {abs(biggest['gap']) * 100:.2f} points ({biggest['name']})")
    log(f"  Status: {overall.upper()} — {REPORT['generalization']['summary']}")
    log(f"\nPipeline finished in {REPORT['duration_seconds']}s. "
        f"Report: {os.path.relpath(report_path, BASE_DIR)}")
    log(f"Registry entries appended: {REPORT['registry_entries_added']}\n")

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(REPORT, f, indent=2)
    return REPORT


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SeedIQ retraining & evaluation pipeline")
    parser.add_argument("--report", default=DEFAULT_REPORT_FILE,
                        help="Path of the structured JSON report (default: reports/retrain_report.json)")
    args = parser.parse_args()
    try:
        main(args.report)
    except Exception as exc:  # make failures machine-readable for /api/retrain
        REPORT["success"] = False
        REPORT["error"] = f"{type(exc).__name__}: {exc}"
        os.makedirs(os.path.dirname(args.report), exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(REPORT, f, indent=2)
        log(f"❌ Pipeline failed: {REPORT['error']}")
        sys.exit(1)
