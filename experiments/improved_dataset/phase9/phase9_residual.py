"""
Phase 9 — Residual correction variant.

Idea: Baseline F3 already captures crop + district + soil + static-rain signal well.
Weather has weak marginal signal but does correlate with yield for some crops.
Instead of adding weather to the base model (which overfits crop-specific models),
train a lightweight residual model on weather features to correct F3's OOF residuals.

Leakage-safe:
  - Residual model trained on F3's GroupKFold OOF residuals (training data only).
  - Nested GroupKFold to evaluate the correction on training OOF.
  - Holdout correction applied once.
"""
import json, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupShuffleSplit, GroupKFold
from sklearn.preprocessing import StandardScaler
warnings.filterwarnings("ignore")

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase9_weather_yield import (
    load_base, add_dynamic_rainfall, build_weather_features, WEATHER_FEATURES,
    metrics_dict, within_pct, per_crop_metrics,
    HISTGBR_PARAMS, RF_PARAMS, MIN_CROP_ROWS, BLEND_ALPHA,
    FROZEN_NPZ, DISTRICT_TO_SUBDIVISION, DEFAULT_SUB, DYN_FEATURES,
)

IMPROVED = Path(__file__).resolve().parents[1]
PHASE9 = Path(__file__).resolve().parent
RES_DIR = PHASE9 / "results"
OUT_JSON = RES_DIR / "phase9_residual_results.json"


def fit_predict_crop_specific(X_tr, y_tr, crops_tr, X_te, crops_te, features,
                              model_params=None, model_cls=HistGradientBoostingRegressor):
    X_tr = X_tr[features].copy()
    X_te = X_te[features].copy()
    preds = np.full(len(X_te), np.nan)
    params = model_params if model_params is not None else HISTGBR_PARAMS
    for crop in np.unique(crops_te):
        mtr = crops_tr == crop
        mte = crops_te == crop
        if mtr.sum() >= MIN_CROP_ROWS:
            m = model_cls(**params)
            m.fit(X_tr[mtr], y_tr[mtr])
            preds[mte] = m.predict(X_te[mte])
        else:
            preds[mte] = y_tr[mtr].mean() if mtr.sum() > 0 else y_tr.mean()
    return preds


def grouped_cv_oof(X_tr, y_tr, groups_tr, crops_tr, features,
                   model_params=None, model_cls=HistGradientBoostingRegressor):
    oof = np.zeros(len(y_tr))
    gkf = GroupKFold(n_splits=5)
    for ftr, fva in gkf.split(X_tr, y_tr, groups_tr):
        X_f, y_f, c_f = X_tr.iloc[ftr], y_tr.iloc[ftr], crops_tr.iloc[ftr]
        X_v, c_v = X_tr.iloc[fva], crops_tr.iloc[fva]
        oof[fva] = fit_predict_crop_specific(X_f, y_f, c_f, X_v, c_v, features,
                                             model_params, model_cls)
    return oof


def f3_oof(df_tr, y_tr, groups_tr, crops_tr, feats_A, feats_B):
    oof_A = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, feats_A)
    oof_B = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, feats_B)
    oof_C = BLEND_ALPHA * oof_A + (1 - BLEND_ALPHA) * oof_B
    for crop in ['Chickpea']:
        mask = (crops_tr == crop).values
        if mask.sum() < MIN_CROP_ROWS:
            continue
        X_c = df_tr[mask].reset_index(drop=True)
        y_c = y_tr[mask].reset_index(drop=True)
        g_c = groups_tr[mask].reset_index(drop=True)
        oof_spec = np.zeros(len(y_c))
        n_splits = min(5, g_c.nunique())
        if n_splits < 2:
            continue
        gkf = GroupKFold(n_splits=n_splits)
        for ftr, fva in gkf.split(X_c, y_c, g_c):
            m = RandomForestRegressor(**RF_PARAMS)
            m.fit(X_c.iloc[ftr][feats_B], y_c.iloc[ftr])
            oof_spec[fva] = m.predict(X_c.iloc[fva][feats_B])
        oof_C[mask] = oof_spec
    return oof_C


def f3_holdout(df_tr, y_tr, crops_tr, df_te, crops_te, feats_A, feats_B):
    pA = fit_predict_crop_specific(df_tr, y_tr, crops_tr, df_te, crops_te, feats_A)
    pB = fit_predict_crop_specific(df_tr, y_tr, crops_tr, df_te, crops_te, feats_B)
    pC = BLEND_ALPHA * pA + (1 - BLEND_ALPHA) * pB
    for crop in ['Chickpea']:
        mtr = (crops_tr == crop).values
        mte = crops_te == crop
        if mtr.sum() >= MIN_CROP_ROWS and mte.sum() > 0:
            m = RandomForestRegressor(**RF_PARAMS)
            m.fit(df_tr[mtr][feats_B], y_tr[mtr])
            pC[mte] = m.predict(df_te[mte][feats_B])
    return pC


