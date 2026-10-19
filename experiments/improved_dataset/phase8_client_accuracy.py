"""
Phase 8: Client Accuracy Improvement — RF, SVM, Hybrid Meta-Model
==================================================================
Benchmark: Phase 6 F3 = 742/1088 = 68.20% within ±25% (HistGBR C + RF for Chickpea)

XGBoost unavailable in this environment (libomp missing, sandbox blocks install).
Using sklearn HistGradientBoostingRegressor as GBDT equivalent.

Three new experiments (leakage-safe, GroupKFold(5) CV on train groups only):
  Exp 1: SVR crop-specific with StandardScaler (RBF kernel)
  Exp 2: Stacking meta-model — OOF preds from HistGBR + RF + SVR -> Ridge meta-learner
  Exp 3: Per-crop best-model selection (best of HistGBR / RF / SVR by CV per crop)

Validation: frozen holdout (GroupShuffleSplit rs=42, test=0.2), GroupKFold(5) CV.
No holdout data used for feature/parameter design or meta-model training.
"""

import json, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.svm import SVR
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.model_selection import GroupShuffleSplit, GroupKFold
warnings.filterwarnings("ignore")

# ── paths ──────────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parents[2]
DATA_DIR  = Path(__file__).resolve().parent / "data"
RES_DIR   = Path(__file__).resolve().parent / "results"
RES_DIR.mkdir(exist_ok=True)

YIELD_CSV    = DATA_DIR / "enriched_yield_karnataka.csv"
RAIN_CSV     = REPO / "SeedIQ" / "data" / "rainfall in india 1901-2015.csv"
MANIFEST_JSON= Path(__file__).resolve().parent / "models" / "yield_enriched_feature_manifest.json"
FROZEN_NPZ   = RES_DIR / "phase3_senior_true_pred__yield_enriched.npz"
OUT_JSON     = RES_DIR / "phase8_client_accuracy_results.json"

# ── district → subdivision mapping (Phase 5) ──────────────────────────────────
DISTRICT_TO_SUBDIVISION = {
    'Dakshina Kannada': 'COASTAL KARNATAKA', 'Uttara Kannada': 'COASTAL KARNATAKA',
    'Ballari': 'NORTH INTERIOR KARNATAKA', 'Belagavi': 'NORTH INTERIOR KARNATAKA',
    'Bidar': 'NORTH INTERIOR KARNATAKA', 'Vijayapura': 'NORTH INTERIOR KARNATAKA',
    'Dharwad': 'NORTH INTERIOR KARNATAKA', 'Kalaburagi': 'NORTH INTERIOR KARNATAKA',
    'Raichur': 'NORTH INTERIOR KARNATAKA',
}
DEFAULT_SUB = 'SOUTH INTERIOR KARNATAKA'

DYN_FEATURES = ['dyn_rain_annual','dyn_rain_kharif','dyn_rain_rabi',
                'dyn_rain_winter','dyn_rain_summer',
                'dyn_rain_anomaly_pct','dyn_kharif_anomaly_pct']

HISTGBR_ABS = dict(loss='absolute_error', max_iter=200, learning_rate=0.05,
                   max_depth=6, min_samples_leaf=4, random_state=42)
RF_PARAMS   = dict(n_estimators=300, max_depth=8, min_samples_leaf=3,
                   random_state=42, n_jobs=-1)
SVR_PARAMS  = dict(kernel='rbf', C=10.0, gamma='scale', epsilon=0.1)
MIN_CROP_ROWS = 15
WEAK_CROPS = ['Soyabean','Pigeonpea','Chickpea']

# ── metrics ───────────────────────────────────────────────────────────────────
def within_pct(y_true, y_pred, tol=0.25):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    rel = np.abs(y_pred - y_true) / np.maximum(np.abs(y_true), 1e-12)
    return int((rel <= tol).sum()), int(len(y_true))

def metrics_dict(y_true, y_pred):
    n25, d = within_pct(y_true, y_pred, 0.25)
    n10, _ = within_pct(y_true, y_pred, 0.10)
    mae = float(np.mean(np.abs(y_pred - y_true)))
    mse = float(np.mean((y_true - y_pred)**2))
    rmse = float(np.sqrt(mse))
    ss_res = float(np.sum((y_true - y_pred)**2))
    ss_tot = float(np.sum((y_true - y_true.mean())**2))
    r2 = 1 - ss_res/ss_tot if ss_tot > 0 else float('nan')
    bias = float(np.mean(y_pred - y_true))
    return {"correct_25": n25, "total": d, "pct_25": round(100*n25/d, 4) if d else None,
            "correct_10": n10, "pct_10": round(100*n10/d, 4) if d else None,
            "mae": round(mae, 6), "mse": round(mse, 6), "rmse": round(rmse, 6),
            "r2": round(r2, 6), "bias": round(bias, 6)}

