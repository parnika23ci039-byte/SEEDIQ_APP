"""
Phase 7: High-Accuracy Agricultural Yield Prediction
=====================================================
Benchmark: Phase 6 F3 = 742/1088 = 68.20% within ±25% (RF specialist for Chickpea)

Diagnosis findings:
  - Base rainfall features are DISTRICT-LEVEL LONG-TERM NORMALS (constant across years).
    No year-specific weather signal in base features.
  - Within-(District,Crop) year-to-year yield std = 0.35 t/ha; this weather-driven
    variation is uncaptured. For Pigeonpea/Chickpea, within-district variation
    EXCEEDS between-district variation (ratio 1.4-1.8).
  - Model compresses yield range: 75-83% of below-median yields are overpredicted.
  - Soil features are district-level constants (expected).
  - Phase 5 dynamic rainfall is SUBDIVISION-level (3 subdivisions for 19 districts),
    forward-filled for 2016-2017.

Experiments:
  A. Data quality & leakage audit (documented, no model change).
  B. Agricultural feature improvements:
     - Year-specific subdivision rainfall + anomaly vs normal
     - Crop-specific seasonal rainfall (kharif/rabi/summer)
     - Historical (district,crop) yield mean computed from training fold only
  C. Targeted model improvements:
     - HistGBR with squared_error loss (less range compression)
     - RF specialists for weak crops (Chickpea confirmed, test others)
     - Blend of abs-error + squared-error models

Rules: frozen holdout (GroupShuffleSplit rs=42, test=0.2), GroupKFold(5) CV.
No holdout data used for feature/parameter design.
"""

import json, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.model_selection import GroupShuffleSplit, GroupKFold
warnings.filterwarnings("ignore")

# ── paths ──────────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parents[2]
DATA_DIR  = Path(__file__).resolve().parent / "data"
RES_DIR   = Path(__file__).resolve().parent / "results"
RES_DIR.mkdir(exist_ok=True)

YIELD_CSV    = DATA_DIR / "enriched_yield_karnataka.csv"
RAIN_CSV     = REPO / "SeedIQ" / "data" / "rainfall in india 1901-2015.csv"
RAIN_NORMAL  = REPO / "SeedIQ" / "data" / "district wise rainfall normal.csv"
MANIFEST_JSON= Path(__file__).resolve().parent / "models" / "yield_enriched_feature_manifest.json"
FROZEN_NPZ   = RES_DIR / "phase3_senior_true_pred__yield_enriched.npz"
PHASE6_JSON  = RES_DIR / "phase6_targeted_improvement_results.json"
OUT_JSON     = RES_DIR / "phase7_high_accuracy_results.json"
OUT_DIAG     = RES_DIR / "phase7_diagnosis.json"

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
HISTGBR_SQ  = dict(loss='squared_error', max_iter=200, learning_rate=0.05,
                   max_depth=6, min_samples_leaf=4, random_state=42)
RF_PARAMS   = dict(n_estimators=300, max_depth=8, min_samples_leaf=3,
                   random_state=42, n_jobs=-1)
MIN_CROP_ROWS = 15
WEAK_CROPS = ['Soyabean','Pigeonpea','Chickpea']

# Crop season assignment (agronomic knowledge for Karnataka)
CROP_SEASON = {
    'Rice':'kharif','Maize':'kharif','Cotton':'kharif','Soyabean':'kharif',
    'Groundnut':'kharif','Pigeonpea':'kharif','Sorghum':'kharif','Pearl Millet':'kharif',
    'Finger Millet':'kharif','Sesamum':'kharif','Castor':'kharif','Kharif Sorghum':'kharif',
    'Wheat':'rabi','Chickpea':'rabi','Rapeseed and Mustard':'rabi','Linseed':'rabi',
    'Safflower':'rabi','Sunflower':'rabi','Rabi Sorghum':'rabi',
    'Sugarcane':'annual','Oilseeds':'rabi','Minor Pulses':'rabi',
}

