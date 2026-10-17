# SeedIQ ML System Audit

**Project:** SeedIQ: Quantum-Enhanced Viability & Storage Intelligence  
**Date:** 2026-08-16  
**Auditor:** Senior ML Engineer & QA Lead  

---

## 1. Executive Summary

A comprehensive audit was performed across all code, datasets, models, databases, registries, and configuration files in the SeedIQ workspace (`c:\Users\SUMITH R\Desktop\SeedIQ1\SeedIQ`). 

SeedIQ is a hybrid AI + Quantum Machine Learning platform providing decision support across four agricultural domains:
1. **Crop Recommendation** (Classification)
2. **Yield Prediction** (Regression)
3. **Seed Viability / Germination Assessment** (Classification)
4. **Storage Intelligence & Optimization** (Rule/Model-Based Recommendation)

---

## 2. Inventory & File Audit

| File / Folder | Status | Purpose / Description |
| :--- | :--- | :--- |
| `app.py` | Present (1046 lines) | Flask backend REST API + Session auth + SQLite predictions logging |
| `train_all_models.py` | Present (565 lines) | Main script that generates synthetic datasets & trains models |
| `qml_model.py` | Present (130 lines) | Pennylane setup + Simulated quantum classifier/regressor fallbacks |
| `data_preprocessing.py` | Present (134 lines) | Automatic dataset type detection, routing, and column preprocessors |
| `crop_prediction_model.py` | Present (240 bytes) | Model wrapper stub pointing to `models/` |
| `yield_prediction_model.py` | Present (197 bytes) | Model wrapper stub pointing to `models/` |
| `seed_classification.py` | Present (182 bytes) | Model wrapper stub pointing to `models/` |
| `storage_recommendation.py` | Present (171 bytes) | Rule/lookup-based storage engine stub |
| `models/` | Present (14 files) | `.pkl` artifacts (rf, xgb, svm, vqc, scalers, encoders) |
| `data/` | Present (24 CSV/XLSX files) | Real & mock agricultural datasets |
| `notebooks/` | Present | Jupyter notebooks for EDA and experimental prototypes |
| `training_history.txt` | Present (33,246 bytes) | Plain text execution log of training runs |
| `training_registry.json` | Present (46,041 bytes) | JSON metadata registry storing trained model details |
| `seediq.db` | Present (32,768 bytes) | SQLite DB with `users` and `predictions` tables |
| `requirements.txt` | Present (15 lines) | Core python package dependencies |

---

## 3. Dataset Audit

The `data/` directory contains 24 files. The core datasets actively used by `train_all_models.py` and `data_preprocessing.py` are:

### 3.1 `merged_ml_dataset.csv` (Crop Recommendation)
- **Rows / Records:** 100
- **Columns:** `Nitrogen`, `Phosphorus`, `Potassium`, `Temperature`, `Humidity`, `pH`, `Rainfall`, `Crop`
- **Features (7):** N, P, K, Temperature (°C), Humidity (%), pH, Rainfall (mm)
- **Target:** `Crop` (5 classes: Rice, Wheat, Maize, Sugarcane, Cotton)
- **Missing Values:** 0
- **Duplicates:** 0

### 3.2 `crop_production_karnataka.csv` (Yield Prediction)
- **Rows / Records:** 100
- **Columns:** `Crop`, `Season`, `Area_Hectares`, `Yield_Tonnes`
- **Features (3 base + 2 engineered):** `Crop`, `Season`, `Area_Hectares`, `Area_Sq`, `Crop_Season`
- **Target:** `Yield_Tonnes` (Continuous regression target)
- **Missing Values:** 0
- **Duplicates:** 0

### 3.3 `seed_viability_data.csv` (Seed Classification / Viability)
- **Rows / Records:** 100
- **Columns:** `Moisture_Level`, `Weight_g`, `Viable`
- **Features (2):** `Moisture_Level` (%), `Weight_g` (grams)
- **Target:** `Viable` (Binary: 0 or 1)
- **Missing Values:** 0
- **Duplicates:** 0

### Additional Datasets Present:
`Crop Yiled with Soil and Weather.csv`, `Crop_recommendation.csv`, `ICRISAT-District Level Data.csv`, `Seed_Data.csv`, `Soil-Climate-data.csv`, `Test Dataset.csv`, `Train Dataset.csv`, `climate_data_karnataka.csv`, `soil_data_karnataka.csv`, `storage_recommendations.csv`.

