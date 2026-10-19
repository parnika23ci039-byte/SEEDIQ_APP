"""
Phase 10 — F3 Error Analysis & Targeted Improvement
=====================================================

Baseline (F3, verified): 742/1088 = 68.20% within ±25%, MAE=0.2378, R²=0.9589

Step 1: Reproduce F3 with GroupKFold OOF on the FULL training set.
Step 2: Deep error analysis (crop, district, year, yield range, outliers).
Step 3: Test ≤3 targeted hypotheses based on evidence.
Step 4: Compare using identical GroupKFold folds (grouped OOF for selection).
"""

import json, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupShuffleSplit, GroupKFold
warnings.filterwarnings("ignore")

# ── paths ──────────────────────────────────────────────────────────────────────
IMPROVED = Path(__file__).resolve().parents[1]
PHASE10  = Path(__file__).resolve().parent
DATA_DIR = IMPROVED / "data"
RES_DIR  = PHASE10 / "results"
RES_DIR.mkdir(parents=True, exist_ok=True)

YIELD_CSV  = DATA_DIR / "enriched_yield_karnataka.csv"
RAIN_CSV   = Path("/Users/apple/SeedIQ/SeedIQ/data/rainfall in india 1901-2015.csv")
MANIFEST   = IMPROVED / "models" / "yield_enriched_feature_manifest.json"
FROZEN_NPZ = IMPROVED / "results" / "phase3_senior_true_pred__yield_enriched.npz"

OUT_OOF_CSV = RES_DIR / "phase10_f3_oof_predictions.csv"
OUT_ERROR   = RES_DIR / "phase10_error_analysis.json"
OUT_RESULTS = RES_DIR / "phase10_hypothesis_results.json"

# ── F3 configuration (identical to Phase 6/8) ─────────────────────────────────
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
BLEND_ALPHA = 0.8

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

# ── data loading ──────────────────────────────────────────────────────────────
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

# ── F3 building blocks ────────────────────────────────────────────────────────
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

def f3_predict(df_tr, y_tr, crops_tr, df_te, crops_te, feats_A, feats_B):
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

def f3_oof(df_tr, y_tr, groups_tr, crops_tr, feats_A, feats_B):
    """GroupKFold(5) OOF for F3."""
    oof_A = np.zeros(len(y_tr))
    oof_B = np.zeros(len(y_tr))
    gkf = GroupKFold(n_splits=5)
    for ftr, fva in gkf.split(df_tr, y_tr, groups_tr):
        Xf, yf, cf = df_tr.iloc[ftr], y_tr.iloc[ftr], crops_tr.iloc[ftr]
        Xv, cv = df_tr.iloc[fva], crops_tr.iloc[fva]
        oof_A[fva] = fit_predict_crop_specific(Xf, yf, cf, Xv, cv, feats_A)
        oof_B[fva] = fit_predict_crop_specific(Xf, yf, cf, Xv, cv, feats_B)
    oof_C = BLEND_ALPHA * oof_A + (1 - BLEND_ALPHA) * oof_B
    # Chickpea RF specialist OOF
    for crop in ['Chickpea']:
        mask = (crops_tr == crop).values
        if mask.sum() < MIN_CROP_ROWS:
            continue
        Xc = df_tr[mask].reset_index(drop=True)
        yc = y_tr[mask].reset_index(drop=True)
        gc = groups_tr[mask].reset_index(drop=True)
        oof_spec = np.zeros(len(yc))
        n_splits = min(5, gc.nunique())
        if n_splits < 2:
            continue
        gkf_c = GroupKFold(n_splits=n_splits)
        for ftr, fva in gkf_c.split(Xc, yc, gc):
            m = RandomForestRegressor(**RF_PARAMS)
            m.fit(Xc.iloc[ftr][feats_B], yc.iloc[ftr])
            oof_spec[fva] = m.predict(Xc.iloc[fva][feats_B])
        oof_C[mask] = oof_spec
    return oof_C

