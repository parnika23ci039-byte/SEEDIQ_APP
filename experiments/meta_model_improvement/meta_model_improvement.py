#!/usr/bin/env python3
"""
SeedIQ Meta Model Improvement — Phase 13 Bounded Task
======================================================
Scope: Seed Viability classifier — the one measurable sub-component of the
       Meta Model pipeline with real labels, reproducible evaluation, and
       a clear accuracy metric.

Findings:
  1. The production meta_model.pkl (RFC binary 0/1, 6 features) has
     SYNTHETIC labels (no real ground-truth for "overall success") — cannot
     be improved without genuine labels.
  2. The stacking model in train_final_meta_and_compare.py is NOT what
     production serves — a train–serve mismatch exists.
  3. The ONLY measurable real-label sub-component is Seed Viability
     (210 rows, 3 classes, 7 acoustic/morphological wheat-kernel features).
  4. The existing clean_dataset() has a sequential outlier-clip bug that
     drops 29 rows (210→181) via index misalignment — causing different
     train/test splits than intended.

Correction applied (Task 2):
  - Use all 210 rows (no buggy outlier clip on a 7-feature, clean dataset).
  - Same stratified 80/20 split (random_state=42).
  - Preprocessor fitted only inside training folds (never on test).
  - One candidate: GradientBoostingClassifier — chosen from 5-fold CV on
    training data only; holdout evaluated ONCE.

Reproducibility:
  python3 experiments/meta_model_improvement/meta_model_improvement.py
"""

import json
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    accuracy_score, f1_score, precision_score, recall_score,
    confusion_matrix, classification_report
)
import warnings
warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[2]
DATA_CSV  = REPO / "SeedIQ" / "data" / "Seed_Data.csv"
OUT_DIR   = Path(__file__).resolve().parent
OUT_JSON  = OUT_DIR / "metrics.json"
MODEL_OUT = OUT_DIR / "seed_viability_gbm_candidate.pkl"

SEED = 42
TEST_SIZE = 0.20


def load_data():
    df = pd.read_csv(DATA_CSV)
    X = df.drop("target", axis=1).reset_index(drop=True)
    y = df["target"].reset_index(drop=True)
    return X, y


def build_baseline(X_tr, y_tr, X_te, y_te):
    """RF n=50 — matches current production configuration."""
    pipe = Pipeline([
        ("sc", StandardScaler()),
        ("clf", RandomForestClassifier(n_estimators=50, random_state=SEED))
    ])
    pipe.fit(X_tr, y_tr)
    return evaluate(pipe, X_tr, y_tr, X_te, y_te, "RF50 (baseline)")


def build_candidate(X_tr, y_tr, X_te, y_te):
    """GradientBoostingClassifier — selected via 5-fold CV on training data only."""
    pipe = Pipeline([
        ("sc", StandardScaler()),
        ("clf", GradientBoostingClassifier(
            n_estimators=200, max_depth=3, learning_rate=0.05, random_state=SEED
        ))
    ])
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    cv_scores = cross_val_score(pipe, X_tr, y_tr, cv=cv, scoring="accuracy")
    pipe.fit(X_tr, y_tr)
    result = evaluate(pipe, X_tr, y_tr, X_te, y_te, "GBM200 (candidate)")
    result["cv_accuracy_mean"] = round(float(cv_scores.mean()), 6)
    result["cv_accuracy_std"]  = round(float(cv_scores.std()),  6)
    return pipe, result


def evaluate(pipe, X_tr, y_tr, X_te, y_te, name):
    y_pred_te = pipe.predict(X_te)
    y_pred_tr = pipe.predict(X_tr)
    acc_te  = float(accuracy_score(y_te, y_pred_te))
    acc_tr  = float(accuracy_score(y_tr, y_pred_tr))
    f1_te   = float(f1_score(y_te, y_pred_te, average="macro", zero_division=0))
    prec_te = float(precision_score(y_te, y_pred_te, average="macro", zero_division=0))
    rec_te  = float(recall_score(y_te, y_pred_te, average="macro", zero_division=0))
    cm      = confusion_matrix(y_te, y_pred_te).tolist()
    correct = int(accuracy_score(y_te, y_pred_te, normalize=False))
    return {
        "name": name,
        "train_accuracy": round(acc_tr, 6),
        "test_accuracy":  round(acc_te, 6),
        "test_correct":   correct,
        "test_total":     len(y_te),
        "test_macro_f1":  round(f1_te, 6),
        "test_macro_precision": round(prec_te, 6),
        "test_macro_recall":    round(rec_te, 6),
        "confusion_matrix": cm,
    }


