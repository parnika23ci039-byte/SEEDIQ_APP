#!/usr/bin/env python3
"""
SeedIQ - Final 5-Model Comparative Evaluation & Stacking Meta Model
===================================================================
Compares ONLY:
  1. Random Forest (RF)
  2. XGBoost
  3. SVM (SVC for classification / SVR for regression)
  4. Quantum ML (Simulated Quantum)
  5. Meta Model (SeedIQ Final Hybrid Stacking Model)

Across:
  - Crop Recommendation (Classification)
  - Yield Prediction (Regression)
  - Seed Viability (Classification)

Strict Scientific Standards:
  - Zero Data Leakage: Preprocessor fitted ONLY on training split
  - Stacking meta-learner trained ONLY on out-of-fold training predictions (cv=5)
  - Independent untouched final test split (20%)
  - Mathematically valid metric reporting (N/A for non-applicable metrics)
  - Full output exports: TXT, CSV, JSON, HTML, SQLite
"""

import os
import sys
import json
import pickle
import sqlite3
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split, StratifiedKFold, KFold, cross_val_score
from sklearn.preprocessing import StandardScaler, OneHotEncoder, LabelEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import (
    RandomForestClassifier, RandomForestRegressor,
    StackingClassifier, StackingRegressor
)
from sklearn.svm import SVC, SVR
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score, f1_score, precision_score, recall_score,
    r2_score, mean_absolute_error, mean_squared_error
)

# Optional XGBoost
try:
    from xgboost import XGBClassifier, XGBRegressor
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

# Quantum ML
try:
    from qml_model import SimulatedQuantumClassifier, SimulatedQuantumRegressor
    QML_AVAILABLE = True
except ImportError:
    QML_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "models")
OUTPUT_DIR = os.path.join(BASE_DIR, "reports", "final_model_comparison")
DB_PATH = os.path.join(BASE_DIR, "seediq.db")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

DEFAULT_SEED = 42
TEST_SPLIT = 0.20
CV_FOLDS = 5

def clean_dataset(df, task, target_col):
    df = df.drop_duplicates().dropna(subset=[target_col])
    if task == "regression":
        df[target_col] = pd.to_numeric(df[target_col], errors="coerce")
        df = df.dropna(subset=[target_col])
    
    num_cols = df.select_dtypes(include=np.number).columns.tolist()
    if target_col in num_cols:
        num_cols.remove(target_col)
        
    for col in num_cols:
        q1, q3 = df[col].quantile(0.01), df[col].quantile(0.99)
        df = df[(df[col] >= q1) & (df[col] <= q3)]
        
    df = df.dropna()
    return df

def build_preprocessor(X):
    num_cols = X.select_dtypes(include=np.number).columns.tolist()
    cat_cols = X.select_dtypes(exclude=np.number).columns.tolist()
    transformers = []
    if num_cols:
        transformers.append(("num", StandardScaler(), num_cols))
    if cat_cols:
        transformers.append(("cat", OneHotEncoder(handle_unknown='ignore', sparse_output=False), cat_cols))
    return ColumnTransformer(transformers=transformers, remainder="passthrough")

def compute_classification_mse(y_true_indices, probas, n_classes):
    """
    Multi-class Brier score / probability Mean Squared Error:
    MSE = (1/N) * sum_i sum_c (y_ic - p_ic)^2
    """
    n_samples = len(y_true_indices)
    one_hot = np.zeros((n_samples, n_classes))
    for i, idx in enumerate(y_true_indices):
        one_hot[i, idx] = 1.0
    mse = float(np.mean(np.sum((one_hot - probas) ** 2, axis=1)))
    rmse = float(np.sqrt(mse))
    return mse, rmse

