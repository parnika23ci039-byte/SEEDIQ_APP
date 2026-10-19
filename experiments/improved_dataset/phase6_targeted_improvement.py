"""
Phase 6: Targeted Yield Accuracy Improvement
=============================================
Benchmark: Candidate C (Phase 5) — 80% HistGBR base + 20% HistGBR+dynamic-rain,
           alpha=0.8, holdout 733/1088 = 67.37% within-25%.

Objective: improve accuracy, especially Soyabean (52.17%), Pigeonpea (54.39%),
Chickpea (56.90%), without data leakage.

Three candidate families:
  F1 — crop × district target-encoding features (computed within CV folds only)
  F2 — crop-specific residual shrinkage learned from training-fold OOF
  F3 — specialist models (Ridge / RandomForest) for the 3 weak crops

Rules:
  - Frozen holdout split identical to Phase 5 (GroupShuffleSplit rs=42, test=0.2)
  - GroupKFold(5) on train groups for CV / OOF
  - No holdout information used for tuning or feature design
  - Candidate C script/results are preserved; this script only reads them.
"""

import json, warnings, sys
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
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
PHASE5_JSON  = RES_DIR / "phase5_dynamic_rainfall_results.json"
OUT_JSON     = RES_DIR / "phase6_targeted_improvement_results.json"
OUT_DIAG     = RES_DIR / "phase6_error_diagnosis.json"

# ── district → subdivision mapping (identical to Phase 5) ─────────────────────
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

WEAK_CROPS = ['Soyabean', 'Pigeonpea', 'Chickpea']

# ── metrics ───────────────────────────────────────────────────────────────────
def within25(y_true, y_pred):
    rel = np.abs(y_pred - y_true) / np.maximum(np.abs(y_true), 1e-12)
    return int((rel <= 0.25).sum()), int(len(y_true))

def metrics_dict(y_true, y_pred):
    n, d = within25(y_true, y_pred)
    mae = float(np.mean(np.abs(y_pred - y_true)))
    ss_res = float(np.sum((y_true - y_pred)**2))
    ss_tot = float(np.sum((y_true - y_true.mean())**2))
    r2 = 1 - ss_res/ss_tot if ss_tot > 0 else float('nan')
    bias = float(np.mean(y_pred - y_true))
    return {"correct": n, "total": d, "pct": round(100*n/d, 4) if d else None,
            "mae": round(mae, 6), "r2": round(r2, 6), "bias": round(bias, 6)}

# ── data loading (identical to Phase 5) ───────────────────────────────────────
def load_base():
    df = pd.read_csv(YIELD_CSV)
    with open(MANIFEST_JSON) as f:
        manifest = json.load(f)
    base_features = [c for c in manifest["feature_columns"] if c in df.columns]
    return df, base_features

def add_dynamic_rainfall(df):
    rain = pd.read_csv(RAIN_CSV)
    rain.columns = [c.strip() for c in rain.columns]
    col_map = {
        'SUBDIVISION': 'SUBDIVISION', 'YEAR': 'YEAR',
        'ANNUAL': 'dyn_rain_annual', 'Jun-Sep': 'dyn_rain_kharif',
        'Oct-Dec': 'dyn_rain_rabi', 'Jan-Feb': 'dyn_rain_winter',
        'Mar-May': 'dyn_rain_summer',
    }
    rain = rain[list(col_map.keys())].rename(columns=col_map)
    rain['SUBDIVISION'] = rain['SUBDIVISION'].str.strip().str.upper()
    normals = rain.groupby('SUBDIVISION')[['dyn_rain_annual','dyn_rain_kharif']].mean()
    normals.columns = ['normal_annual', 'normal_kharif']
    df = df.copy()
    df['SUBDIVISION'] = df['District'].map(DISTRICT_TO_SUBDIVISION).fillna(DEFAULT_SUB).str.upper()
    max_rain_year = int(rain['YEAR'].max())
    df['_join_year'] = df['Year'].clip(upper=max_rain_year)
    merged = df.merge(rain, left_on=['SUBDIVISION', '_join_year'],
                      right_on=['SUBDIVISION', 'YEAR'], how='left')
    merged = merged.merge(normals, on='SUBDIVISION', how='left')
    merged['dyn_rain_anomaly_pct']  = (merged['dyn_rain_annual']  - merged['normal_annual'])  / merged['normal_annual'].replace(0, np.nan)
    merged['dyn_kharif_anomaly_pct']= (merged['dyn_rain_kharif'] - merged['normal_kharif']) / merged['normal_kharif'].replace(0, np.nan)
    return merged