---

## 4. Current Model Audit & Saved Artifacts

All models are saved in the `models/` directory:

| Model Artifact File | Task | Algorithm | Parameters / Config |
| :--- | :--- | :--- | :--- |
| `rf_model.pkl` | Crop Recommendation | `RandomForestClassifier` | `n_estimators=200`, `max_depth=None`, `max_features='sqrt'` |
| `xgb_model.pkl` | Yield Prediction | `XGBRegressor` | `n_estimators=200`, `max_depth=6`, `learning_rate=0.05` |
| `svm_model.pkl` | Crop / Seed Classification | `SVC` | `kernel='rbf'`, `C=1.0`, `probability=True` |
| `meta_model.pkl` | Stacking Ensemble | `LogisticRegression` / `Ridge` | Blends predictions from base models |
| `vqc_crop_model.pkl` | Crop QML | `SimulatedQuantumClassifier` | `n_components=12`, `alpha=0.001`, `epochs=100` |
| `vqc_yield_model.pkl` | Yield QML | `SimulatedQuantumRegressor` | `n_components=8`, `alpha=0.01`, `epochs=100` |
| `vqc_seed_model.pkl` | Seed QML | `SimulatedQuantumClassifier` | `n_components=12`, `alpha=0.001`, `epochs=100` |
| `crop_scaler.pkl` | Crop Preprocessor | `StandardScaler` | Fitted on 7 numeric features |
| `crop_encoder.pkl` | Crop Preprocessor | `LabelEncoder` | 5 crop classes |
| `yield_scaler.pkl` | Yield Preprocessor | `StandardScaler` | Fitted on 5 yield features |
| `yield_crop_encoder.pkl` | Yield Preprocessor | `LabelEncoder` | Crop labels |
| `yield_season_encoder.pkl`| Yield Preprocessor | `LabelEncoder` | Season labels |
| `seed_scaler.pkl` | Seed Preprocessor | `StandardScaler` | Fitted on 2 seed features |

---

## 5. Existing Preprocessing, Split & Metric Evaluation

- **Train / Test Split:** Currently fixed at 80% Train / 20% Test (`test_size=0.20`, `random_state=42`).
- **Validation:** No separate validation split or automated cross-validation in the active `train_all_models.py` training flow.
- **Metrics Reported in Logs:**
  - Crop: Accuracy Score (%)
  - Yield: R² Score
  - Seed: Accuracy Score (%)
- **Missing Metrics:** Precision, Recall, F1-score, ROC-AUC, MAE, MSE, RMSE, Overfitting Generalization Gap.

---

## 6. Quantum Machine Learning (QML) Implementation Status

- **Framework:** PennyLane device `"default.qubit"` with 2 qubits (`RY` & `RZ` rotations) if installed, with a high-dimensional simulated quantum projection fallback (`SimulatedQuantumClassifier` and `SimulatedQuantumRegressor`) using trigonometric feature maps ($\sin, \cos, \sin(2x), \cos(2x)$).
- **Execution Mode:** Simulation-based (CPU / Quantum Circuit Simulator). No physical quantum hardware execution is claimed or present.

---

## 7. Current Database Schema (`seediq.db`)

Currently contains only two tables:
1. `users` (`id`, `username`, `password`, `role`)
2. `predictions` (`id`, `user_id`, `prediction_type`, `inputs`, `results`, `timestamp`)

---

## 8. Identified Gaps & Missing Capabilities

1. **No Automated Testing:** No `tests/` directory or `pytest` suite present.
2. **No Experiment Tracking:** Experiments are currently logged to a static text file (`training_history.txt`) and a simple JSON file (`training_registry.json`). Lacks structured run IDs, hyperparameters search history, or metric tracking per run.
3. **No Automated Hyperparameter Optimization:** Hyperparameters are hardcoded in `train_all_models.py`.
4. **No Dataset Versioning or SHA-256 Hashing:** Datasets are loaded directly without tracking file changes or integrity hashes.
5. **No Data Leakage / Quality Checks:** No checks for target leakage, duplicate records across train/test splits, or data range anomalies before fitting.
6. **No Model Versioning / Lineage:** Models in `models/` are directly overwritten on re-training without version control (e.g. `v001`, `v002`).
7. **No Automated Report Generation:** No HTML/JSON evaluation reports produced after training.