def evaluate_models():
    datasets = {
        "crop": {
            "name": "Crop Recommendation",
            "file": os.path.join(DATA_DIR, "Crop_recommendation.csv"),
            "target": "label",
            "task": "classification"
        },
        "yield": {
            "name": "Yield Prediction",
            "file": os.path.join(DATA_DIR, "Crop Yiled with Soil and Weather.csv"),
            "target": "yeild",
            "task": "regression"
        },
        "seed": {
            "name": "Seed Viability",
            "file": os.path.join(DATA_DIR, "Seed_Data.csv"),
            "target": "target",
            "task": "classification"
        }
    }

    all_results = []
    dataset_summaries = {}

    for ds_key, ds_info in datasets.items():
        print(f"\nEvaluating 5 Models for: {ds_info['name']} ({ds_info['task'].upper()})...")
        df_raw = pd.read_csv(ds_info["file"])
        df = clean_dataset(df_raw, ds_info["task"], ds_info["target"])
        
        X = df.drop(columns=[ds_info["target"]])
        y = df[ds_info["target"]]
        is_cls = (ds_info["task"] == "classification")
        
        label_enc = None
        n_classes = None
        if is_cls:
            label_enc = LabelEncoder()
            y = label_enc.fit_transform(y)
            n_classes = len(np.unique(y))
            
        strat = y if is_cls else None
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=TEST_SPLIT, random_state=DEFAULT_SEED, stratify=strat)
        preprocessor = build_preprocessor(X_tr)
        
        cv_method = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=DEFAULT_SEED) if is_cls else KFold(n_splits=CV_FOLDS, shuffle=True, random_state=DEFAULT_SEED)
        scoring = "f1_macro" if is_cls else "r2"

        # Define 4 base models with validated optimal parameters
        if ds_key == "crop":
            rf = RandomForestClassifier(n_estimators=100, random_state=DEFAULT_SEED, n_jobs=-1)
            xgb = XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.1, random_state=DEFAULT_SEED, eval_metric="mlogloss", verbosity=0)
            svm = SVC(C=10.0, kernel="linear", probability=True, random_state=DEFAULT_SEED)
            qml = SimulatedQuantumClassifier(n_components=12, alpha=0.001)
            meta_estimator = LogisticRegression(C=1.0, max_iter=1000, random_state=DEFAULT_SEED)
        elif ds_key == "yield":
            rf = RandomForestRegressor(n_estimators=200, random_state=DEFAULT_SEED, n_jobs=-1)
            xgb = XGBRegressor(n_estimators=150, max_depth=3, random_state=DEFAULT_SEED, verbosity=0)
            svm = SVR(C=10.0, kernel="rbf")
            qml = SimulatedQuantumRegressor(n_components=12, alpha=0.01)
            meta_estimator = Ridge(alpha=10.0, random_state=DEFAULT_SEED)
        else: # seed
            rf = RandomForestClassifier(n_estimators=50, random_state=DEFAULT_SEED, n_jobs=-1)
            xgb = XGBClassifier(n_estimators=50, max_depth=3, random_state=DEFAULT_SEED, eval_metric="mlogloss", verbosity=0)
            svm = SVC(C=10.0, kernel="linear", probability=True, random_state=DEFAULT_SEED)
            qml = SimulatedQuantumClassifier(n_components=12, alpha=0.001)
            meta_estimator = LogisticRegression(C=1.0, max_iter=1000, random_state=DEFAULT_SEED)

        base_models = [
            ("Random Forest", rf),
            ("XGBoost", xgb),
            ("SVM", svm),
            ("Quantum ML (Simulated Quantum)", qml)
        ]

        # 1. Evaluate 4 Base Models
        ds_model_results = {}
        for m_name, est in base_models:
            pipe = Pipeline([("preprocessor", preprocessor), ("estimator", est)])
            cv_scores = cross_val_score(pipe, X_tr, y_tr, cv=cv_method, scoring=scoring, n_jobs=-1)
            pipe.fit(X_tr, y_tr)
            
            y_te_pred = pipe.predict(X_te)
            y_tr_pred = pipe.predict(X_tr)
            
            if is_cls:
                acc = float(accuracy_score(y_te, y_te_pred))
                f1 = float(f1_score(y_te, y_te_pred, average="macro", zero_division=0))
                tr_f1 = float(f1_score(y_tr, y_tr_pred, average="macro", zero_division=0))
                # Compute probability MSE/RMSE
                if hasattr(pipe, "predict_proba"):
                    probas = pipe.predict_proba(X_te)
                    mse, rmse = compute_classification_mse(y_te, probas, n_classes)
                else:
                    mse, rmse = float(mean_squared_error(y_te, y_te_pred)), float(np.sqrt(mean_squared_error(y_te, y_te_pred)))
                r2 = "N/A"
            else:
                acc = "N/A"
                f1 = "N/A"
                r2 = float(r2_score(y_te, y_te_pred))
                tr_f1 = float(r2_score(y_tr, y_tr_pred))
                mse = float(mean_squared_error(y_te, y_te_pred))
                rmse = float(np.sqrt(mse))
                
            gap = (tr_f1 - (f1 if is_cls else r2))
            
            ds_model_results[m_name] = {
                "dataset": ds_info["name"],
                "task": ds_info["task"].capitalize(),
                "model": m_name,
                "pipeline": pipe,
                "cv_mean": float(np.mean(cv_scores)),
                "cv_std": float(np.std(cv_scores)),
                "accuracy": acc,
                "f1": f1,
                "mse": mse,
                "rmse": rmse,
                "r2": r2,
                "train_score": tr_f1,
                "gap": gap
            }

        # 2. Build & Evaluate Stacking Meta Model
        print(f"  Training SeedIQ Meta Model (Hybrid Stacking) on {ds_info['name']}...")
        named_estimators = [
            ("rf", rf),
            ("xgb", xgb),
            ("svm", svm),
            ("qml", qml)
        ]
        
        if is_cls:
            stacking_est = StackingClassifier(
                estimators=named_estimators,
                final_estimator=meta_estimator,
                cv=5,
                n_jobs=-1,
                passthrough=False
            )
        else:
            stacking_est = StackingRegressor(
                estimators=named_estimators,
                final_estimator=meta_estimator,
                cv=5,
                n_jobs=-1,
                passthrough=False
            )
            
        meta_pipe = Pipeline([("preprocessor", preprocessor), ("meta_stacking", stacking_est)])
        meta_cv_scores = cross_val_score(meta_pipe, X_tr, y_tr, cv=cv_method, scoring=scoring, n_jobs=-1)
        meta_pipe.fit(X_tr, y_tr)
        
        y_te_meta = meta_pipe.predict(X_te)
        y_tr_meta = meta_pipe.predict(X_tr)
        
        if is_cls:
            m_acc = float(accuracy_score(y_te, y_te_meta))
            m_f1 = float(f1_score(y_te, y_te_meta, average="macro", zero_division=0))
            m_tr = float(f1_score(y_tr, y_tr_meta, average="macro", zero_division=0))
            if hasattr(meta_pipe, "predict_proba"):
                m_probas = meta_pipe.predict_proba(X_te)
                m_mse, m_rmse = compute_classification_mse(y_te, m_probas, n_classes)
            else:
                m_mse, m_rmse = float(mean_squared_error(y_te, y_te_meta)), float(np.sqrt(mean_squared_error(y_te, y_te_meta)))
            m_r2 = "N/A"
        else:
            m_acc = "N/A"
            m_f1 = "N/A"
            m_r2 = float(r2_score(y_te, y_te_meta))
            m_tr = float(r2_score(y_tr, y_tr_meta))
            m_mse = float(mean_squared_error(y_te, y_te_meta))
            m_rmse = float(np.sqrt(m_mse))
            
        m_gap = (m_tr - (m_f1 if is_cls else m_r2))
        
        meta_name = "SeedIQ Meta Model (Final Hybrid Model)"
        ds_model_results[meta_name] = {
            "dataset": ds_info["name"],
            "task": ds_info["task"].capitalize(),
            "model": meta_name,
            "pipeline": meta_pipe,
            "cv_mean": float(np.mean(meta_cv_scores)),
            "cv_std": float(np.std(meta_cv_scores)),
            "accuracy": m_acc,
            "f1": m_f1,
            "mse": m_mse,
            "rmse": m_rmse,
            "r2": m_r2,
            "train_score": m_tr,
            "gap": m_gap
        }

        # Save meta model artifact
        ds_save_dir = os.path.join(MODEL_DIR, ds_key, "meta_model")
        os.makedirs(ds_save_dir, exist_ok=True)
        with open(os.path.join(ds_save_dir, "model.pkl"), "wb") as f:
            pickle.dump(meta_pipe, f)
        if ds_key == "seed": # Also save global meta_model.pkl
            with open(os.path.join(MODEL_DIR, "meta_model.pkl"), "wb") as f:
                pickle.dump(meta_pipe, f)

        dataset_summaries[ds_key] = ds_model_results
        for res in ds_model_results.values():
            # Drop pipeline object from serialized results
            entry = {k: v for k, v in res.items() if k != "pipeline"}
            all_results.append(entry)

    # 3. Calculate Overall Scores Across All 3 Tasks
    # Scientific Composite Score:
    # Mean of Primary Metrics: (F1_crop + R2_yield + F1_seed) / 3
    # Both F1 and R2 have theoretical max 1.0.
    composite_scores = {}
    model_keys = [
        "Random Forest",
        "XGBoost",
        "SVM",
        "Quantum ML (Simulated Quantum)",
        "SeedIQ Meta Model (Final Hybrid Model)"
    ]

    for m in model_keys:
        crop_score = dataset_summaries["crop"][m]["f1"]
        yield_score = dataset_summaries["yield"][m]["r2"]
        seed_score = dataset_summaries["seed"][m]["f1"]
        comp = (crop_score + yield_score + seed_score) / 3.0
        composite_scores[m] = {
            "crop_f1": crop_score,
            "yield_r2": yield_score,
            "seed_f1": seed_score,
            "composite": comp
        }

    # 4. Save Artifacts (TXT, CSV, JSON, HTML)
    # JSON
    with open(os.path.join(OUTPUT_DIR, "final_model_comparison.json"), "w") as f:
        json.dump({
            "individual_evaluations": all_results,
            "composite_scores": composite_scores,
            "formula": "Composite Score = (F1_crop + R2_yield + F1_seed) / 3"
        }, f, indent=4)

    # CSV
    df_out = pd.DataFrame(all_results)
    df_out.to_csv(os.path.join(OUTPUT_DIR, "final_model_comparison.csv"), index=False)

    # TXT Report
    txt_report_path = os.path.join(OUTPUT_DIR, "final_model_comparison_report.txt")
    with open(txt_report_path, "w", encoding="utf-8") as f:
        f.write("======================================================================\n")
        f.write("SEEDIQ FINAL 5-MODEL BENCHMARK & META MODEL REPORT\n")
        f.write("======================================================================\n\n")
        f.write("1. EXECUTIVE SUMMARY\n")
        f.write("--------------------\n")
        f.write("This report presents the rigorous evaluation of the 5 designated models:\n")
        f.write("Random Forest, XGBoost, SVM, Simulated Quantum ML, and the Stacking Meta Model\n")
        f.write("across Crop Recommendation, Yield Prediction, and Seed Viability.\n\n")
        
        f.write("2. COMPOSITE OVERALL SCORES ACROSS ALL DATASETS\n")
        f.write("Formula: Composite Score = (Crop Macro-F1 + Yield R2 + Seed Macro-F1) / 3\n")
        f.write("----------------------------------------------------------------------\n")
        for m in model_keys:
            cs = composite_scores[m]
            f.write(f"{m:40} : Overall = {cs['composite']:.4f} [Crop F1={cs['crop_f1']:.4f}, Yield R2={cs['yield_r2']:.4f}, Seed F1={cs['seed_f1']:.4f}]\n")
        f.write("\n")

        f.write("3. DETAILED RESULTS PER DATASET\n")
        f.write("----------------------------------------------------------------------\n")
        for ds_key, ds_info in datasets.items():
            f.write(f"\n[{ds_info['name'].upper()} - {ds_info['task'].upper()}]\n")
            f.write(f"{'Model':40} | {'CV Mean':8} | {'Test Acc':8} | {'Test F1':8} | {'MSE':8} | {'RMSE':8} | {'R2':8} | {'Gap':8}\n")
            f.write("-" * 110 + "\n")
            for m in model_keys:
                r = dataset_summaries[ds_key][m]
                acc_s = f"{r['accuracy']:.4f}" if isinstance(r['accuracy'], float) else r['accuracy']
                f1_s = f"{r['f1']:.4f}" if isinstance(r['f1'], float) else r['f1']
                r2_s = f"{r['r2']:.4f}" if isinstance(r['r2'], float) else r['r2']
                f.write(f"{r['model']:40} | {r['cv_mean']:.4f}   | {acc_s:8} | {f1_s:8} | {r['mse']:.4f}   | {r['rmse']:.4f}   | {r2_s:8} | {r['gap']:.4f}\n")
        f.write("\n")

        f.write("4. FINAL WINNERS & CATEGORY CHAMPIONS\n")
        f.write("----------------------------------------------------------------------\n")
        # Identify winners
        best_classical = max(["Random Forest", "XGBoost", "SVM"], key=lambda m: composite_scores[m]["composite"])
        best_quantum = "Quantum ML (Simulated Quantum)"
        best_hybrid = "SeedIQ Meta Model (Final Hybrid Model)"
        final_winner = max(model_keys, key=lambda m: composite_scores[m]["composite"])
        
        f.write(f"BEST CLASSICAL MODEL:    {best_classical} (Composite: {composite_scores[best_classical]['composite']:.4f})\n")
        f.write(f"BEST QUANTUM MODEL:      {best_quantum} (Composite: {composite_scores[best_quantum]['composite']:.4f})\n")
        f.write(f"BEST FINAL HYBRID MODEL: {best_hybrid} (Composite: {composite_scores[best_hybrid]['composite']:.4f})\n")
        f.write(f"OVERALL SYSTEM WINNER:   {final_winner} (Composite: {composite_scores[final_winner]['composite']:.4f})\n\n")

    # HTML Report
    html_path = os.path.join(OUTPUT_DIR, "final_model_comparison.html")
    html = []
    html.append("<!DOCTYPE html><html><head><meta charset='utf-8'><title>SeedIQ Final 5-Model Performance Report</title>")
    html.append("<style>")
    html.append("""
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 35px; background: #0f172a; color: #f8fafc; }
        h1, h2, h3 { color: #38bdf8; }
        .card { background: #1e293b; border-radius: 8px; padding: 22px; margin-bottom: 25px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); }
        table { border-collapse: collapse; width: 100%; margin-top: 15px; font-size: 13px; }
        th, td { border: 1px solid #334155; padding: 10px 12px; text-align: left; }
        th { background: #0f172a; color: #94a3b8; }
        tr:nth-child(even) { background: #1e293b; }
        tr:hover { background: #334155; }
        .winner-tag { background: #065f46; color: #34d399; font-weight: bold; padding: 3px 8px; border-radius: 4px; }
        .highlight { color: #38bdf8; font-weight: bold; }
        .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px; }
        .stat-box { background: #0f172a; border-radius: 6px; padding: 16px; border-left: 4px solid #38bdf8; }
        .stat-val { font-size: 24px; font-weight: bold; color: #f8fafc; margin-top: 5px; }
        .stat-lbl { font-size: 12px; color: #94a3b8; text-transform: uppercase; }
    """)
    html.append("</style></head><body>")
    html.append("<h1>SeedIQ Final Model Performance Report</h1>")
    html.append("<p style='color: #94a3b8;'>Rigorous 5-Model Evaluation: Random Forest, XGBoost, SVM, Simulated Quantum ML, and the Stacking Meta Model.</p>")

    # Master Table
    html.append("<div class='card'><h2>1. Master 5-Model Comparative Table</h2>")
    html.append("<p>Composite Overall Score = <code>(Crop Macro-F1 + Yield R² + Seed Macro-F1) / 3</code></p>")
    html.append("<table><tr><th>Model</th><th>Crop F1 (Cls)</th><th>Yield R² (Reg)</th><th>Seed F1 (Cls)</th><th>Composite Overall Score</th><th>Distinction</th></tr>")
    for m in model_keys:
        cs = composite_scores[m]
        is_w = (m == final_winner)
        w_badge = "<span class='winner-tag'>WINNER</span>" if is_w else ""
        html.append(f"<tr><td><strong>{m}</strong> {w_badge}</td><td>{cs['crop_f1']:.4f}</td><td>{cs['yield_r2']:.4f}</td><td>{cs['seed_f1']:.4f}</td><td class='highlight'>{cs['composite']:.4f}</td><td>{'Classical Ensemble' if 'Forest' in m or 'XGB' in m else ('Classical Kernel' if 'SVM' in m else ('Quantum Emulation' if 'Quantum' in m else 'Hybrid Stacking'))}</td></tr>")
    html.append("</table></div>")

    # Detailed Per-Dataset Tables
    for ds_key, ds_info in datasets.items():
        html.append(f"<div class='card'><h2>2. {ds_info['name']} Performance ({ds_info['task'].capitalize()})</h2>")
        html.append("<table><tr><th>Model</th><th>CV Mean ± Std</th><th>Accuracy</th><th>F1-Score</th><th>MSE</th><th>RMSE</th><th>R²</th><th>Generalization Gap</th></tr>")
        for m in model_keys:
            r = dataset_summaries[ds_key][m]
            acc_s = f"{r['accuracy']:.4f}" if isinstance(r['accuracy'], float) else r['accuracy']
            f1_s = f"{r['f1']:.4f}" if isinstance(r['f1'], float) else r['f1']
            r2_s = f"{r['r2']:.4f}" if isinstance(r['r2'], float) else r['r2']
            html.append(f"<tr><td><strong>{m}</strong></td><td>{r['cv_mean']:.4f} ± {r['cv_std']:.4f}</td><td>{acc_s}</td><td>{f1_s}</td><td>{r['mse']:.4f}</td><td>{r['rmse']:.4f}</td><td>{r2_s}</td><td>{r['gap']:.4f}</td></tr>")
        html.append("</table></div>")

    # Champions
    html.append("<div class='card'><h2>3. Final Benchmark Champions</h2><div class='stat-grid'>")
    html.append(f"<div class='stat-box'><div class='stat-lbl'>Best Classical Model</div><div class='stat-val'>{best_classical}</div><div style='color:#38bdf8; font-size:12px; margin-top:4px;'>Composite: {composite_scores[best_classical]['composite']:.4f}</div></div>")
    html.append(f"<div class='stat-box'><div class='stat-lbl'>Best Quantum Model</div><div class='stat-val'>Simulated QML</div><div style='color:#38bdf8; font-size:12px; margin-top:4px;'>Composite: {composite_scores[best_quantum]['composite']:.4f}</div></div>")
    html.append(f"<div class='stat-box'><div class='stat-lbl'>Best Final Hybrid Model</div><div class='stat-val'>SeedIQ Meta Model</div><div style='color:#38bdf8; font-size:12px; margin-top:4px;'>Composite: {composite_scores[best_hybrid]['composite']:.4f}</div></div>")
    html.append(f"<div class='stat-box'><div class='stat-lbl'>Overall System Winner</div><div class='stat-val' style='color:#34d399;'>{final_winner}</div><div style='color:#34d399; font-size:12px; margin-top:4px;'>Score: {composite_scores[final_winner]['composite']:.4f}</div></div>")
    html.append("</div></div>")

    html.append("</body></html>")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html))

    # 5. Print Simple Terminal Output as requested
    print("\n" + "="*60)
    print("SEEDIQ FINAL MODEL PERFORMANCE")
    print("="*60)
    
    # We display the consolidated metrics for each model
    # For models on each task:
    for m in model_keys:
        short_name = m.replace(" (Simulated Quantum)", "").replace(" (Final Hybrid Model)", "").replace("SeedIQ ", "")
        print(f"\n{short_name}:")
        # Accuracy: Crop / Seed / Yield
        c_acc = dataset_summaries["crop"][m]["accuracy"]
        s_acc = dataset_summaries["seed"][m]["accuracy"]
        y_acc = dataset_summaries["yield"][m]["accuracy"]
        print(f"Accuracy: Crop={c_acc:.4f} | Seed={s_acc:.4f} | Yield={y_acc}")
        
        c_f1 = dataset_summaries["crop"][m]["f1"]
        s_f1 = dataset_summaries["seed"][m]["f1"]
        y_f1 = dataset_summaries["yield"][m]["f1"]
        print(f"F1:       Crop={c_f1:.4f} | Seed={s_f1:.4f} | Yield={y_f1}")
        
        c_mse = dataset_summaries["crop"][m]["mse"]
        s_mse = dataset_summaries["seed"][m]["mse"]
        y_mse = dataset_summaries["yield"][m]["mse"]
        print(f"MSE:      Crop={c_mse:.4f} | Seed={s_mse:.4f} | Yield={y_mse:.4f}")
        
        c_rmse = dataset_summaries["crop"][m]["rmse"]
        s_rmse = dataset_summaries["seed"][m]["rmse"]
        y_rmse = dataset_summaries["yield"][m]["rmse"]
        print(f"RMSE:     Crop={c_rmse:.4f} | Seed={s_rmse:.4f} | Yield={y_rmse:.4f}")
        
        c_r2 = dataset_summaries["crop"][m]["r2"]
        s_r2 = dataset_summaries["seed"][m]["r2"]
        y_r2 = dataset_summaries["yield"][m]["r2"]
        print(f"R²:       Crop={c_r2} | Seed={s_r2} | Yield={y_r2:.4f}")
        print(f"Overall Composite Score: {composite_scores[m]['composite']:.4f}")

    print("\n" + "="*60)
    print(f"FINAL WINNER: {final_winner} (Composite Score: {composite_scores[final_winner]['composite']:.4f})")
    print(f"BEST CLASSICAL MODEL:    {best_classical} (Composite Score: {composite_scores[best_classical]['composite']:.4f})")
    print(f"BEST QUANTUM MODEL:      {best_quantum} (Composite Score: {composite_scores[best_quantum]['composite']:.4f})")
    print(f"BEST FINAL HYBRID MODEL: {best_hybrid} (Composite Score: {composite_scores[best_hybrid]['composite']:.4f})")
    print("="*60 + "\n")

if __name__ == "__main__":
    evaluate_models()
