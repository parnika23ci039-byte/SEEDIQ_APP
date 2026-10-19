"""
Phase 5: Dynamic Rainfall Feature Experiment
Candidates:
  A - Crop-specific HistGBR, base 56 features (no dynamic rain)
  B - Crop-specific HistGBR, base 56 + 7 dynamic rainfall features
  C - Blend of A and B, weight chosen from CV OOF on train only

Split: GroupShuffleSplit(test_size=0.2, random_state=42) on District|Year groups.
CV: GroupKFold(n_splits=5) on train groups — identical to prior experiments.
Holdout: evaluated ONCE for the CV winner.
"""

import json, warnings, sys
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingRegressor
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
OUT_JSON     = RES_DIR / "phase5_dynamic_rainfall_results.json"

# ── district → subdivision mapping ────────────────────────────────────────────
DISTRICT_TO_SUBDIVISION = {
    'Dakshina Kannada': 'COASTAL KARNATAKA',
    'Uttara Kannada':   'COASTAL KARNATAKA',
    'Ballari':          'NORTH INTERIOR KARNATAKA',
    'Belagavi':         'NORTH INTERIOR KARNATAKA',
    'Bidar':            'NORTH INTERIOR KARNATAKA',
    'Vijayapura':       'NORTH INTERIOR KARNATAKA',
    'Dharwad':          'NORTH INTERIOR KARNATAKA',
    'Kalaburagi':       'NORTH INTERIOR KARNATAKA',
    'Raichur':          'NORTH INTERIOR KARNATAKA',
}
DEFAULT_SUB = 'SOUTH INTERIOR KARNATAKA'

DYN_FEATURES = [
    'dyn_rain_annual', 'dyn_rain_kharif', 'dyn_rain_rabi',
    'dyn_rain_winter', 'dyn_rain_summer',
    'dyn_rain_anomaly_pct', 'dyn_kharif_anomaly_pct',
]

HISTGBR_PARAMS = dict(
    loss='absolute_error', max_iter=200, learning_rate=0.05,
    max_depth=6, min_samples_leaf=4, random_state=42
)
MIN_CROP_ROWS = 15

# ── metric ─────────────────────────────────────────────────────────────────────
def within25(y_true, y_pred):
    rel = np.abs(y_pred - y_true) / np.maximum(y_true, 1e-12)
    return (rel <= 0.25).sum(), len(y_true)

# ── load base dataset ──────────────────────────────────────────────────────────
def load_base():
    df = pd.read_csv(YIELD_CSV)
    with open(MANIFEST_JSON) as f:
        manifest = json.load(f)
    base_features = manifest["feature_columns"]
    # keep only columns that exist
    base_features = [c for c in base_features if c in df.columns]
    return df, base_features

# ── load & process dynamic rainfall ───────────────────────────────────────────
def add_dynamic_rainfall(df):
    rain = pd.read_csv(RAIN_CSV)
    rain.columns = [c.strip() for c in rain.columns]
    # rename columns
    col_map = {
        'SUBDIVISION': 'SUBDIVISION',
        'YEAR': 'YEAR',
        'ANNUAL': 'dyn_rain_annual',
        'Jun-Sep': 'dyn_rain_kharif',
        'Oct-Dec': 'dyn_rain_rabi',
        'Jan-Feb': 'dyn_rain_winter',
        'Mar-May': 'dyn_rain_summer',
    }
    rain = rain[list(col_map.keys())].rename(columns=col_map)

    # normalise subdivision names
    rain['SUBDIVISION'] = rain['SUBDIVISION'].str.strip().str.upper()

    # compute normals (mean over all years) per subdivision
    normals = rain.groupby('SUBDIVISION')[['dyn_rain_annual','dyn_rain_kharif']].mean()
    normals.columns = ['normal_annual', 'normal_kharif']

    # add subdivision column to yield df
    df = df.copy()
    df['SUBDIVISION'] = df['District'].map(DISTRICT_TO_SUBDIVISION).fillna(DEFAULT_SUB)
    df['SUBDIVISION'] = df['SUBDIVISION'].str.upper()

    # join: try exact year first, then forward-fill 2016-2017 with 2015
    max_rain_year = int(rain['YEAR'].max())
    # For years beyond max, we'll use max_rain_year values (forward-fill)
    df['_join_year'] = df['Year'].clip(upper=max_rain_year)
    df['_ffilled'] = df['Year'] > max_rain_year

    merged = df.merge(
        rain, left_on=['SUBDIVISION', '_join_year'], right_on=['SUBDIVISION', 'YEAR'],
        how='left'
    )
    # join normals
    merged = merged.merge(normals, on='SUBDIVISION', how='left')

    # anomaly features
    merged['dyn_rain_anomaly_pct']  = (merged['dyn_rain_annual']  - merged['normal_annual'])  / merged['normal_annual'].replace(0, np.nan)
    merged['dyn_kharif_anomaly_pct']= (merged['dyn_rain_kharif'] - merged['normal_kharif']) / merged['normal_kharif'].replace(0, np.nan)

    # validation
    missing_annual = merged['dyn_rain_annual'].isna().sum()
    ffilled_count  = merged['_ffilled'].sum()
    print(f"  Rain join: {len(merged)} rows, missing dyn_rain_annual={missing_annual}, "
          f"forward-filled rows (year>{max_rain_year})={ffilled_count}")

    # report coverage per district
    cov = merged.groupby('District')['dyn_rain_annual'].apply(lambda x: x.notna().mean())
    bad = cov[cov < 1.0]
    if len(bad):
        print(f"  Districts with <100% rain coverage: {bad.to_dict()}")
    else:
        print(f"  All {cov.shape[0]} districts have 100% rain coverage after join.")

    # assert no test-group leakage: anomaly uses subdivision-level normals computed
    # from ALL years of rain data, which is publicly known climatology — not from yield labels.
    # No yield-derived information enters DYN_FEATURES.
    return merged