# ── crop-specific HistGBR (identical to Phase 5) ──────────────────────────────
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
        X_f, y_f, crops_f = X_tr.iloc[fold_tr_idx], y_tr.iloc[fold_tr_idx], crops_tr.iloc[fold_tr_idx]
        X_v, crops_v = X_tr.iloc[fold_val_idx], crops_tr.iloc[fold_val_idx]
        oof[fold_val_idx] = fit_predict_crop_specific(X_f, y_f, crops_f, X_v, crops_v,
                                                     features, model_params, model_cls)
    return oof

# ── target-encoding feature builder (leakage-free, within-fold) ───────────────
def build_target_encoding_features(df_tr_full, df_val, y_tr_full, crops_tr_full):
    """
    Compute crop-district mean yield from df_tr_full (training portion of a fold)
    and map to df_val. Falls back to crop-mean then global-mean for unseen pairs.
    Returns a DataFrame with one column 'cd_mean_yield' aligned to df_val index.
    """
    tmp = pd.DataFrame({
        'Crop': crops_tr_full.values,
        'District': df_tr_full['District'].values,
        'y': y_tr_full.values,
    })
    cd_mean = tmp.groupby(['Crop', 'District'])['y'].mean().to_dict()
    c_mean  = tmp.groupby('Crop')['y'].mean().to_dict()
    global_mean = tmp['y'].mean()

    out = np.zeros(len(df_val))
    crops_v = df_val['Crop'].values if 'Crop' in df_val.columns else None
    # df_val may be a DataFrame subset; use its Crop
    if crops_v is None:
        crops_v = np.array([None]*len(df_val))
    dists_v = df_val['District'].values
    for i, (c, d) in enumerate(zip(crops_v, dists_v)):
        if (c, d) in cd_mean:
            out[i] = cd_mean[(c, d)]
        elif c in c_mean:
            out[i] = c_mean[c]
        else:
            out[i] = global_mean
    return out

# ── CV OOF with target-encoding feature (F1) ──────────────────────────────────
def grouped_cv_oof_with_te(X_tr, y_tr, groups_tr, crops_tr, base_features,
                           model_params=None, model_cls=HistGradientBoostingRegressor):
    """Each fold: build cd_mean_yield from fold-train, add as feature, train & predict."""
    oof = np.zeros(len(y_tr))
    gkf = GroupKFold(n_splits=5)
    for fold_tr_idx, fold_val_idx in gkf.split(X_tr, y_tr, groups_tr):
        X_f = X_tr.iloc[fold_tr_idx].copy()
        y_f = y_tr.iloc[fold_tr_idx]
        crops_f = crops_tr.iloc[fold_tr_idx]
        X_v = X_tr.iloc[fold_val_idx].copy()
        crops_v = crops_tr.iloc[fold_val_idx]

        te_f = build_target_encoding_features(X_f, X_f, y_f, crops_f)
        te_v = build_target_encoding_features(X_f, X_v, y_f, crops_f)
        X_f = X_f.assign(cd_mean_yield=te_f)
        X_v = X_v.assign(cd_mean_yield=te_v)
        feats = base_features + ['cd_mean_yield']
        oof[fold_val_idx] = fit_predict_crop_specific(X_f, y_f, crops_f, X_v, crops_v,
                                                     feats, model_params, model_cls)
    return oof

