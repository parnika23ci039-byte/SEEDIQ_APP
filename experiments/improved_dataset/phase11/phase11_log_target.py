"""
Phase 11 — Log-Target Transformation for Range Compression
============================================================

F3 baseline (Phase 6/10): 69.54% within ±25% on grouped OOF.
Dominant failure mode (Phase 10): range compression from HistGBR absolute_error
loss on the right-skewed yield distribution. Low yields (0-0.5 t/ha) are 70%
overpredicted; high yields (5+ t/ha) are underpredicted.

Phase 10 already tested post-hoc calibration (variance stretch, isotonic,
linear recalibration) and squared_error loss — all failed. Those approaches
either operated on already-compressed OOF predictions or overfit per-crop
samples.

THIS HYPOTHESIS (ONE TEST):
  Predict log1p(yield) instead of yield, then expm1 the predictions.
  Rationale: yield is right-skewed; in log space it is approximately symmetric.
  absolute_error (median) in log space maps to a geometric-median-like estimate
  in yield space, which should preserve the prediction range better than
  absolute_error on raw yield. The transformation is row-wise (no parameters
  to fit), so there is no leakage and no per-crop overfitting.

  All model fitting happens inside each GroupKFold training fold. Baseline
  (F3) and candidate (F3-log) use identical folds and identical rows.
"""

import json, sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.model_selection import GroupShuffleSplit, GroupKFold
warnings.filterwarnings("ignore")

# Reuse F3 building blocks from Phase 10 (guarantees exact baseline reproduction)
PHASE10 = Path(__file__).resolve().parents[1] / "phase10"
sys.path.insert(0, str(PHASE10))
from phase10_error_analysis import (          # noqa: E402
    load_base, add_dynamic_rainfall, within_pct, metrics_dict,
    fit_predict_crop_specific,
    HISTGBR_PARAMS, RF_PARAMS, MIN_CROP_ROWS, BLEND_ALPHA,
    DYN_FEATURES,
)

# ── paths ──────────────────────────────────────────────────────────────────────
PHASE11 = Path(__file__).resolve().parent
RES_DIR = PHASE11 / "results"
RES_DIR.mkdir(parents=True, exist_ok=True)
OUT_OOF_CSV  = RES_DIR / "phase11_oof_predictions.csv"
OUT_RESULTS  = RES_DIR / "phase11_results.json"

# ── log-target variant of F3 ──────────────────────────────────────────────────
def f3_oof_log(df_tr, y_tr, groups_tr, crops_tr, feats_A, feats_B):
    """
    F3 with log1p(yield) target. Predictions are expm1'd back to yield space.
    Identical structure to f3_oof except the target transform.
    """
    y_log = np.log1p(y_tr.values)
    oof_A = np.zeros(len(y_tr))
    oof_B = np.zeros(len(y_tr))
    gkf = GroupKFold(n_splits=5)
    for ftr, fva in gkf.split(df_tr, y_log, groups_tr):
        Xf, yf, cf = df_tr.iloc[ftr], y_log[ftr], crops_tr.iloc[ftr]
        Xv, cv = df_tr.iloc[fva], crops_tr.iloc[fva]
        oof_A[fva] = fit_predict_crop_specific(Xf, yf, cf, Xv, cv, feats_A)
        oof_B[fva] = fit_predict_crop_specific(Xf, yf, cf, Xv, cv, feats_B)
    # blend in log space, then exponentiate
    oof_C_log = BLEND_ALPHA * oof_A + (1 - BLEND_ALPHA) * oof_B
    oof_C = np.expm1(oof_C_log)
    # Chickpea RF specialist (also in log space)
    for crop in ['Chickpea']:
        mask = (crops_tr == crop).values
        if mask.sum() < MIN_CROP_ROWS:
            continue
        Xc = df_tr[mask].reset_index(drop=True)
        yc = y_log[mask]
        gc = groups_tr[mask].reset_index(drop=True)
        oof_spec = np.zeros(mask.sum())
        n_splits = min(5, gc.nunique())
        if n_splits < 2:
            continue
        for ftr, fva in GroupKFold(n_splits=n_splits).split(Xc, yc, gc):
            m = RandomForestRegressor(**RF_PARAMS)
            m.fit(Xc.iloc[ftr][feats_B], yc[ftr])
            oof_spec[fva] = m.predict(Xc.iloc[fva][feats_B])
        oof_C[mask] = np.expm1(oof_spec)
    return oof_C


