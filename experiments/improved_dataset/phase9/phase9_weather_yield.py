"""
Phase 9 — Weather-Enhanced Yield Prediction
=============================================

Baseline (Phase 6 F3, verified):
  742/1088 = 68.1985% within ±25%, MAE=0.237763, RMSE=0.404546, R²=0.958949

This script adds genuine year-specific, district-level historical weather from
Open-Meteo ERA5 reanalysis (2000–2017) and compares:

  Candidate A: F3 baseline (unchanged feature set)
  Candidate B: F3 + district-level weather features
  Candidate C: F3 + weather features + rainfall-anomaly features (within-fold)

Evaluation protocol (identical to Phase 6/8 for comparability):
  - GroupShuffleSplit(rs=42, test=0.2) on District|Year groups  → frozen holdout
  - GroupKFold(5) on training groups for OOF / CV variability
  - All preprocessing fit on training data only
  - No holdout data used for feature design or tuning

Weather features (per District-Year, derived from daily ERA5 data):
  - Seasonal rainfall totals: annual, kharif (Jun-Sep), rabi (Oct-Dec),
    summer (Mar-May), winter (Jan-Feb) — captures water availability
  - Seasonal mean temperature: annual, kharif, rabi — heat/cold stress
  - Annual max/min temperature — extreme temperature exposure
  - Rainy days (precip ≥ 2.5 mm) — rainfall distribution
  - Extreme-rain days (precip ≥ 50 mm) — flood/damage risk
  - Max daily rainfall — single-day extreme
  - Growing degree days (GDD, base 10°C) — heat accumulation for crop growth
  - Mean diurnal temperature range — temperature variability
  - Rainfall anomaly % vs district normal (within-fold) — drought/wet signal

Limitation: Open-Meteo ERA5 is reanalysis/weather-model data, not guaranteed
ground-station observations. Stated in provenance.
"""

import json, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.model_selection import GroupShuffleSplit, GroupKFold
warnings.filterwarnings("ignore")

# ── paths ──────────────────────────────────────────────────────────────────────
IMPROVED = Path(__file__).resolve().parents[1]          # .../improved_dataset
PHASE9   = Path(__file__).resolve().parent               # .../phase9
DATA_DIR = IMPROVED / "data"
RES_DIR  = PHASE9 / "results"
RES_DIR.mkdir(parents=True, exist_ok=True)

YIELD_CSV  = DATA_DIR / "enriched_yield_karnataka.csv"
RAIN_CSV   = Path("/Users/apple/SeedIQ/SeedIQ/data/rainfall in india 1901-2015.csv")
MANIFEST   = IMPROVED / "models" / "yield_enriched_feature_manifest.json"
FROZEN_NPZ = IMPROVED / "results" / "phase3_senior_true_pred__yield_enriched.npz"
WEATHER_CSV= PHASE9 / "data" / "openmeteo_daily_weather_karnataka.csv"

OUT_JSON    = RES_DIR / "phase9_weather_yield_results.json"
FEATURE_REP = RES_DIR / "phase9_feature_coverage_report.json"

# ── district → subdivision (identical to Phase 5/6/8) ─────────────────────────
DISTRICT_TO_SUBDIVISION = {
    'Dakshina Kannada': 'COASTAL KARNATAKA', 'Uttara Kannada': 'COASTAL KARNATAKA',
    'Ballari': 'NORTH INTERIOR KARNATAKA', 'Belagavi': 'NORTH INTERIOR KARNATAKA',
    'Bidar': 'NORTH INTERIOR KARNATAKA', 'Vijayapura': 'NORTH INTERIOR KARNATAKA',
    'Dharwad': 'NORTH INTERIOR KARNATAKA', 'Kalaburagi': 'NORTH INTERIOR KARNATAKA',
    'Raichur': 'NORTH INTERIOR KARNATAKA',
}
DEFAULT_SUB = 'SOUTH INTERIOR KARNATAKA'

DYN_FEATURES = ['dyn_rain_annual', 'dyn_rain_kharif', 'dyn_rain_rabi',
                'dyn_rain_winter', 'dyn_rain_summer',
                'dyn_rain_anomaly_pct', 'dyn_kharif_anomaly_pct']