def leakage_check(X_tr, X_te, y_tr, y_te):
    """Verify no test rows appear in training set."""
    tr_set = set(map(tuple, X_tr.values.tolist()))
    te_overlap = sum(1 for row in X_te.values.tolist() if tuple(row) in tr_set)
    return {"test_rows_in_train": te_overlap, "leakage_detected": te_overlap > 0}


def main():
    print("=== SeedIQ Meta Model Improvement ===\n")

    X, y = load_data()
    print(f"Dataset: {len(X)} rows × {X.shape[1]} features")
    print(f"Classes: {dict(y.value_counts().sort_index())}")

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=SEED, stratify=y
    )
    print(f"Train: {len(X_tr)}, Test: {len(X_te)}\n")

    # Leakage check
    lc = leakage_check(X_tr, X_te, y_tr, y_te)
    print(f"Leakage check: {lc}")

    # Baseline
    base_result = build_baseline(X_tr, y_tr, X_te, y_te)
    print(f"\nBaseline  — test acc: {base_result['test_accuracy']:.4f} "
          f"({base_result['test_correct']}/{base_result['test_total']}), "
          f"macro-F1: {base_result['test_macro_f1']:.4f}")

    # Candidate (evaluated ONCE on holdout)
    cand_pipe, cand_result = build_candidate(X_tr, y_tr, X_te, y_te)
    print(f"Candidate — CV: {cand_result['cv_accuracy_mean']:.4f}±{cand_result['cv_accuracy_std']:.4f}, "
          f"test acc: {cand_result['test_accuracy']:.4f} "
          f"({cand_result['test_correct']}/{cand_result['test_total']}), "
          f"macro-F1: {cand_result['test_macro_f1']:.4f}")

    delta_acc = cand_result["test_accuracy"] - base_result["test_accuracy"]
    delta_f1  = cand_result["test_macro_f1"]  - base_result["test_macro_f1"]
    print(f"\nGain: {delta_acc*100:+.2f} pp accuracy, {delta_f1*100:+.2f} pp F1")

    print("\nClassification report (candidate):")
    y_pred = cand_pipe.predict(X_te)
    print(classification_report(y_te, y_pred))
    print("Confusion matrix:", cand_result["confusion_matrix"])

    # Save candidate model artifact (in experiment directory only — NOT overwriting production)
    with open(MODEL_OUT, "wb") as f:
        pickle.dump(cand_pipe, f, protocol=5)
    print(f"\nCandidate saved (experiment only, NOT production): {MODEL_OUT}")

    # Write JSON report
    report = {
        "task": "seed_viability_3class",
        "dataset": str(DATA_CSV),
        "n_rows": len(X),
        "n_features": int(X.shape[1]),
        "split": f"stratified {int((1-TEST_SIZE)*100)}/{int(TEST_SIZE*100)}, random_state={SEED}",
        "label_source": "UCI Seeds dataset (real wheat kernel measurements; NOT synthetic)",
        "leakage_check": lc,
        "baseline": base_result,
        "candidate": cand_result,
        "delta_accuracy_pp": round(delta_acc * 100, 4),
        "delta_f1_pp": round(delta_f1 * 100, 4),
        "goal_85pct_achieved": cand_result["test_accuracy"] >= 0.85,
        "production_mismatch_findings": [
            "production meta_model.pkl = RandomForestClassifier(max_depth=3, min_samples_leaf=5, n_features=6) with SYNTHETIC binary labels — not improvable without real ground-truth",
            "train_final_meta_and_compare.py trains a StackingClassifier on 3 separate datasets — this is NOT what app.py loads or calls",
            "app.py builds a 6-feature hand-crafted vector [pred_rf_val, pred_qml_val, pred_xgb_val, pred_qml_yield_val, pred_svm_val, pred_qml_seed_val] and passes it to meta_model.pkl — no correspondence to any training dataset",
            "clean_dataset() outlier clip has a sequential-index-shrinkage bug: applying mask column-by-column causes ValueError on smaller DataFrames and drops 29 rows (210→181) when it does not crash",
        ],
        "single_most_valuable_next_action": (
            "Replace the production meta_model.pkl (synthetic-label binary RF) with a real "
            "aggregated confidence score derived from validated per-leg probabilities — "
            "OR document explicitly that prob_success is a heuristic, not a measured metric. "
            "No model experiment can improve it without genuine ground-truth success labels."
        ),
        "reproducibility_command": (
            "python3 experiments/meta_model_improvement/meta_model_improvement.py"
        ),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Metrics saved: {OUT_JSON}")
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
