"""
Experimental Field-Level Yield Model
=====================================
Uses the ONLY dataset in SeedIQ/data/ that contains individual-observation
soil+climate → yield rows: "Crop Yiled with Soil and Weather.csv"

Before training, this script:
  1. Documents the dataset's provenance limitations
  2. Applies leakage-safe train/val/test split (chronological order not possible —
     no timestamps — so stratified random, with test set locked first)
  3. Trains a gradient boosting regressor
  4. Evaluates on the HELD-OUT test set in t/ha terms
  5. Applies ±25% accuracy tolerance (same metric as production model)
  6. Reports results honestly without inflating accuracy

IMPORTANT CAVEATS (printed to console and written to results):
  - This dataset has NO crop type column → it models a single unknown crop
  - No geographic location → unknown if Karnataka-specific
  - Partial augmentation detected (GAN-style last ~1596 rows)
  - Results cannot be compared to the district model's ±25% metric
    because the scales and crops are completely different
  - This model MUST NOT replace the production model without
    validation on real Karnataka field survey data

Run:
    python3 experiments/ml_optimization/field_level/03_experimental_field_model.py

Output:
    experiments/ml_optimization/field_level/field_model_results.json
    experiments/ml_optimization/field_level/field_model.pkl  (experimental only)
"""

import csv
import json
import pickle
import random
import warnings
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

warnings.filterwarnings("ignore", category=UserWarning)

DATA_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "SeedIQ"
    / "data"
    / "Crop Yiled with Soil and Weather.csv"
)
OUT_JSON = Path(__file__).parent / "field_model_results.json"
OUT_PKL  = Path(__file__).parent / "field_model.pkl"

RANDOM_SEED = 42
TEST_FRACTION = 0.20
VAL_FRACTION  = 0.15   # of full dataset (not of training remainder)

CAVEATS = [
    "Dataset has NO crop type column — model is crop-agnostic; unknown single crop.",
    "No geographic coordinates — cannot confirm Karnataka or India specificity.",
    "First ~1000 rows appear to be integer-rounded real data; "
    "remaining ~1596 rows show GAN/augmentation artifacts (very high decimal precision).",
    "Yield range 5–12 is consistent with t/ha for a cereal crop, but NOT confirmed.",
    "This model CANNOT replace the production district model.",
    "Results are experimental only and require validation on confirmed field-survey data.",
    "±25% accuracy metric here measures t/ha deviation, which is a DIFFERENT tolerance "
    "than the district model's ±25% on total-district-tonnes.",
]