HISTGBR_PARAMS = dict(loss='absolute_error', max_iter=200, learning_rate=0.05,
                      max_depth=6, min_samples_leaf=4, random_state=42)
RF_PARAMS = dict(n_estimators=300, max_depth=8, min_samples_leaf=3,
                 random_state=42, n_jobs=-1)
MIN_CROP_ROWS = 15
BLEND_ALPHA = 0.8  # Phase 5/6 blend weight

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
    mse = float(np.mean((y_true - y_pred) ** 2))
    rmse = float(np.sqrt(mse))
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float('nan')
    bias = float(np.mean(y_pred - y_true))
    return {"correct_25": n25, "total": d,
            "pct_25": round(100 * n25 / d, 4) if d else None,
            "correct_10": n10,
            "pct_10": round(100 * n10 / d, 4) if d else None,
            "mae": round(mae, 6), "mse": round(mse, 6),
            "rmse": round(rmse, 6), "r2": round(r2, 6),
            "bias": round(bias, 6)}

# ── data loading (base + dynamic rainfall, identical to Phase 6/8) ────────────
def load_base():
    df = pd.read_csv(YIELD_CSV)
    with open(MANIFEST) as f:
        manifest = json.load(f)
    base_features = [c for c in manifest["feature_columns"] if c in df.columns]
    return df, base_features

def add_dynamic_rainfall(df):
    rain = pd.read_csv(RAIN_CSV)
    rain.columns = [c.strip() for c in rain.columns]
    col_map = {'SUBDIVISION': 'SUBDIVISION', 'YEAR': 'YEAR',
               'ANNUAL': 'dyn_rain_annual', 'Jun-Sep': 'dyn_rain_kharif',
               'Oct-Dec': 'dyn_rain_rabi', 'Jan-Feb': 'dyn_rain_winter',
               'Mar-May': 'dyn_rain_summer'}
    rain = rain[list(col_map.keys())].rename(columns=col_map)
    rain['SUBDIVISION'] = rain['SUBDIVISION'].str.strip().str.upper()
    normals = rain.groupby('SUBDIVISION')[['dyn_rain_annual', 'dyn_rain_kharif']].mean()
    normals.columns = ['normal_annual', 'normal_kharif']
    df = df.copy()
    df['SUBDIVISION'] = df['District'].map(DISTRICT_TO_SUBDIVISION).fillna(DEFAULT_SUB).str.upper()
    max_rain_year = int(rain['YEAR'].max())
    df['_join_year'] = df['Year'].clip(upper=max_rain_year)
    merged = df.merge(rain, left_on=['SUBDIVISION', '_join_year'],
                      right_on=['SUBDIVISION', 'YEAR'], how='left')
    merged = merged.merge(normals, on='SUBDIVISION', how='left')
    merged['dyn_rain_anomaly_pct'] = ((merged['dyn_rain_annual'] - merged['normal_annual'])
                                       / merged['normal_annual'].replace(0, np.nan))
    merged['dyn_kharif_anomaly_pct'] = ((merged['dyn_rain_kharif'] - merged['normal_kharif'])
                                         / merged['normal_kharif'].replace(0, np.nan))
    return merged