# ── data loading ───────────────────────────────────────────────────────────────
def load_base():
    df = pd.read_csv(YIELD_CSV)
    with open(MANIFEST_JSON) as f:
        manifest = json.load(f)
    base_features = [c for c in manifest["feature_columns"] if c in df.columns]
    return df, base_features

def add_dynamic_rainfall(df):
    rain = pd.read_csv(RAIN_CSV)
    rain.columns = [c.strip() for c in rain.columns]
    col_map = {'SUBDIVISION':'SUBDIVISION','YEAR':'YEAR','ANNUAL':'dyn_rain_annual',
               'Jun-Sep':'dyn_rain_kharif','Oct-Dec':'dyn_rain_rabi',
               'Jan-Feb':'dyn_rain_winter','Mar-May':'dyn_rain_summer'}
    rain = rain[list(col_map.keys())].rename(columns=col_map)
    rain['SUBDIVISION'] = rain['SUBDIVISION'].str.strip().str.upper()
    normals = rain.groupby('SUBDIVISION')[['dyn_rain_annual','dyn_rain_kharif']].mean()
    normals.columns = ['normal_annual','normal_kharif']
    df = df.copy()
    df['SUBDIVISION'] = df['District'].map(DISTRICT_TO_SUBDIVISION).fillna(DEFAULT_SUB).str.upper()
    max_rain_year = int(rain['YEAR'].max())
    df['_join_year'] = df['Year'].clip(upper=max_rain_year)
    df['rain_ffilled'] = (df['Year'] > max_rain_year).astype(int)
    merged = df.merge(rain, left_on=['SUBDIVISION','_join_year'],
                      right_on=['SUBDIVISION','YEAR'], how='left')
    merged = merged.merge(normals, on='SUBDIVISION', how='left')
    merged['dyn_rain_anomaly_pct'] = (merged['dyn_rain_annual'] - merged['normal_annual']) / merged['normal_annual'].replace(0, np.nan)
    merged['dyn_kharif_anomaly_pct'] = (merged['dyn_rain_kharif'] - merged['normal_kharif']) / merged['normal_kharif'].replace(0, np.nan)
    return merged

# ── crop-specific fit/predict ─────────────────────────────────────────────────
def fit_predict_crop_specific(X_tr, y_tr, crops_tr, X_te, crops_te, features,
                              model_cls=HistGradientBoostingRegressor, model_params=None,
                              scale=False):
    """Fit one model per crop. Returns predictions for X_te."""
    X_tr = X_tr[features].copy()
    X_te = X_te[features].copy()
    preds = np.full(len(X_te), np.nan)
    params = model_params if model_params is not None else HISTGBR_ABS
    for crop in np.unique(crops_te):
        mask_tr = crops_tr == crop
        mask_te = crops_te == crop
        if mask_tr.sum() >= MIN_CROP_ROWS:
            if scale:
                imputer = SimpleImputer(strategy='median')
                scaler = StandardScaler()
                Xtr_s = scaler.fit_transform(imputer.fit_transform(X_tr[mask_tr]))
                Xte_s = scaler.transform(imputer.transform(X_te[mask_te]))
            else:
                Xtr_s = X_tr[mask_tr].values
                Xte_s = X_te[mask_te].values
            m = model_cls(**params)
            m.fit(Xtr_s, y_tr[mask_tr])
            preds[mask_te] = m.predict(Xte_s)
        else:
            preds[mask_te] = y_tr[mask_tr].mean() if mask_tr.sum() > 0 else y_tr.mean()
    return preds