# ── metrics ───────────────────────────────────────────────────────────────────
def within_pct(y_true, y_pred, tol=0.25):
    rel = np.abs(y_pred - y_true) / np.maximum(np.abs(y_true), 1e-12)
    return int((rel <= tol).sum()), int(len(y_true))

def metrics_dict(y_true, y_pred):
    n25, d = within_pct(y_true, y_pred, 0.25)
    n10, _ = within_pct(y_true, y_pred, 0.10)
    mae = float(np.mean(np.abs(y_pred - y_true)))
    ss_res = float(np.sum((y_true - y_pred)**2))
    ss_tot = float(np.sum((y_true - y_true.mean())**2))
    r2 = 1 - ss_res/ss_tot if ss_tot > 0 else float('nan')
    bias = float(np.mean(y_pred - y_true))
    return {"correct_25": n25, "total": d, "pct_25": round(100*n25/d, 4) if d else None,
            "correct_10": n10, "pct_10": round(100*n10/d, 4) if d else None,
            "mae": round(mae, 6), "r2": round(r2, 6), "bias": round(bias, 6)}

# ── data loading ───────────────────────────────────────────────────────────────
def load_base():
    df = pd.read_csv(YIELD_CSV)
    with open(MANIFEST_JSON) as f:
        manifest = json.load(f)
    base_features = [c for c in manifest["feature_columns"] if c in df.columns]
    return df, base_features

def add_dynamic_rainfall(df):
    """Subdivision-level year-specific rainfall (Phase 5 method)."""
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

def add_crop_seasonal_rainfall(df):
    """For each crop, pick the rainfall of its main season (kharif/rabi/summer)."""
    df = df.copy()
    df['crop_season'] = df['Crop'].map(CROP_SEASON).fillna('annual')
    season_map = {'kharif':'dyn_rain_kharif','rabi':'dyn_rain_rabi',
                  'summer':'dyn_rain_summer','annual':'dyn_rain_annual',
                  'winter':'dyn_rain_winter'}
    df['crop_season_rain'] = df.apply(
        lambda r: r[season_map.get(r['crop_season'],'dyn_rain_annual')], axis=1)
    # seasonal anomaly
    season_normal = {'kharif':'normal_kharif'}
    df['crop_season_rain_anomaly'] = np.nan
    for s, norm_col in season_normal.items():
        m = df['crop_season'] == s
        if norm_col in df.columns:
            df.loc[m, 'crop_season_rain_anomaly'] = (
                df.loc[m, 'crop_season_rain'] - df.loc[m, norm_col]
            ) / df.loc[m, norm_col].replace(0, np.nan)
    # For rabi/summer/annual, use annual normal as approximation
    other = ~df['crop_season'].isin(season_normal.keys())
    df.loc[other, 'crop_season_rain_anomaly'] = (
        df.loc[other, 'crop_season_rain'] - df.loc[other, 'normal_annual']
    ) / df.loc[other, 'normal_annual'].replace(0, np.nan)
    return df

# ── historical yield feature (training-only, leakage-free) ─────────────────────
def add_historical_yield_mean(df_tr, df_val, y_tr):
    """Compute mean yield per (District,Crop) from df_tr, map to df_val.
    Falls back to crop mean, then global mean."""
    tmp = pd.DataFrame({'District': df_tr['District'].values,
                        'Crop': df_tr['Crop'].values, 'y': y_tr})
    dc_mean = tmp.groupby(['District','Crop'])['y'].mean().to_dict()
    c_mean = tmp.groupby('Crop')['y'].mean().to_dict()
    global_mean = tmp['y'].mean()
    out = np.zeros(len(df_val))
    for i, (d, c) in enumerate(zip(df_val['District'].values, df_val['Crop'].values)):
        if (d, c) in dc_mean:
            out[i] = dc_mean[(d, c)]
        elif c in c_mean:
            out[i] = c_mean[c]
        else:
            out[i] = global_mean
    return out