# ── weather feature engineering ───────────────────────────────────────────────
def build_weather_features():
    """Aggregate daily ERA5 weather to district-year features."""
    w = pd.read_csv(WEATHER_CSV)
    w['date'] = pd.to_datetime(w['time'])
    w['Year'] = w['date'].dt.year
    w['month'] = w['date'].dt.month

    # season masks (meteorological seasons for India)
    w['season'] = np.select(
        [w['month'].isin([1, 2]),
         w['month'].isin([3, 4, 5]),
         w['month'].isin([6, 7, 8, 9]),
         w['month'].isin([10, 11, 12])],
        ['winter', 'summer', 'kharif', 'rabi'],
        default='other')

    g = w.groupby(['District', 'Year'])
    wx = pd.DataFrame({
        'wx_annual_rain': g['precipitation_sum'].sum(),
        'wx_annual_tmean': g['temperature_2m_mean'].mean(),
        'wx_annual_tmax': g['temperature_2m_max'].mean(),
        'wx_annual_tmin': g['temperature_2m_min'].mean(),
        'wx_rainy_days': g['precipitation_sum'].apply(lambda x: int((x >= 2.5).sum())),
        'wx_extreme_rain_days': g['precipitation_sum'].apply(lambda x: int((x >= 50).sum())),
        'wx_max_daily_rain': g['precipitation_sum'].max(),
        'wx_gdd_base10': g['temperature_2m_mean'].apply(lambda x: float(np.maximum(x - 10, 0).sum())),
        'wx_diurnal_range': (g['temperature_2m_max'].mean() - g['temperature_2m_min'].mean()),
    }).reset_index()

    # seasonal rainfall
    seas_rain = w.groupby(['District', 'Year', 'season'])['precipitation_sum'].sum().unstack('season', fill_value=0)
    seas_rain.columns = [f'wx_{c}_rain' for c in seas_rain.columns]
    wx = wx.merge(seas_rain.reset_index(), on=['District', 'Year'], how='left')

    # seasonal mean temp (kharif, rabi — the two main growing seasons)
    seas_temp = w.groupby(['District', 'Year', 'season'])['temperature_2m_mean'].mean().unstack('season')
    wx['wx_kharif_tmean'] = wx.merge(seas_temp[['kharif']].reset_index(),
                                     on=['District', 'Year'], how='left')['kharif']
    wx['wx_rabi_tmean'] = wx.merge(seas_temp[['rabi']].reset_index(),
                                   on=['District', 'Year'], how='left')['rabi']

    return wx

WEATHER_FEATURES = [
    'wx_annual_rain', 'wx_kharif_rain', 'wx_rabi_rain', 'wx_summer_rain', 'wx_winter_rain',
    'wx_annual_tmean', 'wx_kharif_tmean', 'wx_rabi_tmean',
    'wx_annual_tmax', 'wx_annual_tmin',
    'wx_rainy_days', 'wx_extreme_rain_days', 'wx_max_daily_rain',
    'wx_gdd_base10', 'wx_diurnal_range',
]

# ── crop-specific fit/predict (same as Phase 6/8) ─────────────────────────────
def fit_predict_crop_specific(X_tr, y_tr, crops_tr, X_te, crops_te, features,
                              model_params=None, model_cls=HistGradientBoostingRegressor):
    X_tr = X_tr[features].copy()
    X_te = X_te[features].copy()
    preds = np.full(len(X_te), np.nan)
    params = model_params if model_params is not None else HISTGBR_PARAMS
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
                   model_params=None, model_cls=HistGradientBoostingRegressor):
    oof = np.zeros(len(y_tr))
    gkf = GroupKFold(n_splits=5)
    for fold_tr_idx, fold_val_idx in gkf.split(X_tr, y_tr, groups_tr):
        X_f, y_f, crops_f = (X_tr.iloc[fold_tr_idx], y_tr.iloc[fold_tr_idx],
                             crops_tr.iloc[fold_tr_idx])
        X_v, crops_v = X_tr.iloc[fold_val_idx], crops_tr.iloc[fold_val_idx]
        oof[fold_val_idx] = fit_predict_crop_specific(
            X_f, y_f, crops_f, X_v, crops_v, features, model_params, model_cls)
    return oof

# ── F3 predictor (blend + Chickpea RF specialist) ─────────────────────────────
def f3_predict(df_tr, y_tr, crops_tr, df_te, crops_te, feats_A, feats_B):
    """F3: 0.8*HistGBR(feats_A) + 0.2*HistGBR(feats_B), Chickpea→RF on feats_B."""
    pA = fit_predict_crop_specific(df_tr, y_tr, crops_tr, df_te, crops_te, feats_A)
    pB = fit_predict_crop_specific(df_tr, y_tr, crops_tr, df_te, crops_te, feats_B)
    pC = BLEND_ALPHA * pA + (1 - BLEND_ALPHA) * pB
    # Chickpea specialist RF
    for crop in ['Chickpea']:
        mtr = (crops_tr == crop).values
        mte = crops_te == crop
        if mtr.sum() >= MIN_CROP_ROWS and mte.sum() > 0:
            m = RandomForestRegressor(**RF_PARAMS)
            m.fit(df_tr[mtr][feats_B], y_tr[mtr])
            pC[mte] = m.predict(df_te[mte][feats_B])
    return pC