def full_train_predict_with_te(df_tr, y_tr, crops_tr, df_te, crops_te, base_features,
                               model_params=None, model_cls=HistGradientBoostingRegressor):
    te_tr = build_target_encoding_features(df_tr, df_tr, y_tr, crops_tr)
    te_te = build_target_encoding_features(df_tr, df_te, y_tr, crops_tr)
    X_tr = df_tr.assign(cd_mean_yield=te_tr)
    X_te = df_te.assign(cd_mean_yield=te_te)
    feats = base_features + ['cd_mean_yield']
    return fit_predict_crop_specific(X_tr, y_tr, crops_tr, X_te, crops_te,
                                    feats, model_params, model_cls)

# ── residual shrinkage (F2) ───────────────────────────────────────────────────
def learn_crop_shrinkage(oof_pred, y_true, crops, shrink_grid=None):
    """
    For each crop, find a multiplicative shrinkage factor s in [0.5, 1.5] that
    maximises within-25% on OOF predictions. Returns dict crop->s.
    Only learned from training OOF — no holdout data.
    """
    if shrink_grid is None:
        shrink_grid = [0.7, 0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.3]
    shrink = {}
    for crop in np.unique(crops):
        mask = crops == crop
        if mask.sum() < 10:
            shrink[crop] = 1.0
            continue
        best_s, best_n = 1.0, -1
        for s in shrink_grid:
            n, _ = within25(y_true[mask], oof_pred[mask] * s)
            if n > best_n:
                best_n, best_s = n, s
        shrink[crop] = best_s
    return shrink

def apply_crop_shrinkage(preds, crops, shrink):
    out = preds.copy()
    for crop, s in shrink.items():
        out[crops == crop] *= s
    return out

def learn_crop_variance_correction(oof_pred, y_true, crops):
    """
    Focused F2 refinement: per-crop linear variance-stretch correction.
    Diagnosis showed the model compresses the yield range (low yields overpredicted,
    high yields underpredicted). Correct by: pred_corr = crop_mean + k*(pred - crop_mean)
    where k = std(y_true)/std(oof_pred) per crop, learned from OOF only.
    Returns dict crop -> (mean_pred, k).
    """
    corr = {}
    for crop in np.unique(crops):
        mask = crops == crop
        if mask.sum() < 10:
            corr[crop] = (0.0, 1.0)
            continue
        p = oof_pred[mask]
        y = y_true[mask]
        mean_p = float(np.mean(p))
        std_p = float(np.std(p))
        std_y = float(np.std(y))
        k = std_y / std_p if std_p > 1e-9 else 1.0
        # clamp k to avoid extreme corrections
        k = max(0.7, min(1.5, k))
        corr[crop] = (mean_p, k)
    return corr

def apply_crop_variance_correction(preds, crops, corr):
    out = preds.copy().astype(float)
    for crop, (mean_p, k) in corr.items():
        m = crops == crop
        out[m] = mean_p + k * (out[m] - mean_p)
    return out

# ── specialist model per weak crop (F3) ───────────────────────────────────────
SPECIALIST_MODELS = {
    'ridge': (Ridge, dict(alpha=1.0, random_state=42)),
    'rf':    (RandomForestRegressor, dict(n_estimators=300, max_depth=8,
                                          min_samples_leaf=3, random_state=42, n_jobs=-1)),
}