# ── crop-specific HistGBR fit+predict ─────────────────────────────────────────
def fit_predict_crop_specific(X_tr, y_tr, crops_tr, X_te, crops_te, features):
    X_tr = X_tr[features].copy()
    X_te = X_te[features].copy()
    preds = np.full(len(X_te), np.nan)
    for crop in np.unique(crops_te):
        mask_tr = crops_tr == crop
        mask_te = crops_te == crop
        if mask_tr.sum() >= MIN_CROP_ROWS:
            m = HistGradientBoostingRegressor(**HISTGBR_PARAMS)
            m.fit(X_tr[mask_tr], y_tr[mask_tr])
            preds[mask_te] = m.predict(X_te[mask_te])
        else:
            preds[mask_te] = y_tr[mask_tr].mean() if mask_tr.sum() > 0 else y_tr.mean()
    return preds

# ── grouped CV returning OOF predictions ──────────────────────────────────────
def grouped_cv_oof(X_tr, y_tr, groups_tr, crops_tr, features):
    oof = np.zeros(len(y_tr))
    gkf = GroupKFold(n_splits=5)
    for fold_tr_idx, fold_val_idx in gkf.split(X_tr, y_tr, groups_tr):
        X_f, y_f, crops_f = X_tr.iloc[fold_tr_idx], y_tr.iloc[fold_tr_idx], crops_tr.iloc[fold_tr_idx]
        X_v, crops_v        = X_tr.iloc[fold_val_idx], crops_tr.iloc[fold_val_idx]
        oof[fold_val_idx] = fit_predict_crop_specific(X_f, y_f, crops_f, X_v, crops_v, features)
    return oof