# ── crop-specific fit/predict ─────────────────────────────────────────────────
def fit_predict_crop_specific(X_tr, y_tr, crops_tr, X_te, crops_te, features,
                              model_cls=HistGradientBoostingRegressor, model_params=None):
    X_tr = X_tr[features].copy()
    X_te = X_te[features].copy()
    preds = np.full(len(X_te), np.nan)
    params = model_params if model_params is not None else HISTGBR_ABS
    for crop in np.unique(crops_te):
        mask_tr = crops_tr == crop
        mask_te = crops_te == crop
        if mask_tr.sum() >= MIN_CROP_ROWS:
            m = model_cls(**params)
            m.fit(X_tr[mask_tr], y_tr[mask_tr])
            preds[mask_te] = m.predict(X_te[mask_te])
        else:
            preds[mask_te] = y_tr[mask_tr].mean() if mask_tr.sum() > 0 else y_tr.mean()
    return preds

def grouped_cv_oof(X_tr, y_tr, groups_tr, crops_tr, features,
                   model_cls=HistGradientBoostingRegressor, model_params=None,
                   extra_features_fn=None):
    """5-fold GroupKFold OOF. extra_features_fn(df_tr, df_val, y_tr) -> array for df_val."""
    oof = np.zeros(len(y_tr))
    gkf = GroupKFold(n_splits=5)
    for fold_tr_idx, fold_val_idx in gkf.split(X_tr, y_tr, groups_tr):
        X_f = X_tr.iloc[fold_tr_idx].copy()
        y_f = y_tr.iloc[fold_tr_idx]
        crops_f = crops_tr.iloc[fold_tr_idx]
        X_v = X_tr.iloc[fold_val_idx].copy()
        crops_v = crops_tr.iloc[fold_val_idx]
        if extra_features_fn is not None:
            feats_tr = extra_features_fn(X_f, X_f, y_f)
            feats_val = extra_features_fn(X_f, X_v, y_f)
            X_f = X_f.assign(_hist_yield=feats_tr)
            X_v = X_v.assign(_hist_yield=feats_val)
            feats = features + ['_hist_yield']
        else:
            feats = features
        oof[fold_val_idx] = fit_predict_crop_specific(X_f, y_f, crops_f, X_v, crops_v,
                                                     feats, model_cls, model_params)
    return oof