# ── main: data + F3 OOF ───────────────────────────────────────────────────────
def main():
    print("=== Phase 10: F3 Error Analysis & Targeted Improvement ===\n")

    df, base_features = load_base()
    df = add_dynamic_rainfall(df)
    df['group_key'] = df['District'].astype(str) + '|' + df['Year'].astype(str)

    groups = df['group_key'].values
    y = df['yield_per_hectare'].values

    # Frozen split (identical to Phase 6/8) — used only for reference
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr_idx, te_idx = next(gss.split(df, y, groups))
    df_tr, df_te = df.iloc[tr_idx].reset_index(drop=True), df.iloc[te_idx].reset_index(drop=True)
    y_tr, y_te = df_tr['yield_per_hectare'], df_te['yield_per_hectare'].values
    groups_tr, crops_tr, crops_te = df_tr['group_key'], df_tr['Crop'], df_te['Crop'].values

    frozen = np.load(FROZEN_NPZ, allow_pickle=True)
    assert np.allclose(y_te, frozen['y_test_true'], atol=1e-6)
    print(f"Holdout verified: {len(te_idx)} rows match frozen baseline ✓")
    print(f"Train: {len(df_tr)}, Test: {len(df_te)}\n")

    feats_A = base_features
    feats_B = base_features + [f for f in DYN_FEATURES if f not in base_features]

    # ── F3 OOF on training set ──
    print("Computing F3 GroupKFold(5) OOF on training set...")
    oof = f3_oof(df_tr, y_tr, groups_tr, crops_tr, feats_A, feats_B)
    cv_metrics = metrics_dict(y_tr.values, oof)
    print(f"  F3 CV OOF: {cv_metrics['correct_25']}/{cv_metrics['total']} = "
          f"{cv_metrics['pct_25']}%  MAE={cv_metrics['mae']:.4f}  R²={cv_metrics['r2']:.4f}")

    # Save OOF predictions
    oof_df = df_tr[['District', 'Year', 'Crop', 'Area_Hectares', 'yield_per_hectare']].copy()
    oof_df['oof_pred'] = oof
    oof_df['residual'] = oof - oof_df['yield_per_hectare']
    oof_df['abs_residual'] = oof_df['residual'].abs()
    yt = oof_df['yield_per_hectare'].values
    oof_df['rel_error'] = oof_df['abs_residual'] / np.maximum(np.abs(yt), 1e-12)
    oof_df['within_25'] = oof_df['rel_error'] <= 0.25
    oof_df['within_10'] = oof_df['rel_error'] <= 0.10
    oof_df.to_csv(OUT_OOF_CSV, index=False)
    print(f"  OOF predictions saved: {OUT_OOF_CSV}\n")

    # ═══════════════════════════════════════════════════════════════════════════
    # ERROR ANALYSIS
    # ═══════════════════════════════════════════════════════════════════════════
    print("=== ERROR ANALYSIS (F3 OOF, n={}) ===".format(len(oof_df)))

    # Overall
    m = cv_metrics
    print(f"\n  Overall: ±25%={m['pct_25']}%  ±10%={m['pct_10']}%  "
          f"MAE={m['mae']:.4f}  RMSE={m['rmse']:.4f}  R²={m['r2']:.4f}  bias={m['bias']:+.4f}")

    # By crop
    print("\n  --- By Crop ---")
    crop_analysis = {}
    for crop in sorted(oof_df['Crop'].unique()):
        sub = oof_df[oof_df['Crop'] == crop]
        if len(sub) < 10:
            continue
        cm = metrics_dict(sub['yield_per_hectare'].values, sub['oof_pred'].values)
        overpred = (sub['residual'] > 0).mean()
        crop_analysis[crop] = {
            "n": len(sub),
            "pct_25": cm['pct_25'], "pct_10": cm['pct_10'],
            "mae": cm['mae'], "bias": cm['bias'],
            "overpred_pct": round(100 * overpred, 1),
            "y_true_mean": round(sub['yield_per_hectare'].mean(), 3),
            "y_true_median": round(sub['yield_per_hectare'].median(), 3),
        }
    for c, v in sorted(crop_analysis.items(), key=lambda x: x[1]['pct_25']):
        print(f"    {c:22s} n={v['n']:4d}  ±25%={v['pct_25']:6.2f}%  "
              f"MAE={v['mae']:.4f}  bias={v['bias']:+.4f}  "
              f"overpred={v['overpred_pct']:.0f}%  ymean={v['y_true_mean']:.3f}")

    # By actual yield range
    print("\n  --- By Actual Yield Range (t/ha) ---")
    bins = [0, 0.5, 1.0, 2.0, 3.0, 5.0, 20]
    labels = ['0-0.5', '0.5-1.0', '1.0-2.0', '2.0-3.0', '3.0-5.0', '5.0+']
    yield_range_analysis = {}
    for i in range(len(bins) - 1):
        mask = (oof_df['yield_per_hectare'] >= bins[i]) & (oof_df['yield_per_hectare'] < bins[i+1])
        sub = oof_df[mask]
        if len(sub) < 10:
            continue
        rm = metrics_dict(sub['yield_per_hectare'].values, sub['oof_pred'].values)
        overpred = (sub['residual'] > 0).mean()
        yield_range_analysis[labels[i]] = {
            "n": len(sub),
            "pct_25": rm['pct_25'], "mae": rm['mae'], "bias": rm['bias'],
            "overpred_pct": round(100 * overpred, 1),
        }
        print(f"    {labels[i]:8s} n={len(sub):4d}  ±25%={rm['pct_25']:6.2f}%  "
              f"MAE={rm['mae']:.4f}  bias={rm['bias']:+.4f}  overpred={100*overpred:.0f}%")

    # By district (top error contributors)
    print("\n  --- By District (worst 10 by MAE) ---")
    district_analysis = {}
    for d in oof_df['District'].unique():
        sub = oof_df[oof_df['District'] == d]
        if len(sub) < 10:
            continue
        dm = metrics_dict(sub['yield_per_hectare'].values, sub['oof_pred'].values)
        district_analysis[d] = {"n": len(sub), "pct_25": dm['pct_25'],
                                 "mae": dm['mae'], "bias": dm['bias']}
    for d, v in sorted(district_analysis.items(), key=lambda x: -x[1]['mae'])[:10]:
        print(f"    {d:20s} n={v['n']:4d}  ±25%={v['pct_25']:6.2f}%  "
              f"MAE={v['mae']:.4f}  bias={v['bias']:+.4f}")

    # By year
    print("\n  --- By Year ---")
    year_analysis = {}
    for yr in sorted(oof_df['Year'].unique()):
        sub = oof_df[oof_df['Year'] == yr]
        if len(sub) < 10:
            continue
        ym = metrics_dict(sub['yield_per_hectare'].values, sub['oof_pred'].values)
        year_analysis[int(yr)] = {"n": len(sub), "pct_25": ym['pct_25'],
                                   "mae": ym['mae'], "bias": ym['bias']}
        print(f"    {int(yr)}  n={len(sub):4d}  ±25%={ym['pct_25']:6.2f}%  "
              f"MAE={ym['mae']:.4f}  bias={ym['bias']:+.4f}")

    # Relative error distribution
    print("\n  --- Relative Error Distribution ---")
    rel = oof_df['rel_error']
    print(f"    median rel_err: {rel.median():.4f}")
    print(f"    75th pct: {rel.quantile(0.75):.4f}  90th: {rel.quantile(0.90):.4f}  "
          f"95th: {rel.quantile(0.95):.4f}  99th: {rel.quantile(0.99):.4f}")
    print(f"    rel_err > 0.5: {(rel > 0.5).sum()} ({100*(rel>0.5).mean():.1f}%)")
    print(f"    rel_err > 1.0: {(rel > 1.0).sum()} ({100*(rel>1.0).mean():.1f}%)")

    # Top 15 outliers
    print("\n  --- Top 15 Outliers (by abs residual) ---")
    outliers = oof_df.nlargest(15, 'abs_residual')[
        ['District', 'Year', 'Crop', 'yield_per_hectare', 'oof_pred', 'abs_residual', 'rel_error']]
    print(outliers.to_string(index=False))

    # Near-zero target check
    near0 = oof_df[oof_df['yield_per_hectare'] < 0.05]
    print(f"\n  --- Near-zero targets (yield < 0.05 t/ha) ---")
    print(f"    count: {len(near0)} ({100*len(near0)/len(oof_df):.2f}%)")
    if len(near0) > 0:
        print(f"    within ±25%: {near0['within_25'].sum()}/{len(near0)}")
        print(f"    mean abs_residual: {near0['abs_residual'].mean():.4f}")

    # Save error analysis
    error_report = {
        "overall": m,
        "by_crop": crop_analysis,
        "by_yield_range": yield_range_analysis,
        "by_district_worst10": dict(sorted(district_analysis.items(),
                                            key=lambda x: -x[1]['mae'])[:10]),
        "by_year": year_analysis,
        "relative_error_distribution": {
            "median": round(float(rel.median()), 4),
            "p75": round(float(rel.quantile(0.75)), 4),
            "p90": round(float(rel.quantile(0.90)), 4),
            "p95": round(float(rel.quantile(0.95)), 4),
            "p99": round(float(rel.quantile(0.99)), 4),
            "pct_above_0.5": round(100 * float((rel > 0.5).mean()), 2),
            "pct_above_1.0": round(100 * float((rel > 1.0).mean()), 2),
        },
        "top15_outliers": outliers.to_dict(orient='records'),
        "near_zero_targets": {
            "count": int(len(near0)),
            "pct": round(100 * len(near0) / len(oof_df), 4),
            "within_25": int(near0['within_25'].sum()),
        },
    }
    with open(OUT_ERROR, 'w') as f:
        json.dump(error_report, f, indent=2, default=str)
    print(f"\n  Error analysis saved: {OUT_ERROR}")

    # ═══════════════════════════════════════════════════════════════════════════
    # HYPOTHESES (based on error analysis evidence)
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    # Evidence from error analysis will guide hypotheses.
    # Common F3 failure modes (from Phase 6 memory): range compression
    # (low yields overpredicted, high yields underpredicted) due to
    # absolute_error loss in HistGBR.
    #
    # Hypothesis 1: Per-crop variance-stretch correction on OOF residuals
    #   (learn crop-mean and std ratio from training OOF, apply to correct
    #    range compression). F2v in Phase 6 but with proper within-fold learning.
    #
    # Hypothesis 2: Per-crop isotonic calibration (monotonic) on OOF predictions.
    #   Fits a non-decreasing mapping from predicted to actual, correcting
    #   systematic bias and range compression per crop.
    #
    # Hypothesis 3: Per-crop simple linear recalibration (pred → a*pred + b)
    #   learned from OOF, correcting both bias and slope (range compression).

    from sklearn.isotonic import IsotonicRegression

    # We evaluate all hypotheses on the SAME GroupKFold OOF predictions (oof).
    # Correction parameters are learned from OOF residuals, then we re-run
    # a nested CV to measure the corrected OOF performance.

    y_train = y_tr.values
    crops_train = crops_tr.values

    def evaluate_correction(oof_base, y_true, crops, correct_fn):
        """Apply correction function within nested GroupKFold to avoid leakage.
        correct_fn(y_true_train, oof_train, crops_train, oof_val, crops_val) -> corrected_val."""
        gkf = GroupKFold(n_splits=5)
        corrected = np.zeros(len(y_true))
        for ftr, fva in gkf.split(np.zeros(len(y_true)), y_true, groups_tr.values):
            corrected[fva] = correct_fn(
                y_true[ftr], oof_base[ftr], crops[ftr],
                oof_base[fva], crops[fva])
        return metrics_dict(y_true, corrected), corrected

    # ── Hypothesis 1: Per-crop variance-stretch correction ──
    print("\n--- Hypothesis 1: Per-crop variance-stretch (range decompression) ---")
    def h1_correct(yt_tr, oof_tr, c_tr, oof_va, c_va):
        out = oof_va.copy().astype(float)
        for crop in np.unique(c_va):
            mtr = c_tr == crop
            mva = c_va == crop
            if mtr.sum() < 20:
                continue
            p_tr = oof_tr[mtr]
            y_tr_c = yt_tr[mtr]
            mean_p = float(np.mean(p_tr))
            std_p = float(np.std(p_tr))
            std_y = float(np.std(y_tr_c))
            k = std_y / std_p if std_p > 1e-9 else 1.0
            k = max(0.7, min(1.5, k))
            out[mva] = mean_p + k * (out[mva] - mean_p)
        return out

    h1_metrics, h1_oof = evaluate_correction(oof, y_train, crops_train, h1_correct)
    print(f"  H1 CV: {h1_metrics['pct_25']:.2f}%  (base: {cv_metrics['pct_25']:.2f}%)  "
          f"MAE={h1_metrics['mae']:.4f}  R²={h1_metrics['r2']:.4f}  "
          f"Δ={h1_metrics['pct_25']-cv_metrics['pct_25']:+.2f}pp")

    # ── Hypothesis 2: Per-crop isotonic calibration ──
    print("\n--- Hypothesis 2: Per-crop isotonic calibration ---")
    def h2_correct(yt_tr, oof_tr, c_tr, oof_va, c_va):
        out = oof_va.copy().astype(float)
        for crop in np.unique(c_va):
            mtr = c_tr == crop
            mva = c_va == crop
            if mtr.sum() < 20:
                continue
            iso = IsotonicRegression(out_of_bounds='clip', y_min=0)
            iso.fit(oof_tr[mtr], yt_tr[mtr])
            out[mva] = iso.predict(oof_va[mva])
        return out

    h2_metrics, h2_oof = evaluate_correction(oof, y_train, crops_train, h2_correct)
    print(f"  H2 CV: {h2_metrics['pct_25']:.2f}%  (base: {cv_metrics['pct_25']:.2f}%)  "
          f"MAE={h2_metrics['mae']:.4f}  R²={h2_metrics['r2']:.4f}  "
          f"Δ={h2_metrics['pct_25']-cv_metrics['pct_25']:+.2f}pp")

    # ── Hypothesis 3: Per-crop linear recalibration (a*pred + b) ──
    print("\n--- Hypothesis 3: Per-crop linear recalibration (pred → a*pred + b) ---")
    def h3_correct(yt_tr, oof_tr, c_tr, oof_va, c_va):
        out = oof_va.copy().astype(float)
        for crop in np.unique(c_va):
            mtr = c_tr == crop
            mva = c_va == crop
            if mtr.sum() < 20:
                continue
            # Fit y = a*pred + b via least squares (no intercept constraint)
            X = np.column_stack([oof_tr[mtr], np.ones(mtr.sum())])
            coef, *_ = np.linalg.lstsq(X, yt_tr[mtr], rcond=None)
            a, b = coef[0], coef[1]
            # clamp slope to avoid extreme corrections
            a = max(0.5, min(2.0, a))
            out[mva] = a * out[mva] + b
            # floor at 0
            out[mva] = np.maximum(out[mva], 0)
        return out

    h3_metrics, h3_oof = evaluate_correction(oof, y_train, crops_train, h3_correct)
    print(f"  H3 CV: {h3_metrics['pct_25']:.2f}%  (base: {cv_metrics['pct_25']:.2f}%)  "
          f"MAE={h3_metrics['mae']:.4f}  R²={h3_metrics['r2']:.4f}  "
          f"Δ={h3_metrics['pct_25']-cv_metrics['pct_25']:+.2f}pp")

    # ── Per-crop breakdown for best hypothesis ──
    best = max([('base', cv_metrics), ('H1', h1_metrics), ('H2', h2_metrics), ('H3', h3_metrics)],
               key=lambda x: x[1]['pct_25'])
    print(f"\n  CV winner: {best[0]} ({best[1]['pct_25']:.2f}%)")

    # ── Reference holdout evaluation (frozen split, not used for selection) ──
    print("\n--- Reference: Frozen holdout evaluation (for reference only) ---")
    pred_base_hold = f3_predict(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te), feats_A, feats_B)
    m_base_hold = metrics_dict(y_te, pred_base_hold)
    assert m_base_hold['correct_25'] == 742

    # Learn correction params from FULL training OOF, apply to holdout
    def correct_holdout(pred_hold, crops_hold, correct_fn_name):
        out = pred_hold.copy().astype(float)
        for crop in np.unique(crops_hold):
            mtr = crops_train == crop
            mva = crops_hold == crop
            if mtr.sum() < 20:
                continue
            if correct_fn_name == 'H1':
                p_tr = oof[mtr]
                mean_p = float(np.mean(p_tr))
                std_p = float(np.std(p_tr))
                std_y = float(np.std(y_train[mtr]))
                k = std_y / std_p if std_p > 1e-9 else 1.0
                k = max(0.7, min(1.5, k))
                out[mva] = mean_p + k * (out[mva] - mean_p)
            elif correct_fn_name == 'H2':
                iso = IsotonicRegression(out_of_bounds='clip', y_min=0)
                iso.fit(oof[mtr], y_train[mtr])
                out[mva] = iso.predict(pred_hold[mva])
            elif correct_fn_name == 'H3':
                X = np.column_stack([oof[mtr], np.ones(mtr.sum())])
                coef, *_ = np.linalg.lstsq(X, y_train[mtr], rcond=None)
                a, b = max(0.5, min(2.0, coef[0])), coef[1]
                out[mva] = np.maximum(a * out[mva] + b, 0)
        return out

    h1_hold = correct_holdout(pred_base_hold, crops_te, 'H1')
    h2_hold = correct_holdout(pred_base_hold, crops_te, 'H2')
    h3_hold = correct_holdout(pred_base_hold, crops_te, 'H3')
    m_h1_hold = metrics_dict(y_te, h1_hold)
    m_h2_hold = metrics_dict(y_te, h2_hold)
    m_h3_hold = metrics_dict(y_te, h3_hold)

    print(f"  Baseline F3: {m_base_hold['pct_25']:.2f}%  (742/1088)")
    print(f"  H1 holdout:  {m_h1_hold['pct_25']:.2f}%  Δ={m_h1_hold['pct_25']-m_base_hold['pct_25']:+.2f}pp")
    print(f"  H2 holdout:  {m_h2_hold['pct_25']:.2f}%  Δ={m_h2_hold['pct_25']-m_base_hold['pct_25']:+.2f}pp")
    print(f"  H3 holdout:  {m_h3_hold['pct_25']:.2f}%  Δ={m_h3_hold['pct_25']-m_base_hold['pct_25']:+.2f}pp")

    # ── Per-crop Δ for best hypothesis on CV ──
    print(f"\n--- Per-crop CV Δ for {best[0]} ---")
    best_oof = {'base': oof, 'H1': h1_oof, 'H2': h2_oof, 'H3': h3_oof}[best[0]]
    crop_delta = {}
    for crop in sorted(np.unique(crops_train)):
        mask = crops_train == crop
        if mask.sum() < 20:
            continue
        nb, db = within_pct(y_train[mask], oof[mask], 0.25)
        nw, dw = within_pct(y_train[mask], best_oof[mask], 0.25)
        crop_delta[crop] = {"base_pct": round(100*nb/db, 2),
                             "best_pct": round(100*nw/dw, 2),
                             "delta_pp": round(100*(nw/dw - nb/db), 2)}
        if abs(crop_delta[crop]['delta_pp']) > 0.1:
            print(f"    {crop:22s} base={crop_delta[crop]['base_pct']:6.2f}%  "
                  f"{best[0]}={crop_delta[crop]['best_pct']:6.2f}%  "
                  f"Δ={crop_delta[crop]['delta_pp']:+.2f}pp")

    # Save results
    results = {
        "baseline_f3_cv": cv_metrics,
        "baseline_f3_holdout_reference": m_base_hold,
        "hypotheses": {
            "H1_variance_stretch": {
                "description": "Per-crop variance-stretch: pred_corrected = mean_pred + k*(pred - mean_pred), k = std(y)/std(pred) from OOF",
                "cv": h1_metrics,
                "holdout_reference": m_h1_hold,
            },
            "H2_isotonic": {
                "description": "Per-crop isotonic regression calibration on OOF predictions",
                "cv": h2_metrics,
                "holdout_reference": m_h2_hold,
            },
            "H3_linear_recalibration": {
                "description": "Per-crop linear recalibration: pred → a*pred + b from OOF least squares",
                "cv": h3_metrics,
                "holdout_reference": m_h3_hold,
            },
        },
        "cv_winner": best[0],
        "cv_winner_pct_25": best[1]['pct_25'],
        "cv_delta_pp_vs_base": round(best[1]['pct_25'] - cv_metrics['pct_25'], 4),
        "per_crop_delta_best": crop_delta,
        "selection_note": (
            "Model selection based on grouped OOF (GroupKFold 5) CV only. "
            "Frozen holdout shown for reference only — not used for selection."
        ),
    }
    with open(OUT_RESULTS, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved: {OUT_RESULTS}")

    print("\n" + "=" * 70)
    print("PHASE 10 SUMMARY")
    print("=" * 70)
    print(f"  Baseline F3 CV:  {cv_metrics['pct_25']:.2f}%  (holdout ref: {m_base_hold['pct_25']:.2f}%)")
    print(f"  H1 CV:           {h1_metrics['pct_25']:.2f}%  Δ={h1_metrics['pct_25']-cv_metrics['pct_25']:+.2f}pp  "
          f"(holdout ref: {m_h1_hold['pct_25']:.2f}%)")
    print(f"  H2 CV:           {h2_metrics['pct_25']:.2f}%  Δ={h2_metrics['pct_25']-cv_metrics['pct_25']:+.2f}pp  "
          f"(holdout ref: {m_h2_hold['pct_25']:.2f}%)")
    print(f"  H3 CV:           {h3_metrics['pct_25']:.2f}%  Δ={h3_metrics['pct_25']-cv_metrics['pct_25']:+.2f}pp  "
          f"(holdout ref: {m_h3_hold['pct_25']:.2f}%)")
    print(f"\n  CV winner: {best[0]} ({best[1]['pct_25']:.2f}%)")
    if best[1]['pct_25'] - cv_metrics['pct_25'] > 0.5:
        print("  → Measurable improvement detected on grouped CV.")
    else:
        print("  → No material improvement. F3 baseline retained.")
    print("=" * 70)

if __name__ == "__main__":
    main()