def specialist_cv_oof_for_crop(X_tr, y_tr, groups_tr, crops_tr, crop, features,
                               model_cls, model_params):
    """Run 5-fold GroupKFold OOF for a single crop using a specialist model."""
    mask = crops_tr == crop
    if mask.sum() < MIN_CROP_ROWS:
        return None
    X_c = X_tr[mask].reset_index(drop=True)
    y_c = y_tr[mask].reset_index(drop=True)
    g_c = groups_tr[mask].reset_index(drop=True)
    oof = np.zeros(len(y_c))
    gkf = GroupKFold(n_splits=5)
    # if not enough groups for 5 folds, reduce
    n_groups = g_c.nunique()
    n_splits = min(5, n_groups)
    if n_splits < 2:
        return None
    gkf = GroupKFold(n_splits=n_splits)
    try:
        for fold_tr_idx, fold_val_idx in gkf.split(X_c, y_c, g_c):
            m = model_cls(**model_params)
            m.fit(X_c.iloc[fold_tr_idx][features], y_c.iloc[fold_tr_idx])
            oof[fold_val_idx] = m.predict(X_c.iloc[fold_val_idx][features])
    except Exception:
        return None
    return oof, mask.values

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("=== Phase 6: Targeted Yield Accuracy Improvement ===\n")

    # 1. Load data (identical to Phase 5)
    df, base_features = load_base()
    df = add_dynamic_rainfall(df)
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

    # verify holdout
    frozen = np.load(FROZEN_NPZ, allow_pickle=True)
    assert len(te_idx) == len(frozen['y_test_true'])
    assert np.allclose(y_te, frozen['y_test_true'], atol=1e-6)
    print(f"Holdout verified: {len(te_idx)} rows match frozen baseline ✓")
    print(f"Split: train={len(df_tr)}, test={len(df_te)}")

    features_A = base_features
    features_B = base_features + [f for f in DYN_FEATURES if f not in base_features]

    # ── 2. Reproduce Candidate C OOF + holdout ───────────────────────────────
    print("\n--- Reproducing Candidate C (Phase 5) ---")
    oof_A = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, features_A)
    oof_B = grouped_cv_oof(df_tr, y_tr, groups_tr, crops_tr, features_B)
    best_alpha = 0.8  # from Phase 5 saved result
    oof_C = best_alpha * oof_A + (1 - best_alpha) * oof_B
    cv_C_n, cv_C_d = within25(y_tr.values, oof_C)
    print(f"  Reproduced C CV: {cv_C_n}/{cv_C_d} = {100*cv_C_n/cv_C_d:.4f}% "
          f"(Phase 5 reported: 69.4463%)")

    pred_A_hold = fit_predict_crop_specific(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te), features_A)
    pred_B_hold = fit_predict_crop_specific(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te), features_B)
    pred_C_hold = best_alpha * pred_A_hold + (1 - best_alpha) * pred_B_hold
    hC = metrics_dict(y_te, pred_C_hold)
    print(f"  Reproduced C holdout: {hC['correct']}/{hC['total']} = {hC['pct']:.4f}% "
          f"(Phase 5 reported: 733/1088 = 67.3713%)")
    assert hC['correct'] == 733 and hC['total'] == 1088, "Candidate C reproduction mismatch!"

    # ── 3. Error diagnosis for weak crops (on training OOF) ──────────────────
    print("\n--- Error Diagnosis (Candidate C OOF on train) ---")
    diagnosis = {}
    for crop in WEAK_CROPS:
        mask = (crops_tr == crop).values
        y_c = y_tr.values[mask]
        oof_c = oof_C[mask]
        res = oof_c - y_c
        rel_err = np.abs(res) / np.maximum(np.abs(y_c), 1e-12)
        within = rel_err <= 0.25
        n_correct = int(within.sum())
        n_total = len(y_c)
        diag = {
            "n_train_oof": n_total,
            "oof_correct": n_correct,
            "oof_pct": round(100*n_correct/n_total, 2) if n_total else None,
            "y_true_min": round(float(y_c.min()), 4),
            "y_true_max": round(float(y_c.max()), 4),
            "y_true_mean": round(float(y_c.mean()), 4),
            "y_true_median": round(float(np.median(y_c)), 4),
            "residual_mean": round(float(res.mean()), 4),
            "residual_median": round(float(np.median(res)), 4),
            "residual_std": round(float(res.std()), 4),
            "signed_bias": round(float(res.mean()), 4),
            "overpred_pct": round(100*float((res > 0).mean()), 2),
            "rel_err_mean": round(float(rel_err.mean()), 4),
            "rel_err_median": round(float(np.median(rel_err)), 4),
            # low-yield (< median) overprediction check
            "low_yield_mask_pct": round(100*float((y_c <= np.median(y_c)).mean()), 1),
            "low_yield_overpred_pct": round(100*float((res[y_c <= np.median(y_c)] > 0).mean()), 1)
                                              if (y_c <= np.median(y_c)).sum() > 0 else None,
            "n_districts": int(df_tr[mask]['District'].nunique()),
            "n_years": int(df_tr[mask]['Year'].nunique()),
            "n_groups": int(df_tr[mask]['group_key'].nunique()),
        }
        diagnosis[crop] = diag
        print(f"\n  {crop}:")
        print(f"    OOF: {n_correct}/{n_total} = {diag['oof_pct']}%")
        print(f"    y_true: min={diag['y_true_min']}, max={diag['y_true_max']}, "
              f"mean={diag['y_true_mean']}, median={diag['y_true_median']}")
        print(f"    signed bias (pred-true): {diag['signed_bias']:+.4f}  "
              f"(overpred {diag['overpred_pct']}%)")
        print(f"    residual std: {diag['residual_std']}")
        print(f"    low-yield (≤median) overpred: {diag['low_yield_overpred_pct']}%")
        print(f"    districts={diag['n_districts']}, years={diag['n_years']}, "
              f"groups={diag['n_groups']}")

    with open(OUT_DIAG, 'w') as f:
        json.dump(diagnosis, f, indent=2)

    # ── 4. Candidate Family F1: crop×district target encoding ────────────────
    print("\n--- Family F1: crop×district target encoding ---")
    oof_F1_A = grouped_cv_oof_with_te(df_tr, y_tr, groups_tr, crops_tr, features_A)
    oof_F1_B = grouped_cv_oof_with_te(df_tr, y_tr, groups_tr, crops_tr, features_B)
    # blend with same alpha
    oof_F1 = best_alpha * oof_F1_A + (1 - best_alpha) * oof_F1_B
    f1_n, f1_d = within25(y_tr.values, oof_F1)
    print(f"  F1 CV: {f1_n}/{f1_d} = {100*f1_n/f1_d:.4f}%  (C: {100*cv_C_n/cv_C_d:.4f}%)")

    # ── 5. Candidate Family F2: crop-specific residual shrinkage ──────────────
    print("\n--- Family F2: crop-specific shrinkage (learned from OOF) ---")
    shrink_C = learn_crop_shrinkage(oof_C, y_tr.values, crops_tr.values)
    oof_F2 = apply_crop_shrinkage(oof_C, crops_tr.values, shrink_C)
    f2_n, f2_d = within25(y_tr.values, oof_F2)
    print(f"  F2 CV: {f2_n}/{f2_d} = {100*f2_n/f2_d:.4f}%  (C: {100*cv_C_n/cv_C_d:.4f}%)")
    print("  Shrinkage factors (non-1.0 only):")
    for c, s in shrink_C.items():
        if abs(s - 1.0) > 1e-9:
            print(f"    {c}: {s}")

    # ── F2-refined: variance-stretch correction (focused fix for range compression) ──
    print("\n--- F2-refined: per-crop variance-stretch correction ---")
    varcorr_C = learn_crop_variance_correction(oof_C, y_tr.values, crops_tr.values)
    oof_F2v = apply_crop_variance_correction(oof_C, crops_tr.values, varcorr_C)
    f2v_n, f2v_d = within25(y_tr.values, oof_F2v)
    print(f"  F2v CV: {f2v_n}/{f2v_d} = {100*f2v_n/f2v_d:.4f}%  (C: {100*cv_C_n/cv_C_d:.4f}%)")
    print("  Variance correction k factors (k!=1 only):")
    for c, (mp, k) in varcorr_C.items():
        if abs(k - 1.0) > 1e-9:
            print(f"    {c}: k={k:.4f}, mean_pred={mp:.4f}")

    # ── 6. Candidate Family F3: specialist models for weak crops ─────────────
    print("\n--- Family F3: specialist models for weak crops (CV OOF per crop) ---")
    # Compare each specialist against Candidate C OOF on the same crop rows
    specialist_winners = {}  # crop -> (model_name, oof_specialist)
    for crop in WEAK_CROPS:
        mask = (crops_tr == crop).values
        y_c = y_tr.values[mask]
        oof_C_c = oof_C[mask]
        n_C, d_C = within25(y_c, oof_C_c)
        print(f"  {crop}: C OOF = {n_C}/{d_C} = {100*n_C/d_C:.2f}%")
        best_name, best_oof, best_n = 'C', oof_C_c, n_C
        for mname, (mcls, mparams) in SPECIALIST_MODELS.items():
            res = specialist_cv_oof_for_crop(df_tr, y_tr, groups_tr, crops_tr, crop,
                                             features_B, mcls, mparams)
            if res is None:
                print(f"    {mname}: skipped (insufficient data)")
                continue
            oof_spec, _ = res
            n_s, d_s = within25(y_c, oof_spec)
            print(f"    {mname}: {n_s}/{d_s} = {100*n_s/d_s:.2f}%")
            if n_s > best_n:
                best_name, best_oof, best_n = mname, oof_spec, n_s
        specialist_winners[crop] = best_name
        print(f"    → best for {crop}: {best_name} ({best_n}/{d_C})")

    # Build F3 OOF: replace weak-crop OOF with specialist where better
    oof_F3 = oof_C.copy()
    for crop in WEAK_CROPS:
        if specialist_winners[crop] == 'C':
            continue
        mcls, mparams = SPECIALIST_MODELS[specialist_winners[crop]]
        res = specialist_cv_oof_for_crop(df_tr, y_tr, groups_tr, crops_tr, crop,
                                         features_B, mcls, mparams)
        if res is not None:
            oof_spec, mask = res
            oof_F3[mask] = oof_spec
    f3_n, f3_d = within25(y_tr.values, oof_F3)
    print(f"  F3 CV (mixed): {f3_n}/{f3_d} = {100*f3_n/f3_d:.4f}%  "
          f"(C: {100*cv_C_n/cv_C_d:.4f}%)")

    # ── 7. Combined candidate: F1 + F2 shrinkage applied ─────────────────────
    print("\n--- Combined: F1 features + F2 shrinkage ---")
    shrink_F1 = learn_crop_shrinkage(oof_F1, y_tr.values, crops_tr.values)
    oof_F1F2 = apply_crop_shrinkage(oof_F1, crops_tr.values, shrink_F1)
    f1f2_n, f1f2_d = within25(y_tr.values, oof_F1F2)
    print(f"  F1+F2 CV: {f1f2_n}/{f1f2_d} = {100*f1f2_n/f1f2_d:.4f}%")

    # ── 8. Select best by CV ─────────────────────────────────────────────────
    cv_scores = {
        'C': cv_C_n / cv_C_d,
        'F1': f1_n / f1_d,
        'F2': f2_n / f2_d,
        'F2v': f2v_n / f2v_d,
        'F3': f3_n / f3_d,
        'F1+F2': f1f2_n / f1f2_d,
    }
    print("\n--- CV Summary ---")
    for k, v in sorted(cv_scores.items(), key=lambda x: -x[1]):
        print(f"  {k:8s}: {100*v:.4f}%")

    best_name = max(cv_scores, key=cv_scores.get)
    print(f"\nCV winner: {best_name} ({100*cv_scores[best_name]:.4f}%)")

    # ── 9. Holdout evaluation for all candidates ─────────────────────────────
    print("\n--- Holdout evaluation (all candidates) ---")
    holdout = {}

    # Candidate C (already computed)
    holdout['C'] = metrics_dict(y_te, pred_C_hold)

    # F1: target encoding
    pred_F1_A = full_train_predict_with_te(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te), features_A)
    pred_F1_B = full_train_predict_with_te(df_tr, y_tr, crops_tr, df_te, pd.Series(crops_te), features_B)
    pred_F1 = best_alpha * pred_F1_A + (1 - best_alpha) * pred_F1_B
    holdout['F1'] = metrics_dict(y_te, pred_F1)

    # F2: shrinkage on C (use shrink learned from C OOF)
    pred_F2 = apply_crop_shrinkage(pred_C_hold, crops_te, shrink_C)
    holdout['F2'] = metrics_dict(y_te, pred_F2)

    # F2v: variance-stretch correction on C
    pred_F2v = apply_crop_variance_correction(pred_C_hold, crops_te, varcorr_C)
    holdout['F2v'] = metrics_dict(y_te, pred_F2v)

    # F3: specialist for weak crops
    pred_F3 = pred_C_hold.copy()
    for crop in WEAK_CROPS:
        if specialist_winners[crop] == 'C':
            continue
        mcls, mparams = SPECIALIST_MODELS[specialist_winners[crop]]
        mask_tr = (crops_tr == crop).values
        mask_te = crops_te == crop
        if mask_tr.sum() < MIN_CROP_ROWS or mask_te.sum() == 0:
            continue
        m = mcls(**mparams)
        m.fit(df_tr[mask_tr][features_B], y_tr[mask_tr])
        pred_F3[mask_te] = m.predict(df_te[mask_te][features_B])
    holdout['F3'] = metrics_dict(y_te, pred_F3)

    # F1+F2
    pred_F1F2 = apply_crop_shrinkage(pred_F1, crops_te, shrink_F1)
    holdout['F1+F2'] = metrics_dict(y_te, pred_F1F2)

    for k, v in holdout.items():
        flag = " ← CV winner" if k == best_name else ""
        print(f"  {k:8s}: {v['correct']}/{v['total']} = {v['pct']:.4f}%  "
              f"MAE={v['mae']:.4f}  R²={v['r2']:.4f}  bias={v['bias']:+.4f}{flag}")

    # ── 10. Per-crop breakdown for C and the best new candidate ──────────────
    best_holdout_name = max(holdout, key=lambda k: holdout[k]['pct'] if holdout[k]['pct'] else -1)
    print(f"\nBest holdout candidate: {best_holdout_name} "
          f"({holdout[best_holdout_name]['pct']}%)")

    per_crop = {}
    for cand_name in ['C', best_holdout_name]:
        preds = {'C': pred_C_hold, 'F1': pred_F1, 'F2': pred_F2, 'F2v': pred_F2v,
                 'F3': pred_F3, 'F1+F2': pred_F1F2}[cand_name]
        per_crop[cand_name] = {}
        for crop in sorted(np.unique(crops_te)):
            mask = crops_te == crop
            n, d = within25(y_te[mask], preds[mask])
            per_crop[cand_name][crop] = {"correct": n, "total": d,
                                          "pct": round(100*n/d, 2) if d else None}

    # ── 11. Save results ─────────────────────────────────────────────────────
    report = {
        "benchmark_phase5_c": {
            "cv_pct": round(100*cv_C_n/cv_C_d, 4),
            "holdout": holdout['C'],
        },
        "cv_scores": {k: round(100*v, 4) for k, v in cv_scores.items()},
        "cv_winner": best_name,
        "holdout": holdout,
        "holdout_best": best_holdout_name,
        "shrinkage_factors_C": {k: v for k, v in shrink_C.items() if abs(v-1) > 1e-9},
        "shrinkage_factors_F1": {k: v for k, v in shrink_F1.items() if abs(v-1) > 1e-9},
        "variance_correction_k": {k: round(v[1], 4) for k, v in varcorr_C.items() if abs(v[1]-1) > 1e-9},
        "specialist_winners": specialist_winners,
        "per_crop": per_crop,
        "pp_gain_vs_C": {
            k: round(holdout[k]['pct'] - holdout['C']['pct'], 4)
            for k in holdout if k != 'C'
        },
    }
    with open(OUT_JSON, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nResults saved: {OUT_JSON}")
    print("=== Phase 6 complete ===")

if __name__ == "__main__":
    main()