def grouped_cv_oof(X_tr, y_tr, groups_tr, crops_tr, features,
                   model_cls=HistGradientBoostingRegressor, model_params=None, scale=False):
    """5-fold GroupKFold OOF predictions."""
    oof = np.zeros(len(y_tr))
    gkf = GroupKFold(n_splits=5)
    for fold_tr_idx, fold_val_idx in gkf.split(X_tr, y_tr, groups_tr):
        X_f = X_tr.iloc[fold_tr_idx].copy()
        y_f = y_tr.iloc[fold_tr_idx]
        crops_f = crops_tr.iloc[fold_tr_idx]
        X_v = X_tr.iloc[fold_val_idx].copy()
        crops_v = crops_tr.iloc[fold_val_idx]
        oof[fold_val_idx] = fit_predict_crop_specific(
            X_f, y_f, crops_f, X_v, crops_v, features, model_cls, model_params, scale)
    return oof

def full_train_predict(df_tr, y_tr, crops_tr, df_te, crops_te, features,
                       model_cls=HistGradientBoostingRegressor, model_params=None, scale=False):
    return fit_predict_crop_specific(df_tr, y_tr, crops_tr, df_te, crops_te,
                                    features, model_cls, model_params, scale)

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("=== Phase 8: Client Accuracy — RF, SVM, Hybrid Meta-Model ===\n")

    # ── Load ──
    df, base_features = load_base()
    df = add_dynamic_rainfall(df)
    df['group_key'] = df['District'].astype(str) + '|' + df['Year'].astype(str)
    groups = df['group_key'].values
    y = df['yield_per_hectare'].values

    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr_idx, te_idx = next(gss.split(df, y, groups))
    df_tr, df_te = df.iloc[tr_idx].reset_index(drop=True), df.iloc[te_idx].reset_index(drop=True)
    y_tr = df_tr['yield_per_hectare']
    y_te = df_te['yield_per_hectare'].values
    groups_tr = df_tr['group_key']
    crops_tr = df_tr['Crop']
    crops_te = df_te['Crop'].values

    frozen = np.load(FROZEN_NPZ, allow_pickle=True)
    assert len(te_idx) == len(frozen['y_test_true'])
    assert np.allclose(y_te, frozen['y_test_true'], atol=1e-6)
    print(f"Holdout verified: {len(te_idx)} rows match frozen baseline ✓")
    print(f"Split: train={len(df_tr)}, test={len(df_te)}")

    features_A = base_features
    features_B = base_features + [f for f in DYN_FEATURES if f not in base_features]
    best_alpha = 0.8  # Phase 5 blend weight

    # ── Reproduce Phase 6 F3 benchmark ──
    print("\n=== Reproducing Phase 6 F3 benchmark ===")
    pred_A_hold = full_train_predict(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te), features_A)
    pred_B_hold = full_train_predict(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te), features_B)
    pred_C_hold = best_alpha * pred_A_hold + (1 - best_alpha) * pred_B_hold
    pred_F3 = pred_C_hold.copy()
    for crop in ['Chickpea']:
        m = RandomForestRegressor(**RF_PARAMS)
        mask_tr = (crops_tr == crop).values
        mask_te = crops_te == crop
        m.fit(df_tr[mask_tr][features_B], y_tr[mask_tr])
        pred_F3[mask_te] = m.predict(df_te[mask_te][features_B])
    f3_metrics = metrics_dict(y_te, pred_F3)
    print(f"Phase 6 F3: {f3_metrics['correct_25']}/{f3_metrics['total']} = {f3_metrics['pct_25']}%  "
          f"MAE={f3_metrics['mae']:.4f}  MSE={f3_metrics['mse']:.4f}  RMSE={f3_metrics['rmse']:.4f}  R²={f3_metrics['r2']:.4f}")
    assert f3_metrics['correct_25'] == 742, "F3 reproduction mismatch!"

    # OOF for Candidate C (used as base and in stacking)
    oof_A = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, features_A)
    oof_B = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, features_B)
    oof_C = best_alpha * oof_A + (1 - best_alpha) * oof_B

    # ═══════════════════════════════════════════════════════════════════════════
    # EXPERIMENT 1: SVR crop-specific (RBF, scaled features)
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n=== Experiment 1: SVR (RBF, scaled) crop-specific ===")
    print("  Computing OOF...")
    oof_svr = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, features_B,
                             model_cls=SVR, model_params=SVR_PARAMS, scale=True)
    cv_svr = metrics_dict(y_tr.values, oof_svr)
    print(f"  SVR CV: {cv_svr['correct_25']}/{cv_svr['total']} = {cv_svr['pct_25']}%  "
          f"MAE={cv_svr['mae']:.4f}  R²={cv_svr['r2']:.4f}")

    # SVR holdout
    pred_svr_hold = full_train_predict(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te),
                                       features_B, model_cls=SVR, model_params=SVR_PARAMS, scale=True)
    hold_svr = metrics_dict(y_te, pred_svr_hold)
    print(f"  SVR holdout: {hold_svr['correct_25']}/{hold_svr['total']} = {hold_svr['pct_25']}%")

    # ═══════════════════════════════════════════════════════════════════════════
    # EXPERIMENT 2: Stacking meta-model
    # Base models: HistGBR(C), RF(crop-specific), SVR
    # Meta-learner: Ridge, trained on OOF predictions (leakage-free)
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n=== Experiment 2: Stacking meta-model (HistGBR + RF + SVR -> Ridge) ===")
    # RF OOF (crop-specific)
    print("  Computing RF OOF...")
    oof_rf = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, features_B,
                            model_cls=RandomForestRegressor, model_params=RF_PARAMS)
    cv_rf = metrics_dict(y_tr.values, oof_rf)
    print(f"  RF CV: {cv_rf['correct_25']}/{cv_rf['total']} = {cv_rf['pct_25']}%")

    # Build meta-features: [oof_C, oof_rf, oof_svr]
    meta_X = np.column_stack([oof_C, oof_rf, oof_svr])
    meta_y = y_tr.values

    # Meta-model CV: nested GroupKFold to avoid leakage in meta-learner evaluation
    print("  Meta-model nested CV...")
    gkf_meta = GroupKFold(n_splits=5)
    oof_meta = np.zeros(len(meta_y))
    for ftr, fva in gkf_meta.split(meta_X, meta_y, groups_tr):
        meta = Ridge(alpha=1.0)
        meta.fit(meta_X[ftr], meta_y[ftr])
        oof_meta[fva] = meta.predict(meta_X[fva])
    cv_meta = metrics_dict(meta_y, oof_meta)
    print(f"  Stacking CV: {cv_meta['correct_25']}/{cv_meta['total']} = {cv_meta['pct_25']}%")

    # Train meta-model on full OOF, predict holdout
    meta_full = Ridge(alpha=1.0)
    meta_full.fit(meta_X, meta_y)
    # Holdout base predictions
    pred_rf_hold = full_train_predict(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te),
                                      features_B, model_cls=RandomForestRegressor, model_params=RF_PARAMS)
    meta_X_hold = np.column_stack([pred_C_hold, pred_rf_hold, pred_svr_hold])
    pred_meta_hold = meta_full.predict(meta_X_hold)
    hold_meta = metrics_dict(y_te, pred_meta_hold)
    print(f"  Stacking holdout: {hold_meta['correct_25']}/{hold_meta['total']} = {hold_meta['pct_25']}%")
    print(f"    Meta coefficients: C={meta_full.coef_[0]:.3f}, RF={meta_full.coef_[1]:.3f}, SVR={meta_full.coef_[2]:.3f}, intercept={meta_full.intercept_:.3f}")

    # ═══════════════════════════════════════════════════════════════════════════
    # EXPERIMENT 3: Per-crop best-model selection
    # For each crop, select best of {HistGBR(C), RF, SVR} by CV within-25%
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n=== Experiment 3: Per-crop best-model selection ===")
    oof_best = np.zeros(len(y_tr))
    crop_model_choice = {}
    for crop in sorted(df_tr['Crop'].unique()):
        mask = (crops_tr == crop).values
        y_c = y_tr.values[mask]
        n_c, d_c = within_pct(y_c, oof_C[mask])
        n_rf, _ = within_pct(y_c, oof_rf[mask])
        n_svr, _ = within_pct(y_c, oof_svr[mask])
        scores = {'HistGBR(C)': n_c, 'RF': n_rf, 'SVR': n_svr}
        best_model = max(scores, key=scores.get)
        crop_model_choice[crop] = best_model
        if best_model == 'HistGBR(C)':
            oof_best[mask] = oof_C[mask]
        elif best_model == 'RF':
            oof_best[mask] = oof_rf[mask]
        else:
            oof_best[mask] = oof_svr[mask]
    cv_best = metrics_dict(y_tr.values, oof_best)
    print(f"  Per-crop best CV: {cv_best['correct_25']}/{cv_best['total']} = {cv_best['pct_25']}%")
    model_counts = pd.Series(crop_model_choice).value_counts().to_dict()
    print(f"  Model selection counts: {model_counts}")

    # Holdout for per-crop best
    pred_best_hold = np.zeros(len(y_te))
    for crop in np.unique(crops_te):
        mask_te = crops_te == crop
        chosen = crop_model_choice.get(crop, 'HistGBR(C)')
        if chosen == 'RF':
            pred_best_hold[mask_te] = pred_rf_hold[mask_te]
        elif chosen == 'SVR':
            pred_best_hold[mask_te] = pred_svr_hold[mask_te]
        else:
            pred_best_hold[mask_te] = pred_C_hold[mask_te]
    hold_best = metrics_dict(y_te, pred_best_hold)
    print(f"  Per-crop best holdout: {hold_best['correct_25']}/{hold_best['total']} = {hold_best['pct_25']}%")

    # ═══════════════════════════════════════════════════════════════════════════
    # CV summary
    # ═══════════════════════════════════════════════════════════════════════════
    cv_scores = {
        'F3(Phase6)': 3127/4497,
        'SVR': cv_svr['correct_25']/cv_svr['total'],
        'RF': cv_rf['correct_25']/cv_rf['total'],
        'Stacking': cv_meta['correct_25']/cv_meta['total'],
        'Per-crop-best': cv_best['correct_25']/cv_best['total'],
    }
    print("\n--- CV Summary ---")
    for k, v in sorted(cv_scores.items(), key=lambda x: -x[1]):
        print(f"  {k:16s}: {100*v:.4f}%")
    best_cv = max(cv_scores, key=cv_scores.get)
    print(f"\nCV winner: {best_cv}")

    # ═══════════════════════════════════════════════════════════════════════════
    # Holdout evaluation
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n=== Holdout evaluation ===")
    hold_rf = metrics_dict(y_te, pred_rf_hold)
    holdout = {
        'F3(Phase6)': f3_metrics,
        'SVR': hold_svr,
        'RF': hold_rf,
        'Stacking': hold_meta,
        'Per-crop-best': hold_best,
    }
    for k, v in holdout.items():
        flag = " ← best CV" if k == best_cv else ""
        print(f"  {k:16s}: {v['correct_25']}/{v['total']} = {v['pct_25']:.4f}%  "
              f"MAE={v['mae']:.4f}  MSE={v['mse']:.4f}  RMSE={v['rmse']:.4f}  "
              f"R²={v['r2']:.4f}  ±10%={v['pct_10']:.2f}%{flag}")

    # Per-crop for top candidates
    preds_map = {'F3(Phase6)': pred_F3, 'SVR': pred_svr_hold, 'RF': pred_rf_hold,
                 'Stacking': pred_meta_hold, 'Per-crop-best': pred_best_hold}
    per_crop = {}
    for cand in ['F3(Phase6)', 'Stacking', 'Per-crop-best']:
        preds = preds_map[cand]
        per_crop[cand] = {}
        for crop in sorted(np.unique(crops_te)):
            mask = crops_te == crop
            n, d = within_pct(y_te[mask], preds[mask], 0.25)
            per_crop[cand][crop] = {"correct": n, "total": d,
                                     "pct": round(100*n/d, 2) if d else None}

    # ── Save ──
    report = {
        "benchmark_phase6_f3": f3_metrics,
        "cv_scores": {k: round(100*v, 4) for k, v in cv_scores.items()},
        "cv_winner": best_cv,
        "holdout": holdout,
        "meta_model_coefficients": {
            "HistGBR(C)": round(float(meta_full.coef_[0]), 4),
            "RF": round(float(meta_full.coef_[1]), 4),
            "SVR": round(float(meta_full.coef_[2]), 4),
            "intercept": round(float(meta_full.intercept_), 4),
        },
        "per_crop_model_choice": crop_model_choice,
        "model_selection_counts": model_counts,
        "per_crop": per_crop,
        "pp_gain_vs_phase6": {
            k: round(holdout[k]['pct_25'] - f3_metrics['pct_25'], 4)
            for k in holdout if k != 'F3(Phase6)'
        },
        "xgboost_available": False,
        "xgboost_note": "XGBoost could not be loaded (libomp OpenMP symbols missing; "
                        "sandbox blocks brew install libomp). Used HistGradientBoostingRegressor "
                        "as GBDT equivalent.",
    }
    with open(OUT_JSON, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nResults saved: {OUT_JSON}")
    print("=== Phase 8 complete ===")

if __name__ == "__main__":
    main()