def main():
    print("=== Phase 9: Residual-correction with weather ===\n")
    df, base_features = load_base()
    df = add_dynamic_rainfall(df)
    df['group_key'] = df['District'].astype(str) + '|' + df['Year'].astype(str)
    wx = build_weather_features()
    df = df.merge(wx, on=['District', 'Year'], how='left')
    assert df[WEATHER_FEATURES].isna().any(axis=1).sum() == 0

    groups = df['group_key'].values
    y = df['yield_per_hectare'].values
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr_idx, te_idx = next(gss.split(df, y, groups))
    df_tr, df_te = df.iloc[tr_idx].reset_index(drop=True), df.iloc[te_idx].reset_index(drop=True)
    y_tr, y_te = df_tr['yield_per_hectare'], df_te['yield_per_hectare'].values
    groups_tr, crops_tr, crops_te = df_tr['group_key'], df_tr['Crop'], df_te['Crop'].values

    frozen = np.load(FROZEN_NPZ, allow_pickle=True)
    assert np.allclose(y_te, frozen['y_test_true'], atol=1e-6)

    feats_A = base_features
    feats_B = base_features + [f for f in DYN_FEATURES if f not in base_features]

    # 1. Baseline F3
    print("Baseline F3...")
    oof_base = f3_oof(df_tr, y_tr, groups_tr, crops_tr, feats_A, feats_B)
    pred_base = f3_holdout(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te), feats_A, feats_B)
    m_base = metrics_dict(y_te, pred_base)
    cv_base = metrics_dict(y_tr.values, oof_base)
    print(f"  Baseline holdout: {m_base['pct_25']:.2f}%  CV: {cv_base['pct_25']:.2f}%")
    assert m_base['correct_25'] == 742

    # 2. Residual = y_true - oof_base (training data only)
    residuals = y_tr.values - oof_base

    # Weather features for residual model
    # Use a subset that has meaningful per-crop correlation: rainfall + rainy days
    WX_SUBSET = ['wx_annual_rain', 'wx_kharif_rain', 'wx_rabi_rain', 'wx_summer_rain',
                 'wx_rainy_days', 'wx_extreme_rain_days', 'wx_diurnal_range',
                 'wx_annual_tmean', 'wx_kharif_tmean', 'wx_gdd_base10']

    Xwx_tr = df_tr[WX_SUBSET].values
    Xwx_te = df_te[WX_SUBSET].values

    # 3. Nested CV: train residual model on fold-train, predict fold-val residual correction
    print("\nNested CV for residual correction (Ridge on weather)...")
    gkf = GroupKFold(n_splits=5)
    oof_corrected = np.zeros(len(y_tr))
    fold_scores_base = []
    fold_scores_corr = []
    for ftr, fva in gkf.split(df_tr, y_tr, groups_tr):
        # residual model on fold-train
        scaler = StandardScaler()
        Xtr_s = scaler.fit_transform(Xwx_tr[ftr])
        Xva_s = scaler.transform(Xwx_tr[fva])
        ridge = Ridge(alpha=1.0)
        ridge.fit(Xtr_s, residuals[ftr])
        corr_val = ridge.predict(Xva_s)
        oof_corrected[fva] = oof_base[fva] + corr_val

        nb, db = within_pct(y_tr.values[fva], oof_base[fva], 0.25)
        nc, dc = within_pct(y_tr.values[fva], oof_corrected[fva], 0.25)
        fold_scores_base.append(round(100 * nb / db, 2))
        fold_scores_corr.append(round(100 * nc / dc, 2))

    cv_corr = metrics_dict(y_tr.values, oof_corrected)
    print(f"  Corrected CV: {cv_corr['pct_25']:.2f}%  (base: {cv_base['pct_25']:.2f}%)")
    print(f"  Fold base:     {fold_scores_base}")
    print(f"  Fold corrected: {fold_scores_corr}")

    # 4. Train residual model on full training OOF residuals, apply to holdout
    scaler_full = StandardScaler()
    Xtr_full = scaler_full.fit_transform(Xwx_tr)
    ridge_full = Ridge(alpha=1.0)
    ridge_full.fit(Xtr_full, residuals)
    Xte_full = scaler_full.transform(Xwx_te)
    corr_holdout = ridge_full.predict(Xte_full)
    pred_corr = pred_base + corr_holdout
    m_corr = metrics_dict(y_te, pred_corr)

    print(f"\n  Corrected holdout: {m_corr['correct_25']}/{m_corr['total']} = {m_corr['pct_25']:.2f}%  "
          f"MAE={m_corr['mae']:.4f}  R²={m_corr['r2']:.4f}")
    print(f"  Baseline holdout:  {m_base['correct_25']}/{m_base['total']} = {m_base['pct_25']:.2f}%  "
          f"MAE={m_base['mae']:.4f}  R²={m_base['r2']:.4f}")
    gain = m_corr['pct_25'] - m_base['pct_25']
    print(f"  Δ: {gain:+.2f}pp")

    # 5. Try crop-specific residual models (one Ridge per crop)
    print("\n--- Crop-specific residual models (Ridge per crop) ---")
    oof_corr_crop = oof_base.copy()
    for crop in np.unique(crops_tr):
        mask = (crops_tr == crop).values
        if mask.sum() < 30:
            continue
        g_c = groups_tr[mask].reset_index(drop=True)
        n_splits = min(5, g_c.nunique())
        if n_splits < 2:
            continue
        Xc = Xwx_tr[mask]
        rc = residuals[mask]
        gkf_c = GroupKFold(n_splits=n_splits)
        for ftr, fva in gkf_c.split(Xc, rc, g_c):
            sc = StandardScaler()
            Xs = sc.fit_transform(Xc[ftr])
            ridge_c = Ridge(alpha=1.0)
            ridge_c.fit(Xs, rc[ftr])
            oof_corr_crop[np.where(mask)[0][fva]] = (
                oof_base[np.where(mask)[0][fva]] + ridge_c.predict(sc.transform(Xc[fva])))
    cv_corr_crop = metrics_dict(y_tr.values, oof_corr_crop)
    print(f"  Crop-specific residual CV: {cv_corr_crop['pct_25']:.2f}%  "
          f"(base: {cv_base['pct_25']:.2f}%)")

    # Holdout crop-specific residual
    pred_corr_crop = pred_base.copy()
    for crop in np.unique(crops_te):
        mtr = (crops_tr == crop).values
        mte = crops_te == crop
        if mtr.sum() < 30 or mte.sum() == 0:
            continue
        sc = StandardScaler()
        Xs = sc.fit_transform(Xwx_tr[mtr])
        ridge_c = Ridge(alpha=1.0)
        ridge_c.fit(Xs, residuals[mtr])
        pred_corr_crop[mte] = pred_base[mte] + ridge_c.predict(sc.transform(Xwx_te[mte]))
    m_corr_crop = metrics_dict(y_te, pred_corr_crop)
    print(f"  Crop-specific residual holdout: {m_corr_crop['pct_25']:.2f}%  "
          f"Δ={m_corr_crop['pct_25']-m_base['pct_25']:+.2f}pp")

    results = {
        "baseline": {"holdout": m_base, "cv": cv_base,
                     "per_crop": per_crop_metrics(y_te, pred_base, crops_te)},
        "residual_ridge_global": {
            "desc": "Global Ridge residual correction on 10 weather features",
            "weather_features": WX_SUBSET,
            "holdout": m_corr, "cv": cv_corr,
            "fold_pct_25_base": fold_scores_base,
            "fold_pct_25_corrected": fold_scores_corr,
            "per_crop": per_crop_metrics(y_te, pred_corr, crops_te),
        },
        "residual_ridge_crop_specific": {
            "desc": "Per-crop Ridge residual correction",
            "holdout": m_corr_crop, "cv": cv_corr_crop,
            "per_crop": per_crop_metrics(y_te, pred_corr_crop, crops_te),
        },
    }
    with open(OUT_JSON, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {OUT_JSON}")

    print("\n" + "=" * 60)
    print("RESIDUAL CORRECTION SUMMARY")
    print("=" * 60)
    print(f"  Baseline:              {m_base['pct_25']:.2f}%  (CV {cv_base['pct_25']:.2f}%)")
    print(f"  Global Ridge residual: {m_corr['pct_25']:.2f}%  (CV {cv_corr['pct_25']:.2f}%)  "
          f"Δ={m_corr['pct_25']-m_base['pct_25']:+.2f}pp")
    print(f"  Crop-specific Ridge:   {m_corr_crop['pct_25']:.2f}%  (CV {cv_corr_crop['pct_25']:.2f}%)  "
          f"Δ={m_corr_crop['pct_25']-m_base['pct_25']:+.2f}pp")

if __name__ == "__main__":
    main()