def f3_oof(df_tr, y_tr, groups_tr, crops_tr, feats_A, feats_B):
    """F3 OOF via GroupKFold: blend OOFs, then Chickpea RF OOF."""
    oof_A = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, feats_A)
    oof_B = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, feats_B)
    oof_C = BLEND_ALPHA * oof_A + (1 - BLEND_ALPHA) * oof_B
    # Chickpea RF OOF
    for crop in ['Chickpea']:
        mask = (crops_tr == crop).values
        if mask.sum() < MIN_CROP_ROWS:
            continue
        X_c = df_tr[mask].reset_index(drop=True)
        y_c = y_tr[mask].reset_index(drop=True)
        g_c = groups_tr[mask].reset_index(drop=True)
        crops_c = crops_tr[mask].reset_index(drop=True)
        oof_spec = np.zeros(len(y_c))
        n_groups = g_c.nunique()
        n_splits = min(5, n_groups)
        if n_splits < 2:
            continue
        gkf = GroupKFold(n_splits=n_splits)
        for ftr, fva in gkf.split(X_c, y_c, g_c):
            m = RandomForestRegressor(**RF_PARAMS)
            m.fit(X_c.iloc[ftr][feats_B], y_c.iloc[ftr])
            oof_spec[fva] = m.predict(X_c.iloc[fva][feats_B])
        oof_C[mask] = oof_spec
    return oof_C