def main():
    print("=== Phase 11: Log-Target Transformation Experiment ===\n")

    # ── data (identical to Phase 10) ──
    df, base_features = load_base()
    df = add_dynamic_rainfall(df)
    df['group_key'] = df['District'].astype(str) + '|' + df['Year'].astype(str)
    groups = df['group_key'].values
    y = df['yield_per_hectare'].values

    # Frozen split (identical to Phase 6/8/10)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr_idx, te_idx = next(gss.split(df, y, groups))
    df_tr = df.iloc[tr_idx].reset_index(drop=True)
    y_tr = df_tr['yield_per_hectare']
    groups_tr = df_tr['group_key']
    crops_tr = df_tr['Crop']

    feats_A = base_features
    feats_B = base_features + [f for f in DYN_FEATURES if f not in base_features]

    print(f"Train rows: {len(df_tr)}")
    print(f"Features A (base): {len(feats_A)}")
    print(f"Features B (base+rain): {len(feats_B)}\n")

    # ── Baseline F3 OOF (reproduce Phase 10) ──
    print("Computing F3 baseline OOF (GroupKFold=5 on District|Year)...")
    from phase10_error_analysis import f3_oof
    oof_base = f3_oof(df_tr, y_tr, groups_tr, crops_tr, feats_A, feats_B)
    m_base = metrics_dict(y_tr.values, oof_base)
    print(f"  F3 baseline: {m_base['correct_25']}/{m_base['total']} = {m_base['pct_25']}% "
          f"(±10%={m_base['pct_10']}%, MAE={m_base['mae']:.4f}, R²={m_base['r2']:.4f})\n")

    # ── Candidate: F3 with log1p target ──
    print("Computing F3-log OOF (same folds, log1p target)...")
    oof_log = f3_oof_log(df_tr, y_tr, groups_tr, crops_tr, feats_A, feats_B)
    m_log = metrics_dict(y_tr.values, oof_log)
    print(f"  F3-log:     {m_log['correct_25']}/{m_log['total']} = {m_log['pct_25']}% "
          f"(±10%={m_log['pct_10']}%, MAE={m_log['mae']:.4f}, R²={m_log['r2']:.4f})\n")

    delta = m_log['pct_25'] - m_base['pct_25']
    print(f"  Δ within-25%: {delta:+.4f} pp")
    print(f"  Δ within-10%: {m_log['pct_10'] - m_base['pct_10']:+.4f} pp")
    print(f"  Δ MAE:        {m_log['mae'] - m_base['mae']:+.4f} t/ha")
    print(f"  Δ R²:         {m_log['r2'] - m_base['r2']:+.4f}\n")

    # ── Range compression check ──
    print("Range compression (yield_std / pred_std, lower=better):")
    yv = y_tr.values
    for crop in ['Sugarcane', 'Rice', 'Maize', 'Cotton', 'Groundnut']:
        mask = (crops_tr == crop).values
        if mask.sum() < 20:
            continue
        yc = yv[mask]
        r_base = yc.std() / oof_base[mask].std() if oof_base[mask].std() > 0 else float('inf')
        r_log = yc.std() / oof_log[mask].std() if oof_log[mask].std() > 0 else float('inf')
        print(f"  {crop:12s}: base={r_base:.3f}  log={r_log:.3f}")
    print()

    # ── Subgroup breakdown: low yields, drought years, weak crops ──
    print("Subgroup analysis (within-25%):")
    print(f"{'subgroup':30s} {'n':>5s} {'base':>8s} {'log':>8s} {'delta':>8s}")
    subgroups = {}
    # low yield
    mask_low = yv < 0.5
    subgroups['yield < 0.5 t/ha'] = mask_low
    # drought years
    subgroups['year 2003'] = (df_tr['Year'] == 2003).values
    subgroups['year 2016'] = (df_tr['Year'] == 2016).values
    # weak crops
    for c in ['Sesamum', 'Pigeonpea', 'Minor Pulses']:
        subgroups[f'crop={c}'] = (crops_tr == c).values
    # best crops
    for c in ['Sugarcane', 'Rice']:
        subgroups[f'crop={c}'] = (crops_tr == c).values

    sub_results = {}
    for name, mask in subgroups.items():
        n = int(mask.sum())
        if n < 10:
            continue
        nb, _ = within_pct(yv[mask], oof_base[mask], 0.25)
        nl, _ = within_pct(yv[mask], oof_log[mask], 0.25)
        pb = 100 * nb / n
        pl = 100 * nl / n
        sub_results[name] = {'n': n, 'base_pct_25': round(pb, 2),
                             'log_pct_25': round(pl, 2),
                             'delta_pp': round(pl - pb, 2)}
        print(f"  {name:30s} {n:5d} {pb:7.1f}% {pl:7.1f}% {pl-pb:+7.1f}pp")
    print()

    # ── Fold-level variability ──
    print("Per-fold within-25%:")
    gkf = GroupKFold(n_splits=5)
    fold_base, fold_log = [], []
    for i, (_, fva) in enumerate(gkf.split(df_tr, y_tr, groups_tr), 1):
        nb, _ = within_pct(yv[fva], oof_base[fva], 0.25)
        nl, _ = within_pct(yv[fva], oof_log[fva], 0.25)
        pb, pl = 100*nb/len(fva), 100*nl/len(fva)
        fold_base.append(pb); fold_log.append(pl)
        print(f"  Fold {i}: base={pb:.1f}%  log={pl:.1f}%  Δ={pl-pb:+.1f}pp")
    print(f"  Base mean={np.mean(fold_base):.2f}% std={np.std(fold_base):.2f}pp")
    print(f"  Log  mean={np.mean(fold_log):.2f}% std={np.std(fold_log):.2f}pp\n")

    # ── Decision ──
    # Acceptance: improve over 69.54% by meaningful margin, consistent across
    # folds, no unacceptable regression in other metrics.
    meaningful = 1.0  # pp threshold for "meaningful"
    consistent = bool((np.array(fold_log) > np.array(fold_base)).sum() >= 4)
    no_regression = bool(m_log['mae'] <= m_base['mae'] * 1.05 and
                         m_log['r2'] >= m_base['r2'] - 0.01)
    if delta >= meaningful and consistent and no_regression:
        decision = "REPLACE_F3_WITH_F3_LOG"
    else:
        decision = "RETAIN_F3"

    print(f"DECISION: {decision}")
    print(f"  Δ±25% = {delta:+.2f}pp (threshold ≥{meaningful}pp)")
    print(f"  Consistent across folds: {consistent} ({(np.array(fold_log)>np.array(fold_base)).sum()}/5)")
    print(f"  No unacceptable regression: {no_regression}")
    print()

    # ── Save OOF predictions ──
    oof_df = df_tr[['District', 'Year', 'Crop', 'yield_per_hectare']].copy()
    oof_df['oof_pred_base'] = oof_base
    oof_df['oof_pred_log'] = oof_log
    oof_df['residual_base'] = oof_base - oof_df['yield_per_hectare']
    oof_df['residual_log'] = oof_log - oof_df['yield_per_hectare']
    oof_df.to_csv(OUT_OOF_CSV, index=False)
    print(f"OOF predictions saved: {OUT_OOF_CSV}")

    # ── Save results JSON ──
    results = {
        "baseline_f3": m_base,
        "candidate_f3_log": m_log,
        "delta": {
            "pct_25_pp": round(delta, 4),
            "pct_10_pp": round(m_log['pct_10'] - m_base['pct_10'], 4),
            "mae_t_ha": round(m_log['mae'] - m_base['mae'], 6),
            "r2": round(m_log['r2'] - m_base['r2'], 6),
        },
        "fold_results": {
            "base": [round(x, 4) for x in fold_base],
            "log": [round(x, 4) for x in fold_log],
            "base_mean": round(float(np.mean(fold_base)), 4),
            "base_std": round(float(np.std(fold_base)), 4),
            "log_mean": round(float(np.mean(fold_log)), 4),
            "log_std": round(float(np.std(fold_log)), 4),
        },
        "subgroup_analysis": sub_results,
        "decision": decision,
        "acceptance_criteria": {
            "meaningful_delta_pp": meaningful,
            "consistent_across_folds": consistent,
            "no_unacceptable_regression": no_regression,
        },
        "data_limitations": [
            "IMD rainfall covers only 1901-2015; years 2016-2017 are clipped to 2015 (stale rainfall features).",
            "Rainfall is at subdivision level (3 Karnataka subdivisions), not district level.",
            "District-level IMD gridded rainfall was unavailable (Kaggle dataset requires authentication).",
            "Open-Meteo ERA5 reanalysis exists for all 18 years but Phase 9 showed it does not improve the metric.",
        ],
        "n_rows_train": len(df_tr),
        "n_features_A": len(feats_A),
        "n_features_B": len(feats_B),
    }
    with open(OUT_RESULTS, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved: {OUT_RESULTS}")


if __name__ == "__main__":
    main()