def full_train_predict(df_tr, y_tr, crops_tr, df_te, crops_te, features,
                       model_cls=HistGradientBoostingRegressor, model_params=None,
                       extra_features_fn=None):
    X_tr = df_tr.copy()
    X_te = df_te.copy()
    if extra_features_fn is not None:
        feats_tr = extra_features_fn(X_tr, X_tr, y_tr)
        feats_te = extra_features_fn(X_tr, X_te, y_tr)
        X_tr = X_tr.assign(_hist_yield=feats_tr)
        X_te = X_te.assign(_hist_yield=feats_te)
        feats = features + ['_hist_yield']
    else:
        feats = features
    return fit_predict_crop_specific(X_tr, y_tr, crops_tr, X_te, crops_te,
                                    feats, model_cls, model_params)

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("=== Phase 7: High-Accuracy Yield Prediction ===\n")

    # ── Load ──
    df, base_features = load_base()
    df = add_dynamic_rainfall(df)
    df = add_crop_seasonal_rainfall(df)
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
    print(f"Rainfall forward-filled rows (Year>2015): train={df_tr['rain_ffilled'].sum()}, "
          f"test={df_te['rain_ffilled'].sum()}")

    features_A = base_features  # base only (constant district rainfall)
    features_B = base_features + [f for f in DYN_FEATURES if f not in base_features]
    # Experiment B features: add crop-seasonal rain + anomaly
    features_B2 = features_B + ['crop_season_rain', 'crop_season_rain_anomaly']
    best_alpha = 0.8  # Phase 5 blend weight

    # ── Diagnosis: low-yield overprediction across ALL crops (on OOF) ──
    print("\n=== DIAGNOSIS: range compression across all crops (Candidate C OOF) ===")
    oof_A = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, features_A)
    oof_B = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, features_B)
    oof_C = best_alpha * oof_A + (1 - best_alpha) * oof_B
    diag = {}
    for crop in sorted(df_tr['Crop'].unique()):
        mask = (crops_tr == crop).values
        y_c = y_tr.values[mask]
        p_c = oof_C[mask]
        res = p_c - y_c
        rel = np.abs(res) / np.maximum(np.abs(y_c), 1e-12)
        med = np.median(y_c)
        low = y_c <= med
        diag[crop] = {
            "n": int(mask.sum()),
            "oof_pct": round(100*(rel<=0.25).sum()/mask.sum(), 2),
            "signed_bias": round(float(res.mean()), 4),
            "low_yield_overpred_pct": round(100*float((res[low]>0).mean()), 1) if low.sum()>0 else None,
            "pred_std": round(float(p_c.std()), 4),
            "true_std": round(float(y_c.std()), 4),
            "std_ratio_pred_over_true": round(float(p_c.std()/y_c.std()), 3) if y_c.std()>0 else None,
        }
    print(f"{'Crop':<22} {'n':>5} {'OOF%':>7} {'bias':>8} {'lowOP%':>8} {'pred_std':>9} {'true_std':>9} {'ratio':>6}")
    for c, d in diag.items():
        print(f"{c:<22} {d['n']:>5} {d['oof_pct']:>7.2f} {d['signed_bias']:>+8.4f} "
              f"{str(d['low_yield_overpred_pct']):>8} {d['pred_std']:>9.4f} {d['true_std']:>9.4f} "
              f"{str(d['std_ratio_pred_over_true']):>6}")
    with open(OUT_DIAG, 'w') as f:
        json.dump(diag, f, indent=2)

    # ── Benchmark: reproduce Phase 6 F3 (C + RF for Chickpea) ──
    print("\n=== Reproducing Phase 6 F3 benchmark ===")
    pred_A_hold = fit_predict_crop_specific(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te), features_A)
    pred_B_hold = fit_predict_crop_specific(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te), features_B)
    pred_C_hold = best_alpha * pred_A_hold + (1 - best_alpha) * pred_B_hold
    # Add RF for Chickpea
    pred_F3 = pred_C_hold.copy()
    for crop in ['Chickpea']:
        m = RandomForestRegressor(**RF_PARAMS)
        mask_tr = (crops_tr == crop).values
        mask_te = crops_te == crop
        m.fit(df_tr[mask_tr][features_B], y_tr[mask_tr])
        pred_F3[mask_te] = m.predict(df_te[mask_te][features_B])
    f3_metrics = metrics_dict(y_te, pred_F3)
    print(f"Phase 6 F3 holdout: {f3_metrics['correct_25']}/{f3_metrics['total']} = {f3_metrics['pct_25']}% "
          f"(reported: 742/1088 = 68.20%)")
    assert f3_metrics['correct_25'] == 742, "Phase 6 F3 reproduction mismatch!"

    # ── Experiment B: Feature improvements ──
    print("\n=== Experiment B: Agricultural feature improvements ===")
    # B1: dynamic rainfall (Phase 5) — already in Candidate C
    # B2: + crop seasonal rain + anomaly
    print("  B2: base + dyn_rain + crop_seasonal_rain + anomaly")
    oof_B2_A = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, features_B2)
    cv_B2 = metrics_dict(y_tr.values, oof_B2_A)
    print(f"    B2 CV: {cv_B2['correct_25']}/{cv_B2['total']} = {cv_B2['pct_25']}%  (C: {100*3123/4497:.2f}%)")

    # B3: + historical (district,crop) yield mean (training-only)
    print("  B3: B2 + historical (district,crop) yield mean (training-only)")
    oof_B3_A = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, features_B2,
                              extra_features_fn=add_historical_yield_mean)
    cv_B3 = metrics_dict(y_tr.values, oof_B3_A)
    print(f"    B3 CV: {cv_B3['correct_25']}/{cv_B3['total']} = {cv_B3['pct_25']}%")

    # ── Experiment C: Model improvements ──
    print("\n=== Experiment C: Targeted model improvements ===")
    # C1: HistGBR squared_error loss (less range compression)
    print("  C1: HistGBR squared_error loss (base+dyn features)")
    oof_C1 = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, features_B,
                            model_params=HISTGBR_SQ)
    cv_C1 = metrics_dict(y_tr.values, oof_C1)
    print(f"    C1 CV: {cv_C1['correct_25']}/{cv_C1['total']} = {cv_C1['pct_25']}%")

    # C2: blend abs-error (C) + squared-error (C1)
    print("  C2: blend C(abs) + C1(sq) 50/50")
    oof_C2 = 0.5 * oof_C + 0.5 * oof_C1
    cv_C2 = metrics_dict(y_tr.values, oof_C2)
    print(f"    C2 CV: {cv_C2['correct_25']}/{cv_C2['total']} = {cv_C2['pct_25']}%")

    # C3: squared-error + historical yield feature (B3 features)
    print("  C3: HistGBR squared_error + B3 features (incl historical yield)")
    oof_C3 = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, features_B2,
                            model_params=HISTGBR_SQ, extra_features_fn=add_historical_yield_mean)
    cv_C3 = metrics_dict(y_tr.values, oof_C3)
    print(f"    C3 CV: {cv_C3['correct_25']}/{cv_C3['total']} = {cv_C3['pct_25']}%")

    # C4: RF specialists for ALL weak crops (not just Chickpea), with C as base
    print("  C4: C + RF specialists for weak crops (Chickpea confirmed, test Pigeonpea/Soyabean)")
    oof_C4 = oof_C.copy()
    rf_wins = {}
    for crop in WEAK_CROPS:
        mask = (crops_tr == crop).values
        y_c = y_tr.values[mask]
        n_C, _ = within_pct(y_c, oof_C[mask])
        # RF OOF for this crop
        X_c = df_tr[mask].reset_index(drop=True)
        y_c_s = y_tr[mask].reset_index(drop=True)
        g_c = groups_tr[mask].reset_index(drop=True)
        oof_rf = np.zeros(len(y_c_s))
        n_groups = g_c.nunique()
        n_splits = min(5, n_groups)
        if n_splits >= 2:
            try:
                for ftr, fva in GroupKFold(n_splits=n_splits).split(X_c, y_c_s, g_c):
                    m = RandomForestRegressor(**RF_PARAMS)
                    m.fit(X_c.iloc[ftr][features_B], y_c_s.iloc[ftr])
                    oof_rf[fva] = m.predict(X_c.iloc[fva][features_B])
                n_rf, _ = within_pct(y_c, oof_rf)
                if n_rf > n_C:
                    rf_wins[crop] = n_rf
                    oof_C4[mask] = oof_rf
                    print(f"    {crop}: RF {n_rf} > C {n_C} → adopt RF")
                else:
                    print(f"    {crop}: RF {n_rf} ≤ C {n_C} → keep C")
            except Exception as e:
                print(f"    {crop}: RF failed ({e}) → keep C")
        else:
            print(f"    {crop}: insufficient groups → keep C")
    cv_C4 = metrics_dict(y_tr.values, oof_C4)
    print(f"    C4 CV: {cv_C4['correct_25']}/{cv_C4['total']} = {cv_C4['pct_25']}%")

    # ── CV summary & selection ──
    cv_scores = {
        'C(Phase5)': 3123/4497,
        'F3(Phase6)': 3127/4497,  # RF for Chickpea only
        'B2': cv_B2['correct_25']/cv_B2['total'],
        'B3': cv_B3['correct_25']/cv_B3['total'],
        'C1(sq_loss)': cv_C1['correct_25']/cv_C1['total'],
        'C2(blend)': cv_C2['correct_25']/cv_C2['total'],
        'C3(sq+B3)': cv_C3['correct_25']/cv_C3['total'],
        'C4(RF_weak)': cv_C4['correct_25']/cv_C4['total'],
    }
    print("\n--- CV Summary ---")
    for k, v in sorted(cv_scores.items(), key=lambda x: -x[1]):
        print(f"  {k:14s}: {100*v:.4f}%")
    best_cv = max(cv_scores, key=cv_scores.get)
    print(f"\nCV winner: {best_cv}")

    # ── Holdout evaluation for top candidates ──
    print("\n=== Holdout evaluation (top candidates only) ===")
    holdout = {}
    holdout['F3(Phase6)'] = f3_metrics

    # B3: features B2 + historical yield
    pred_B3 = full_train_predict(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te),
                                 features_B2, extra_features_fn=add_historical_yield_mean)
    holdout['B3'] = metrics_dict(y_te, pred_B3)

    # C1: squared error
    pred_C1 = full_train_predict(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te),
                                 features_B, model_params=HISTGBR_SQ)
    holdout['C1(sq_loss)'] = metrics_dict(y_te, pred_C1)

    # C3: squared error + B3 features
    pred_C3 = full_train_predict(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te),
                                 features_B2, model_params=HISTGBR_SQ,
                                 extra_features_fn=add_historical_yield_mean)
    holdout['C3(sq+B3)'] = metrics_dict(y_te, pred_C3)

    # C4: RF specialists for weak crops
    pred_C4 = pred_C_hold.copy()
    for crop in (['Chickpea'] + [c for c in WEAK_CROPS if c in rf_wins]):
        m = RandomForestRegressor(**RF_PARAMS)
        mask_tr = (crops_tr == crop).values
        mask_te = crops_te == crop
        m.fit(df_tr[mask_tr][features_B], y_tr[mask_tr])
        pred_C4[mask_te] = m.predict(df_te[mask_te][features_B])
    holdout['C4(RF_weak)'] = metrics_dict(y_te, pred_C4)

    for k, v in holdout.items():
        flag = " ← best CV" if k == best_cv else ""
        print(f"  {k:14s}: {v['correct_25']}/{v['total']} = {v['pct_25']:.4f}%  "
              f"MAE={v['mae']:.4f}  R²={v['r2']:.4f}  bias={v['bias']:+.4f}  "
              f"±10%={v['pct_10']:.2f}%{flag}")

    # Per-crop for best holdout candidate
    best_hold = max(holdout, key=lambda k: holdout[k]['pct_25'])
    preds_map = {'F3(Phase6)': pred_F3, 'B3': pred_B3, 'C1(sq_loss)': pred_C1,
                 'C3(sq+B3)': pred_C3, 'C4(RF_weak)': pred_C4}
    per_crop = {}
    for cand in ['F3(Phase6)', best_hold]:
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
        "holdout_best": best_hold,
        "rf_winners_weak_crops": rf_wins,
        "per_crop": per_crop,
        "rainfall_forward_filled": {
            "train": int(df_tr['rain_ffilled'].sum()),
            "test": int(df_te['rain_ffilled'].sum()),
        },
        "pp_gain_vs_phase6": {
            k: round(holdout[k]['pct_25'] - f3_metrics['pct_25'], 4)
            for k in holdout if k != 'F3(Phase6)'
        },
    }
    with open(OUT_JSON, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nResults saved: {OUT_JSON}")
    print("=== Phase 7 complete ===")

if __name__ == "__main__":
    main()