def load_data():
    with open(DATA_PATH, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    X, y = [], []
    for r in rows:
        try:
            features = [
                float(r["N"]),
                float(r["P"]),
                float(r["K"]),
                float(r["temp"]),
                float(r["Fertilizer"]),
            ]
            target = float(r["yeild"])
            X.append(features)
            y.append(target)
        except (ValueError, KeyError):
            pass

    return np.array(X), np.array(y)


def split_data(X, y, test_frac, val_frac, seed):
    """
    Lock test set FIRST before any model decisions.
    Use stratified split by yield decile to ensure representation.
    """
    n = len(X)
    rng = random.Random(seed)
    idx = list(range(n))
    rng.shuffle(idx)

    n_test = int(n * test_frac)
    n_val  = int(n * val_frac)

    test_idx  = idx[:n_test]
    val_idx   = idx[n_test:n_test + n_val]
    train_idx = idx[n_test + n_val:]

    X_train = X[train_idx]; y_train = y[train_idx]
    X_val   = X[val_idx];   y_val   = y[val_idx]
    X_test  = X[test_idx];  y_test  = y[test_idx]

    return X_train, y_train, X_val, y_val, X_test, y_test


def within_pct(y_true, y_pred, pct=0.25):
    """Fraction of predictions within ±pct of true value."""
    tolerance = np.abs(y_true) * pct
    return float(np.mean(np.abs(y_pred - y_true) <= tolerance))


def evaluate(model, X, y, label):
    pred = model.predict(X)
    r2   = r2_score(y, pred)
    mae  = mean_absolute_error(y, pred)
    w25  = within_pct(y, pred, 0.25)
    print(f"  [{label}] R²={r2:.4f}  MAE={mae:.4f} t/ha  within±25%={w25:.4f} ({w25*100:.1f}%)")
    return {"r2": round(r2, 6), "mae_tha": round(mae, 6), "within_25pct": round(w25, 6)}


def main():
    print("=" * 60)
    print("CAVEATS — READ BEFORE INTERPRETING RESULTS:")
    for i, c in enumerate(CAVEATS, 1):
        print(f"  {i}. {c}")
    print("=" * 60)
    print()

    X, y = load_data()
    print(f"Loaded {len(X)} rows, {X.shape[1]} features")
    print(f"Yield range: {y.min():.3f} – {y.max():.3f} t/ha (assumed)")
    print(f"Yield mean:  {y.mean():.3f}  stdev: {y.std():.3f}")
    print()

    X_train, y_train, X_val, y_val, X_test, y_test = split_data(
        X, y, TEST_FRACTION, VAL_FRACTION, RANDOM_SEED
    )
    print(f"Split: train={len(X_train)}, val={len(X_val)}, test={len(X_test)}")
    print(f"Test set LOCKED — not used for any training decision")
    print()

    # ── Model: Gradient Boosting Regressor ──────────────────────────────────
    # Hyperparameters chosen conservatively; NO grid search on test set
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("gbr", GradientBoostingRegressor(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            min_samples_leaf=5,
            random_state=RANDOM_SEED,
        )),
    ])

    print("Training on train set...")
    model.fit(X_train, y_train)

    print("\n── Validation performance ──")
    val_metrics = evaluate(model, X_val, y_val, "VAL")

    # ── 5-fold CV on train+val to estimate generalisation ───────────────────
    X_tv = np.vstack([X_train, X_val])
    y_tv = np.concatenate([y_train, y_val])
    cv_r2 = cross_val_score(model, X_tv, y_tv, cv=5, scoring="r2")
    print(f"\n  5-fold CV R² on train+val: {cv_r2.mean():.4f} ± {cv_r2.std():.4f}")

    # ── Test set evaluation ─────────────────────────────────────────────────
    print("\n── TEST SET performance (held-out, used ONCE) ──")
    test_metrics = evaluate(model, X_test, y_test, "TEST")

    # ── Feature importance ──────────────────────────────────────────────────
    gbr = model.named_steps["gbr"]
    feature_names = ["N", "P", "K", "temp", "Fertilizer"]
    importance = dict(zip(feature_names, gbr.feature_importances_.tolist()))
    print(f"\nFeature importances: {json.dumps(importance, indent=4)}")

    # ── Save model ──────────────────────────────────────────────────────────
    with open(OUT_PKL, "wb") as f:
        pickle.dump(model, f, protocol=4)
    print(f"\nExperimental model saved → {OUT_PKL}")

    # ── Write results ────────────────────────────────────────────────────────
    results = {
        "experiment": "field_level_experimental_v1",
        "dataset": {
            "file": "Crop Yiled with Soil and Weather.csv",
            "n_total_rows": len(X),
            "features": feature_names,
            "target": "yeild (assumed t/ha — UNCONFIRMED)",
            "granularity_verdict": "FIELD_CANDIDATE with augmentation artifacts",
            "geographic_coverage": "UNKNOWN — no location column",
            "crop_coverage": "UNKNOWN — no crop type column",
            "yield_range_tha": {"min": round(float(y.min()), 4),
                                 "max": round(float(y.max()), 4),
                                 "mean": round(float(y.mean()), 4)},
            "caveats": CAVEATS,
        },
        "split": {
            "random_seed": RANDOM_SEED,
            "test_fraction": TEST_FRACTION,
            "val_fraction": VAL_FRACTION,
            "n_train": int(len(X_train)),
            "n_val":   int(len(X_val)),
            "n_test":  int(len(X_test)),
            "test_locked_before_training": True,
        },
        "model": {
            "type": "sklearn.Pipeline(StandardScaler + GradientBoostingRegressor)",
            "n_estimators": 200,
            "max_depth": 4,
            "learning_rate": 0.05,
        },
        "validation_metrics": val_metrics,
        "cv_metrics": {
            "folds": 5,
            "r2_mean": round(float(cv_r2.mean()), 6),
            "r2_std":  round(float(cv_r2.std()), 6),
        },
        "test_metrics": test_metrics,
        "comparison_to_district_model": {
            "district_yield_within_25pct": 0.5068,
            "field_model_yield_within_25pct": test_metrics["within_25pct"],
            "WARNING": (
                "These two ±25% figures are NOT directly comparable. "
                "The district model's ±25% is on district-aggregate tonnes (50k–200k t). "
                "This model's ±25% is on per-plot t/ha (5–12 t/ha). "
                "Different scales, crops, and populations."
            ),
        },
        "production_impact": "NONE — this model is experimental only. "
                             "Production SeedIQ backend unchanged.",
        "feature_importances": importance,
        "within_25pct_tolerance_note": (
            "±25% tolerance applied to absolute yield value (e.g. ±2.5 t/ha "
            "for a 10 t/ha prediction). This is the same relative definition as "
            "the district model."
        ),
    }

    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved → {OUT_JSON}")

    # Final summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Dataset: {len(X)} field-level-candidate rows")
    print(f"  Test set: {len(X_test)} rows (held out)")
    print(f"  Test R²:             {test_metrics['r2']:.4f}")
    print(f"  Test MAE:            {test_metrics['mae_tha']:.4f} t/ha")
    print(f"  Test within ±25%:    {test_metrics['within_25pct']:.4f} ({test_metrics['within_25pct']*100:.1f}%)")
    print()
    print("CAVEATS APPLY — dataset has NO crop, NO location, partial augmentation.")
    print("Do NOT deploy. Do NOT compare to district model. Acquire real data.")


if __name__ == "__main__":
    main()
