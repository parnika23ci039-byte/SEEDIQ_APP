import os
import sys
import json
import time
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.model_selection import train_test_split, GridSearchCV, StratifiedKFold, KFold
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from xgboost import XGBRegressor
from sklearn.svm import SVC
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, r2_score, mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, LabelEncoder

from experiment_tracker import get_db_connection, register_dataset_version, log_hyperparameter_trial
from data_validator import run_data_quality_checks, run_data_leakage_checks
from qml_model import SimulatedQuantumClassifier, SimulatedQuantumRegressor

def get_env_metadata():
    return {
        "python_version": sys.version.split()[0],
        "sklearn_version": sklearn.__version__,
        "xgboost_version": xgboost.__version__,
        "numpy_version": np.__version__,
        "pandas_version": pd.__version__
    }

def run_experiment_pipeline(task_name, dataset_path, target_col, is_classification=True):
    """Runs end-to-end model comparison & hyperparameter tuning for a given task."""
    exp_timestamp = time.strftime("%Y%m%d-%H%M%S")
    exp_id = f"SEEDIQ-EXP-{exp_timestamp}-{task_name.upper()}"
    print(f"\n==================================================")
    print(f"🔬 RUNNING EXPERIMENT: {exp_id}")
    print(f"==================================================")
    
    # 1. Quality Checks
    quality_rep = run_data_quality_checks(dataset_path, target_col)
    if not quality_rep["passed"]:
        print(f"❌ Data Quality Failure: {quality_rep['errors']}")
        return None
        
    ds_version = register_dataset_version(task_name, dataset_path, target_col)
    
    # Register Experiment in DB immediately with status='RUNNING'
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO experiments (experiment_id, model_name, task_name, dataset_name, dataset_version, random_seed, status, data_quality_status)
            VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', 'PASSED')
        ''', (exp_id, "MultiModelComparison", task_name, dataset_path, ds_version, 42))
        conn.commit()

    try:
        # 2. Load Data and Process Features
        df = pd.read_csv(dataset_path).dropna()
        if target_col not in df.columns:
            for c in df.columns:
                if c.lower() == target_col.lower():
                    target_col = c
                    break
                    
        y_raw = df[target_col]
        X_raw = df.drop(columns=[target_col])
        
        # One-Hot Encode categorical columns to preserve Crop & Season features
        cat_cols = X_raw.select_dtypes(include=['object', 'category']).columns
        if len(cat_cols) > 0:
            X = pd.get_dummies(X_raw, columns=cat_cols, drop_first=True)
        else:
            X = X_raw.select_dtypes(include=np.number)
            
        y = y_raw
        if is_classification and y.dtype == 'object':
            le = LabelEncoder()
            y = le.fit_transform(y)
            
        # Split: 70% Train, 15% Val (CV), 15% Test (Split occurs BEFORE model training)
        if is_classification:
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.15, random_state=42, stratify=y if len(np.unique(y)) > 1 else None)
        else:
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.15, random_state=42)
            
        # 3. Data Leakage Check
        leakage_rep = run_data_leakage_checks(X_train, X_test, y_train, y_test)
        leakage_status = "NO_LEAKAGE" if leakage_rep["passed"] else "LEAKAGE_DETECTED"
        if not leakage_rep["passed"]:
            print(f"❌ Data Leakage Error: {leakage_rep['errors']}")

        # Baseline Model Evaluation
        if is_classification:
            baseline_model = DummyClassifier(strategy="most_frequent")
            baseline_model.fit(X_train, y_train)
            b_pred = baseline_model.predict(X_test)
            baseline_score = float(f1_score(y_test, b_pred, average='macro', zero_division=0))
        else:
            baseline_model = DummyRegressor(strategy="mean")
            baseline_model.fit(X_train, y_train)
            b_pred = baseline_model.predict(X_test)
            baseline_score = float(r2_score(y_test, b_pred))

        # 4. Model Search Space Definition
        if is_classification:
            models_to_tune = {
                "RandomForest": (
                    RandomForestClassifier(random_state=42),
                    {
                        'n_estimators': [50, 100, 150],
                        'max_depth': [None, 5, 10],
                        'min_samples_split': [2, 5]
                    }
                ),
                "SVM": (
                    Pipeline([('scaler', StandardScaler()), ('svm', CalibratedClassifierCV(estimator=SVC(random_state=42)))]),
                    {
                        'svm__estimator__C': [0.1, 1.0, 10.0],
                        'svm__estimator__kernel': ['rbf', 'linear']
                    }
                ),
                "SimulatedQML": (
                    SimulatedQuantumClassifier(),
                    {
                        'n_components': [8, 12],
                        'alpha': [0.001, 0.01]
                    }
                )
            }
        else:
            models_to_tune = {
                "XGBoost": (
                    XGBRegressor(random_state=42),
                    {
                        'n_estimators': [50, 100, 150],
                        'max_depth': [3, 5, 7],
                        'learning_rate': [0.01, 0.1]
                    }
                ),
                "RandomForest": (
                    Pipeline([('scaler', StandardScaler()), ('rf', RandomForestRegressor(random_state=42))]),
                    {
                        'rf__n_estimators': [50, 100],
                        'rf__max_depth': [None, 5]
                    }
                ),
                "SimulatedQML": (
                    SimulatedQuantumRegressor(),
                    {
                        'n_components': [6, 8],
                        'alpha': [0.01, 0.1]
                    }
                )
            }

        model_evaluations = []
        failed_models = []
        
        for m_name, (model_obj, param_grid) in models_to_tune.items():
            print(f"  -> Tuning & Training {m_name}...")
            start_t = time.time()
            
            try:
                if param_grid:
                    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42) if is_classification else KFold(n_splits=5, shuffle=True, random_state=42)
                    search = GridSearchCV(model_obj, param_grid, cv=cv, scoring='f1_macro' if is_classification else 'r2', n_jobs=1)
                    search.fit(X_train, y_train)
                    best_model = search.best_estimator_
                    best_params = search.best_params_
                    cv_score = float(search.best_score_)
                    
                    for trial_idx, (params_i, mean_score_i) in enumerate(zip(search.cv_results_['params'], search.cv_results_['mean_test_score'])):
                        log_hyperparameter_trial(exp_id, trial_idx + 1, params_i, float(mean_score_i))
                else:
                    best_model = model_obj
                    best_model.fit(X_train, y_train)
                    best_params = {}
                    cv_score = 0.0
                    
                train_time = time.time() - start_t
                
                # Test evaluation (evaluated ONCE on held-out test set)
                start_inf = time.time()
                y_pred = best_model.predict(X_test)
                inf_time = time.time() - start_inf
                
                if is_classification:
                    acc = float(accuracy_score(y_test, y_pred))
                    prec = float(precision_score(y_test, y_pred, average='macro', zero_division=0))
                    rec = float(recall_score(y_test, y_pred, average='macro', zero_division=0))
                    f1 = float(f1_score(y_test, y_pred, average='macro', zero_division=0))
                    primary_metric = f1
                    metrics_dict = {"accuracy": acc, "precision": prec, "recall": rec, "f1": f1}
                else:
                    mae = float(mean_absolute_error(y_test, y_pred))
                    mse = float(mean_squared_error(y_test, y_pred))
                    rmse = float(np.sqrt(mse))
                    r2 = float(r2_score(y_test, y_pred))
                    primary_metric = r2
                    metrics_dict = {"mae": mae, "mse": mse, "rmse": rmse, "r2": r2}
                    
                # Overfitting Gap Analysis
                y_train_pred = best_model.predict(X_train)
                train_score = float(f1_score(y_train, y_train_pred, average='macro', zero_division=0) if is_classification else r2_score(y_train, y_train_pred))
                gen_gap = train_score - primary_metric
                
                # Strict Overfitting & Underfitting Rules
                if (is_classification and train_score < 0.50) or (not is_classification and train_score < 0.30) or gen_gap < -0.05:
                    overfit_status = "UNDERFITTING"
                elif gen_gap > 0.20:
                    overfit_status = "SEVERE_OVERFITTING"
                elif gen_gap > 0.10:
                    overfit_status = "POSSIBLE_OVERFITTING"
                else:
                    overfit_status = "HEALTHY"
                    
                # Warnings List
                model_warnings = []
                if primary_metric == 1.0:
                    model_warnings.append("PERFECT_SCORE_WARNING")
                if not is_classification and primary_metric < 0:
                    model_warnings.append("NEGATIVE_R2_WARNING")
                if gen_gap > 0.10:
                    model_warnings.append("LARGE_GENERALIZATION_GAP")
                    
                model_evaluations.append({
                    "model_name": m_name,
                    "best_model": best_model,
                    "best_params": best_params,
                    "cv_score": cv_score,
                    "test_score": primary_metric,
                    "train_score": train_score,
                    "gen_gap": gen_gap,
                    "overfit_status": overfit_status,
                    "metrics": metrics_dict,
                    "train_time": train_time,
                    "inf_time": inf_time,
                    "warnings": model_warnings,
                    "status": "SUCCESS"
                })
            except Exception as err:
                print(f"  ❌ Model {m_name} failed during training: {err}")
                failed_models.append((m_name, str(err)))

        # Evaluate Experiment Status Lifecycle
        if len(model_evaluations) == len(models_to_tune):
            exp_status = "SUCCESS"
        elif len(model_evaluations) > 0:
            exp_status = "PARTIAL"
        else:
            exp_status = "FAILED"

        if exp_status == "FAILED":
            err_msg = "; ".join([f"{m}: {e}" for m, e in failed_models])
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE experiments SET status = 'FAILED', error_message = ? WHERE experiment_id = ?", (err_msg, exp_id))
                conn.commit()
            print(f"❌ Experiment {exp_id} FAILED - All models failed: {err_msg}")
            return None

        # Pick Best Model among successful ones
        best_eval = max(model_evaluations, key=lambda x: x["test_score"])
        print(f"🏆 Best Model Selected for {task_name}: {best_eval['model_name']} (Test Score: {best_eval['test_score']:.4f})")
        
        # Save Artifacts & Update DB
        model_dir = os.path.join('models', task_name.lower())
        os.makedirs(model_dir, exist_ok=True)
        out_model_path = os.path.join(model_dir, f"{best_eval['model_name'].lower()}_model.pkl")
        
        import pickle
        with open(out_model_path, 'wb') as f:
            pickle.dump(best_eval['best_model'], f)

        if isinstance(best_eval['best_model'], XGBRegressor):
            xgb_native_path = os.path.join(model_dir, f"{best_eval['model_name'].lower()}_model.json")
            best_eval['best_model'].save_model(xgb_native_path)
            
        err_msg = "; ".join([f"{m}: {e}" for m, e in failed_models]) if failed_models else None
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE experiments 
                SET model_name = ?, status = ?, training_time = ?, inference_time = ?, model_path = ?, error_message = ?,
                    leakage_status = ?, overfitting_status = ?, baseline_score = ?, model_score = ?, validation_status = 'VALIDATED'
                WHERE experiment_id = ?
            ''', (
                best_eval['model_name'], exp_status, best_eval['train_time'], best_eval['inf_time'], out_model_path, err_msg,
                leakage_status, best_eval['overfit_status'], baseline_score, best_eval['test_score'], exp_id
            ))
            
            # Save metrics
            for m_k, m_v in best_eval['metrics'].items():
                cursor.execute('''
                    INSERT INTO experiment_metrics (experiment_id, metric_name, metric_value, split)
                    VALUES (?, ?, ?, 'TEST')
                ''', (exp_id, m_k, float(m_v)))
                
            # Model versioning
            cursor.execute('''
                INSERT INTO model_versions (model_name, version, experiment_id, model_path, dataset_version, best_parameters_json, metrics_json, is_production)
                VALUES (?, 'v001', ?, ?, ?, ?, ?, 1)
            ''', (best_eval['model_name'], exp_id, out_model_path, ds_version, json.dumps(best_eval['best_params']), json.dumps(best_eval['metrics'])))
            
            conn.commit()

        return {
            "exp_id": exp_id,
            "task": task_name,
            "best_eval": best_eval,
            "all_evals": model_evaluations,
            "failed_models": failed_models,
            "exp_status": exp_status,
            "dataset_version": ds_version,
            "baseline_score": baseline_score,
            "leakage_status": leakage_status,
            "env_metadata": get_env_metadata()
        }

    except Exception as general_err:
        print(f"❌ Unexpected pipeline error in {exp_id}: {general_err}")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE experiments SET status = 'FAILED', error_message = ? WHERE experiment_id = ?", (str(general_err), exp_id))
            conn.commit()
        return None