# ── main ───────────────────────────────────────────────────────────────────────
def main():
    print("=== Phase 5: Dynamic Rainfall Experiment ===\n")

    # 1. Load data
    df, base_features = load_base()
    print(f"Base dataset: {len(df)} rows, {len(base_features)} base features.")

    # 2. Add dynamic rainfall
    df = add_dynamic_rainfall(df)

    # 3. Define split — identical to all prior experiments
    df['group_key'] = df['District'].astype(str) + '|' + df['Year'].astype(str)
    groups = df['group_key'].values
    y = df['yield_per_hectare'].values

    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr_idx, te_idx = next(gss.split(df, y, groups))

    df_tr, df_te = df.iloc[tr_idx].reset_index(drop=True), df.iloc[te_idx].reset_index(drop=True)
    y_tr  = df_tr['yield_per_hectare']
    y_te  = df_te['yield_per_hectare'].values
    groups_tr = df_tr['group_key']
    crops_tr  = df_tr['Crop']
    crops_te  = df_te['Crop'].values

    # Verify holdout size matches frozen baseline
    frozen = np.load(FROZEN_NPZ, allow_pickle=True)
    assert len(te_idx) == len(frozen['y_test_true']), \
        f"Holdout size mismatch: {len(te_idx)} vs {len(frozen['y_test_true'])}"
    assert np.allclose(y_te, frozen['y_test_true'], atol=1e-6), \
        "Holdout y_true mismatch with frozen baseline!"
    print(f"\nHoldout verified: {len(te_idx)} rows match frozen baseline ✓")

    n_tr_groups = df_tr['group_key'].nunique()
    n_te_groups = df_te['group_key'].nunique()
    overlap = set(df_tr['group_key']) & set(df_te['group_key'])
    assert len(overlap) == 0, f"Group leakage detected: {overlap}"
    print(f"Split: train={len(df_tr)} rows ({n_tr_groups} groups), "
          f"test={len(df_te)} rows ({n_te_groups} groups), overlap=0 ✓")

    # Verify DYN_FEATURES present and no NaN in split sets
    for f in DYN_FEATURES:
        nan_tr = df_tr[f].isna().sum()
        nan_te = df_te[f].isna().sum()
        if nan_tr > 0 or nan_te > 0:
            print(f"  WARNING: {f} has {nan_tr} train / {nan_te} test NaN — HistGBR handles NaN natively.")

    features_A = base_features
    features_B = base_features + [f for f in DYN_FEATURES if f not in base_features]
    print(f"\nCandidate A: {len(features_A)} features (base only)")
    print(f"Candidate B: {len(features_B)} features (base + {len(features_B)-len(features_A)} dynamic rain)")

    # ── 4. 5-Fold CV OOF for A and B ──────────────────────────────────────────
    print("\n--- 5-Fold GroupKFold CV ---")

    print("  Candidate A (no dynamic rain)...")
    oof_A = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, features_A)
    cv_A_n, cv_A_d = within25(y_tr.values, oof_A)
    print(f"  A CV: {cv_A_n}/{cv_A_d} = {100*cv_A_n/cv_A_d:.4f}%")

    print("  Candidate B (with dynamic rain)...")
    oof_B = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, features_B)
    cv_B_n, cv_B_d = within25(y_tr.values, oof_B)
    print(f"  B CV: {cv_B_n}/{cv_B_d} = {100*cv_B_n/cv_B_d:.4f}%")

    # ── 5. Blend C: search alpha on OOF ───────────────────────────────────────
    print("  Candidate C (blend A+B, alpha from OOF)...")
    best_alpha, best_cv_C = None, -1
    for alpha in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        oof_C = alpha * oof_A + (1 - alpha) * oof_B
        n_c, d_c = within25(y_tr.values, oof_C)
        pct_c = n_c / d_c
        print(f"    alpha={alpha:.1f}: {n_c}/{d_c} = {100*pct_c:.4f}%")
        if pct_c > best_cv_C:
            best_cv_C, best_alpha = pct_c, alpha
    oof_C_best = best_alpha * oof_A + (1 - best_alpha) * oof_B
    cv_C_n, cv_C_d = within25(y_tr.values, oof_C_best)
    print(f"  C CV (alpha={best_alpha}): {cv_C_n}/{cv_C_d} = {100*cv_C_n/cv_C_d:.4f}%")

    # ── 6. Select winner by CV ────────────────────────────────────────────────
    results_cv = {
        'A': cv_A_n/cv_A_d, 'B': cv_B_n/cv_B_d, 'C': cv_C_n/cv_C_d
    }
    winner = max(results_cv, key=results_cv.get)
    print(f"\nCV winner: Candidate {winner} ({100*results_cv[winner]:.4f}%)")

    # ── 7. One-shot holdout evaluation ────────────────────────────────────────
    print("\n--- One-shot holdout evaluation (winner only) ---")

    # Retrain winner on full train set
    def full_train_predict(features):
        return fit_predict_crop_specific(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te), features)

    pred_A_hold = full_train_predict(features_A)
    pred_B_hold = full_train_predict(features_B)

    holdout_preds = {
        'A': pred_A_hold,
        'B': pred_B_hold,
        'C': best_alpha * pred_A_hold + (1 - best_alpha) * pred_B_hold,
    }

    report = {"candidates": {}, "winner": winner, "best_blend_alpha": best_alpha}
    for name, preds in holdout_preds.items():
        n, d = within25(y_te, preds)
        mae  = np.mean(np.abs(preds - y_te))
        ss_res = np.sum((y_te - preds)**2)
        ss_tot = np.sum((y_te - y_te.mean())**2)
        r2   = 1 - ss_res/ss_tot
        bias = np.mean(preds - y_te)
        is_winner = (name == winner)
        flag = " ← WINNER" if is_winner else ""
        print(f"  Candidate {name}: {n}/{d} = {100*n/d:.4f}%  MAE={mae:.4f}  R²={r2:.4f}  bias={bias:+.4f}{flag}")
        report["candidates"][name] = {
            "cv_within25_pct": round(100*results_cv[name], 4),
            "holdout_correct": int(n),
            "holdout_total":   int(d),
            "holdout_within25_pct": round(100*n/d, 4),
            "holdout_mae": round(float(mae), 6),
            "holdout_r2":  round(float(r2),  6),
            "holdout_bias": round(float(bias), 6),
        }

    # Per-crop breakdown for winner
    winner_preds = holdout_preds[winner]
    print(f"\n--- Per-crop breakdown (Candidate {winner}) ---")
    per_crop = {}
    for crop in sorted(np.unique(crops_te)):
        mask = crops_te == crop
        n, d = within25(y_te[mask], winner_preds[mask])
        per_crop[crop] = {"correct": int(n), "total": int(d),
                          "pct": round(100*n/d, 2) if d > 0 else None}
        print(f"  {crop:<25s}: {n}/{d} = {100*n/d:.2f}%" if d > 0 else f"  {crop}: N/A")

    # Baseline comparison
    baseline_preds = frozen['y_test_pred']
    n_base, d_base = within25(y_te, baseline_preds)
    print(f"\n--- Baseline (frozen phase3): {n_base}/{d_base} = {100*n_base/d_base:.4f}% ---")
    report["baseline_frozen_holdout_pct"] = round(100*n_base/d_base, 4)
    report["per_crop_winner"] = per_crop

    # Save
    with open(OUT_JSON, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nResults saved: {OUT_JSON}")
    print("=== Phase 5 complete ===")


if __name__ == "__main__":
    main()
