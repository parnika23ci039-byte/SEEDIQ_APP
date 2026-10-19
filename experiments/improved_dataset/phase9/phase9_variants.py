"""
Phase 9 — Variant experiments: targeted weather integration.

Variant D: F3 with weather ONLY in the B branch (feats_A unchanged, feats_B += weather).
          The A branch (80% blend weight) stays identical to baseline.
Variant E: F3 with weather in B branch + Chickpea RF kept on original feats_B (no weather)
          to protect the specialist that degraded most.
"""
import json, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.model_selection import GroupShuffleSplit, GroupKFold
warnings.filterwarnings("ignore")

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase9_weather_yield import (
    load_base, add_dynamic_rainfall, build_weather_features, WEATHER_FEATURES,
    metrics_dict, within_pct, per_crop_metrics, f3_predict, f3_oof,
    grouped_cv_oof, fit_predict_crop_specific,
    HISTGBR_PARAMS, RF_PARAMS, MIN_CROP_ROWS, BLEND_ALPHA,
    YIELD_CSV, RAIN_CSV, MANIFEST, FROZEN_NPZ, WEATHER_CSV,
    DISTRICT_TO_SUBDIVISION, DEFAULT_SUB, DYN_FEATURES,
)

IMPROVED = Path(__file__).resolve().parents[1]
PHASE9 = Path(__file__).resolve().parent
RES_DIR = PHASE9 / "results"
OUT_JSON = RES_DIR / "phase9_variant_results.json"

def f3_predict_B_wx(df_tr, y_tr, crops_tr, df_te, crops_te, feats_A, feats_B,
                    chickpea_use_wx=True):
    """F3: 0.8*HistGBR(feats_A) + 0.2*HistGBR(feats_B), Chickpea→RF.
    If chickpea_use_wx=False, Chickpea RF uses feats_A (no weather) instead of feats_B."""
    pA = fit_predict_crop_specific(df_tr, y_tr, crops_tr, df_te, crops_te, feats_A)
    pB = fit_predict_crop_specific(df_tr, y_tr, crops_tr, df_te, crops_te, feats_B)
    pC = BLEND_ALPHA * pA + (1 - BLEND_ALPHA) * pB
    for crop in ['Chickpea']:
        mtr = (crops_tr == crop).values
        mte = crops_te == crop
        if mtr.sum() >= MIN_CROP_ROWS and mte.sum() > 0:
            m = RandomForestRegressor(**RF_PARAMS)
            chickpea_feats = feats_B if chickpea_use_wx else feats_A
            m.fit(df_tr[mtr][chickpea_feats], y_tr[mtr])
            pC[mte] = m.predict(df_te[mte][chickpea_feats])
    return pC

def f3_oof_B_wx(df_tr, y_tr, groups_tr, crops_tr, feats_A, feats_B, chickpea_use_wx=True):
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
        chickpea_feats = feats_B if chickpea_use_wx else feats_A
        for ftr, fva in gkf.split(X_c, y_c, g_c):
            m = RandomForestRegressor(**RF_PARAMS)
            m.fit(X_c.iloc[ftr][chickpea_feats], y_c.iloc[ftr])
            oof_spec[fva] = m.predict(X_c.iloc[fva][chickpea_feats])
        oof_C[mask] = oof_spec
    return oof_C

def main():
    print("=== Phase 9 Variants: targeted weather integration ===\n")
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
    feats_B_wx = feats_B + WEATHER_FEATURES

    results = {}

    # Variant D: weather only in B branch (A unchanged)
    print("--- Variant D: weather ONLY in B branch (A unchanged) ---")
    pred_D = f3_predict_B_wx(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te),
                             feats_A, feats_B_wx, chickpea_use_wx=True)
    m_D = metrics_dict(y_te, pred_D)
    oof_D = f3_oof_B_wx(df_tr, y_tr, groups_tr, crops_tr, feats_A, feats_B_wx, chickpea_use_wx=True)
    cv_D = metrics_dict(y_tr.values, oof_D)
    print(f"  Holdout: {m_D['correct_25']}/{m_D['total']} = {m_D['pct_25']}%  "
          f"MAE={m_D['mae']:.4f}  R²={m_D['r2']:.4f}")
    print(f"  CV OOF : {cv_D['correct_25']}/{cv_D['total']} = {cv_D['pct_25']}%")
    results['D'] = {"holdout": m_D, "cv": cv_D,
                    "per_crop": per_crop_metrics(y_te, pred_D, crops_te),
                    "desc": "F3, weather only in B branch (A unchanged)"}

    # Variant E: weather in B branch, Chickpea RF on A (no weather)
    print("\n--- Variant E: weather in B, Chickpea RF on A (no weather) ---")
    pred_E = f3_predict_B_wx(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te),
                             feats_A, feats_B_wx, chickpea_use_wx=False)
    m_E = metrics_dict(y_te, pred_E)
    oof_E = f3_oof_B_wx(df_tr, y_tr, groups_tr, crops_tr, feats_A, feats_B_wx, chickpea_use_wx=False)
    cv_E = metrics_dict(y_tr.values, oof_E)
    print(f"  Holdout: {m_E['correct_25']}/{m_E['total']} = {m_E['pct_25']}%  "
          f"MAE={m_E['mae']:.4f}  R²={m_E['r2']:.4f}")
    print(f"  CV OOF : {cv_E['correct_25']}/{cv_E['total']} = {cv_E['pct_25']}%")
    results['E'] = {"holdout": m_E, "cv": cv_E,
                    "per_crop": per_crop_metrics(y_te, pred_E, crops_te),
                    "desc": "F3, weather in B, Chickpea RF on A (no weather)"}

    # Variant F: weather only in B branch, replace dyn_rain with district weather in B
    # (B uses base + wx instead of base + dyn_rain + wx)
    print("\n--- Variant F: B = base + wx (no subdivision dyn_rain) ---")
    feats_F_B = feats_A + WEATHER_FEATURES  # base + district wx, no dyn_rain
    pred_F = f3_predict_B_wx(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te),
                             feats_A, feats_F_B, chickpea_use_wx=False)
    m_F = metrics_dict(y_te, pred_F)
    oof_F = f3_oof_B_wx(df_tr, y_tr, groups_tr, crops_tr, feats_A, feats_F_B, chickpea_use_wx=False)
    cv_F = metrics_dict(y_tr.values, oof_F)
    print(f"  Holdout: {m_F['correct_25']}/{m_F['total']} = {m_F['pct_25']}%  "
          f"MAE={m_F['mae']:.4f}  R²={m_F['r2']:.4f}")
    print(f"  CV OOF : {cv_F['correct_25']}/{cv_F['total']} = {cv_F['pct_25']}%")
    results['F'] = {"holdout": m_F, "cv": cv_F,
                    "per_crop": per_crop_metrics(y_te, pred_F, crops_te),
                    "desc": "F3, B = base + district wx (no subdivision dyn_rain), Chickpea on A"}

    print("\n" + "=" * 60)
    print("VARIANT SUMMARY (vs baseline A = 68.1985%)")
    print("=" * 60)
    for k, v in results.items():
        h = v['holdout']
        gain = h['pct_25'] - 68.1985
        print(f"  {k}: {h['pct_25']:.2f}%  MAE={h['mae']:.4f}  R²={h['r2']:.4f}  "
              f"Δ={gain:+.2f}pp  (CV={v['cv']['pct_25']:.2f}%)")

    with open(OUT_JSON, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {OUT_JSON}")

if __name__ == "__main__":
    main()