# ── per-crop breakdown ────────────────────────────────────────────────────────
def per_crop_metrics(y_true, y_pred, crops):
    out = {}
    for crop in sorted(np.unique(crops)):
        mask = crops == crop
        n, d = within_pct(y_true[mask], y_pred[mask], 0.25)
        out[crop] = {"correct": n, "total": d,
                     "pct": round(100 * n / d, 2) if d else None}
    return out

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("=== Phase 9: Weather-Enhanced Yield Prediction ===\n")

    # 1. Load yield data + dynamic rainfall
    df, base_features = load_base()
    df = add_dynamic_rainfall(df)
    df['group_key'] = df['District'].astype(str) + '|' + df['Year'].astype(str)

    # 2. Build weather features and merge
    wx = build_weather_features()
    print(f"Weather features: {len(WEATHER_FEATURES)} columns, "
          f"{len(wx)} district-year rows")
    n_before = len(df)
    df = df.merge(wx, on=['District', 'Year'], how='left')
    n_missing_wx = df[WEATHER_FEATURES].isna().any(axis=1).sum()
    print(f"Merged: {n_before} → {len(df)} rows; "
          f"{n_missing_wx} rows with missing weather features")
    assert n_missing_wx == 0, "Weather merge produced missing values!"

    groups = df['group_key'].values
    y = df['yield_per_hectare'].values

    # 3. Frozen split (identical to Phase 6/8)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr_idx, te_idx = next(gss.split(df, y, groups))
    df_tr, df_te = df.iloc[tr_idx].reset_index(drop=True), df.iloc[te_idx].reset_index(drop=True)
    y_tr, y_te = df_tr['yield_per_hectare'], df_te['yield_per_hectare'].values
    groups_tr, crops_tr, crops_te = df_tr['group_key'], df_tr['Crop'], df_te['Crop'].values

    # verify holdout matches frozen baseline
    frozen = np.load(FROZEN_NPZ, allow_pickle=True)
    assert len(te_idx) == len(frozen['y_test_true'])
    assert np.allclose(y_te, frozen['y_test_true'], atol=1e-6)
    print(f"Holdout verified: {len(te_idx)} rows match frozen baseline ✓")
    print(f"Split: train={len(df_tr)}, test={len(df_te)}\n")

    # Feature sets
    feats_A = base_features
    feats_B = base_features + [f for f in DYN_FEATURES if f not in base_features]
    feats_B_wx = feats_B + WEATHER_FEATURES
    feats_A_wx = feats_A + WEATHER_FEATURES  # for Candidate C variant

    # ═══════════════════════════════════════════════════════════════════════════
    # Candidate A: F3 baseline (unchanged)
    # ═══════════════════════════════════════════════════════════════════════════
    print("--- Candidate A: F3 baseline ---")
    pred_A = f3_predict(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te), feats_A, feats_B)
    m_A = metrics_dict(y_te, pred_A)
    oof_A = f3_oof(df_tr, y_tr, groups_tr, crops_tr, feats_A, feats_B)
    cv_A = metrics_dict(y_tr.values, oof_A)
    print(f"  Holdout: {m_A['correct_25']}/{m_A['total']} = {m_A['pct_25']}%  "
          f"MAE={m_A['mae']:.4f}  RMSE={m_A['rmse']:.4f}  R²={m_A['r2']:.4f}")
    print(f"  CV OOF : {cv_A['correct_25']}/{cv_A['total']} = {cv_A['pct_25']}%")
    assert m_A['correct_25'] == 742, f"Baseline F3 mismatch: {m_A['correct_25']}"

    # ═══════════════════════════════════════════════════════════════════════════
    # Candidate B: F3 + district weather features
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n--- Candidate B: F3 + weather features ---")
    pred_B = f3_predict(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te),
                        feats_A_wx, feats_B_wx)
    m_B = metrics_dict(y_te, pred_B)
    oof_B = f3_oof(df_tr, y_tr, groups_tr, crops_tr, feats_A_wx, feats_B_wx)
    cv_B = metrics_dict(y_tr.values, oof_B)
    print(f"  Holdout: {m_B['correct_25']}/{m_B['total']} = {m_B['pct_25']}%  "
          f"MAE={m_B['mae']:.4f}  RMSE={m_B['rmse']:.4f}  R²={m_B['r2']:.4f}")
    print(f"  CV OOF : {cv_B['correct_25']}/{cv_B['total']} = {cv_B['pct_25']}%")

    # ═══════════════════════════════════════════════════════════════════════════
    # Candidate C: F3 + weather + within-fold rainfall anomaly features
    #   Adds district-rainfall anomaly (% deviation from district normal),
    #   where the district normal is computed from the training fold only.
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n--- Candidate C: F3 + weather + within-fold rainfall anomaly ---")
    ANOM_FEATURES = ['wx_rain_anomaly_pct', 'wx_kharif_rain_anomaly_pct']

    def add_anomaly_features(df_tr_fold, df_val_fold):
        """Compute district normal annual rainfall from training fold, map to both."""
        normals = df_tr_fold.groupby('District')['wx_annual_rain'].mean().to_dict()
        kharif_norm = df_tr_fold.groupby('District')['wx_kharif_rain'].mean().to_dict()
        for d in [df_tr_fold, df_val_fold]:
            norm = d['District'].map(normals)
            d['wx_rain_anomaly_pct'] = (d['wx_annual_rain'] - norm) / norm.replace(0, np.nan)
            knorm = d['District'].map(kharif_norm)
            d['wx_kharif_rain_anomaly_pct'] = (d['wx_kharif_rain'] - knorm) / knorm.replace(0, np.nan)
        return df_tr_fold, df_val_fold

    feats_C_A = feats_A_wx + ANOM_FEATURES
    feats_C_B = feats_B_wx + ANOM_FEATURES

    # CV OOF for C
    oof_C = np.zeros(len(y_tr))
    gkf = GroupKFold(n_splits=5)
    for fold_tr_idx, fold_val_idx in gkf.split(df_tr, y_tr, groups_tr):
        X_f = df_tr.iloc[fold_tr_idx].copy()
        y_f = y_tr.iloc[fold_tr_idx]
        crops_f = crops_tr.iloc[fold_tr_idx]
        X_v = df_tr.iloc[fold_val_idx].copy()
        crops_v = crops_tr.iloc[fold_val_idx]
        X_f, X_v = add_anomaly_features(X_f, X_v)
        oof_C[fold_val_idx] = f3_predict(X_f, y_f, crops_f, X_v, crops_v, feats_C_A, feats_C_B)
    cv_C = metrics_dict(y_tr.values, oof_C)

    # Holdout for C
    df_tr_c = df_tr.copy()
    df_te_c = df_te.copy()
    df_tr_c, df_te_c = add_anomaly_features(df_tr_c, df_te_c)
    pred_C = f3_predict(df_tr_c, y_tr, crops_tr, df_te_c, pd.Series(crops_te), feats_C_A, feats_C_B)
    m_C = metrics_dict(y_te, pred_C)
    print(f"  Holdout: {m_C['correct_25']}/{m_C['total']} = {m_C['pct_25']}%  "
          f"MAE={m_C['mae']:.4f}  RMSE={m_C['rmse']:.4f}  R²={m_C['r2']:.4f}")
    print(f"  CV OOF : {cv_C['correct_25']}/{cv_C['total']} = {cv_C['pct_25']}%")

    # ═══════════════════════════════════════════════════════════════════════════
    # CV variability: per-fold within-25% for each candidate
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n--- CV fold variability (within-25% per fold) ---")
    def per_fold_scores(oof, y_true, groups):
        gkf = GroupKFold(n_splits=5)
        scores = []
        for _, val_idx in gkf.split(np.zeros(len(y_true)), y_true, groups):
            n, d = within_pct(y_true[val_idx], oof[val_idx], 0.25)
            scores.append(round(100 * n / d, 2) if d else None)
        return scores

    fold_A = per_fold_scores(oof_A, y_tr.values, groups_tr.values)
    fold_B = per_fold_scores(oof_B, y_tr.values, groups_tr.values)
    fold_C = per_fold_scores(oof_C, y_tr.values, groups_tr.values)
    print(f"  A: {fold_A}  mean={np.mean(fold_A):.2f}  std={np.std(fold_A):.2f}")
    print(f"  B: {fold_B}  mean={np.mean(fold_B):.2f}  std={np.std(fold_B):.2f}")
    print(f"  C: {fold_C}  mean={np.mean(fold_C):.2f}  std={np.std(fold_C):.2f}")

    # ═══════════════════════════════════════════════════════════════════════════
    # Per-crop breakdown (holdout) for A, B, C
    # ═══════════════════════════════════════════════════════════════════════════
    pc_A = per_crop_metrics(y_te, pred_A, crops_te)
    pc_B = per_crop_metrics(y_te, pred_B, crops_te)
    pc_C = per_crop_metrics(y_te, pred_C, crops_te)

    # ═══════════════════════════════════════════════════════════════════════════
    # Save results
    # ═══════════════════════════════════════════════════════════════════════════
    cv_scores = {'A': cv_A['pct_25'], 'B': cv_B['pct_25'], 'C': cv_C['pct_25']}
    best_cv = max(cv_scores, key=cv_scores.get)

    holdout = {'A': m_A, 'B': m_B, 'C': m_C}
    best_holdout = max(holdout, key=lambda k: holdout[k]['pct_25'] if holdout[k]['pct_25'] else -1)

    report = {
        "baseline_verified": {
            "correct_25": m_A['correct_25'], "total": m_A['total'],
            "pct_25": m_A['pct_25'], "mae": m_A['mae'],
            "rmse": m_A['rmse'], "r2": m_A['r2'],
            "note": "Phase 6 F3 reproduced exactly (742/1088 = 68.1985%)",
        },
        "weather_data": {
            "source": "Open-Meteo Archive API, ERA5",
            "n_districts": 19,
            "date_coverage": "2000-01-01 to 2017-12-31",
            "n_weather_features": len(WEATHER_FEATURES),
            "weather_features": WEATHER_FEATURES,
            "limitation": "ERA5 is reanalysis/weather-model data, not ground-station observations.",
        },
        "candidates": {
            "A": {"description": "F3 baseline (base + dynamic rainfall)",
                  "features_A_count": len(feats_A), "features_B_count": len(feats_B),
                  "holdout": m_A, "cv": cv_A, "fold_pct_25": fold_A,
                  "per_crop": pc_A},
            "B": {"description": "F3 + district-level weather features",
                  "features_A_count": len(feats_A_wx), "features_B_count": len(feats_B_wx),
                  "holdout": m_B, "cv": cv_B, "fold_pct_25": fold_B,
                  "per_crop": pc_B},
            "C": {"description": "F3 + weather + within-fold rainfall anomaly",
                  "features_A_count": len(feats_C_A), "features_B_count": len(feats_C_B),
                  "holdout": m_C, "cv": cv_C, "fold_pct_25": fold_C,
                  "per_crop": pc_C},
        },
        "cv_scores_pct_25": cv_scores,
        "cv_winner": best_cv,
        "holdout_best": best_holdout,
        "pp_gain_vs_baseline_holdout": {
            k: round(holdout[k]['pct_25'] - m_A['pct_25'], 4)
            for k in holdout if k != 'A'
        },
        "mae_change_vs_baseline": {
            k: round(holdout[k]['mae'] - m_A['mae'], 6) for k in holdout if k != 'A'
        },
        "rmse_change_vs_baseline": {
            k: round(holdout[k]['rmse'] - m_A['rmse'], 6) for k in holdout if k != 'A'
        },
        "r2_change_vs_baseline": {
            k: round(holdout[k]['r2'] - m_A['r2'], 6) for k in holdout if k != 'A'
        },
        "split": {"train": len(df_tr), "test": len(df_te),
                  "group_key": "District|Year", "test_size": 0.2, "random_state": 42},
        "xgboost_available": False,
        "xgboost_note": "XGBoost unavailable (libomp); HistGradientBoostingRegressor used as GBDT.",
    }
    with open(OUT_JSON, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nResults saved: {OUT_JSON}")

    # Feature coverage report
    feat_report = {
        "weather_features": WEATHER_FEATURES,
        "n_weather_features": len(WEATHER_FEATURES),
        "missing_values_after_merge": int(n_missing_wx),
        "coverage": "100% (all yield rows matched to district-year weather)",
        "feature_units": {
            "wx_annual_rain": "mm", "wx_kharif_rain": "mm", "wx_rabi_rain": "mm",
            "wx_summer_rain": "mm", "wx_winter_rain": "mm",
            "wx_annual_tmean": "°C", "wx_kharif_tmean": "°C", "wx_rabi_tmean": "°C",
            "wx_annual_tmax": "°C", "wx_annual_tmin": "°C",
            "wx_rainy_days": "count (precip ≥ 2.5mm)",
            "wx_extreme_rain_days": "count (precip ≥ 50mm)",
            "wx_max_daily_rain": "mm",
            "wx_gdd_base10": "°C-days (sum of max(0, tmean-10))",
            "wx_diurnal_range": "°C (mean of tmax-tmin)",
        },
        "aggregation": "daily → district-year",
        "season_definitions": {
            "winter": "Jan-Feb", "summer": "Mar-May",
            "kharif": "Jun-Sep", "rabi": "Oct-Dec",
        },
        "weather_summary_stats": wx[WEATHER_FEATURES].describe().round(2).to_dict(),
    }
    with open(FEATURE_REP, 'w') as f:
        json.dump(feat_report, f, indent=2)
    print(f"Feature coverage report saved: {FEATURE_REP}")

    # Final summary
    print("\n" + "=" * 70)
    print("PHASE 9 SUMMARY")
    print("=" * 70)
    print(f"  Baseline (A): {m_A['pct_25']}%  MAE={m_A['mae']:.4f}  "
          f"RMSE={m_A['rmse']:.4f}  R²={m_A['r2']:.4f}  ±10%={m_A['pct_10']:.2f}%")
    print(f"  B (+weather): {m_B['pct_25']}%  MAE={m_B['mae']:.4f}  "
          f"RMSE={m_B['rmse']:.4f}  R²={m_B['r2']:.4f}  ±10%={m_B['pct_10']:.2f}%")
    print(f"  C (+anomaly): {m_C['pct_25']}%  MAE={m_C['mae']:.4f}  "
          f"RMSE={m_C['rmse']:.4f}  R²={m_C['r2']:.4f}  ±10%={m_C['pct_10']:.2f}%")
    print(f"\n  CV winner: {best_cv} ({cv_scores[best_cv]:.2f}%)")
    print(f"  Holdout best: {best_holdout} ({holdout[best_holdout]['pct_25']:.2f}%)")
    gain_B = m_B['pct_25'] - m_A['pct_25']
    gain_C = m_C['pct_25'] - m_A['pct_25']
    print(f"  Δ vs baseline (pp): B={gain_B:+.2f}  C={gain_C:+.2f}")
    print("=" * 70)

if __name__ == "__main__":
    main()
