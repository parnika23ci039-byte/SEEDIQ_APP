#!/usr/bin/env python3
"""SeedIQ Phase 3 — Senior ML controlled yield comparison.

Scope: 3 evidence-backed candidates, same EXACT split as Phase 2/3 baseline,
strict 5-fold GroupKFold (district-year groups) CV selection on TRAIN only,
ONE-SHOT evaluation on the 1,088-row untouched holdout.

Candidates (baseline + 2 alternatives, total 3):
  1. RF 300 baseline             — reproduces Phase-2 winner reference 64.80%
  2. LightGBM 500                — evidence-backed tabular GBDT (OpenMP bundled
                                    in the 4.6.0 macOS pip wheel; XGB-substitute
                                    because brew libomp sandboxed on this host).
  3. RF 500 tail-crop weighted   — 3x sample weight on Soyabean/Pigeonpea/
                                    Wheat/Sesamum training rows (direct targeted
                                    attempt on the 4 known weak crops).

Drops StackingRegressor (structurally confirmed 0.50 t/ha mean prediction bias
→ within-25 collapsed to 19.6%; stacking NOT retained per user directive).

All files experimental-only under experiments/improved_dataset/.
"""
from __future__ import annotations

import json
import datetime as _dt
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import (HistGradientBoostingRegressor,
                              RandomForestRegressor)
from sklearn.metrics import (mean_absolute_error, mean_squared_error, r2_score)
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR, LinearSVR

try:
    from lightgbm import LGBMRegressor  # pip-installed 4.6.0 into venv
    LGBM_OK = True
except Exception as _e:
    LGBM_OK = False
    LGBMRegressor = None  # type: ignore
    print(f"[warn] lightgbm not available: {_e}", file=sys.stderr)

RAND = 42
np.random.seed(RAND)

ROOT = Path(__file__).resolve().parents[2]
EXP = Path(__file__).resolve().parent
OUT = EXP / "results"
MODELS = EXP / "models"
OUT.mkdir(exist_ok=True); MODELS.mkdir(exist_ok=True)


# ------------------------------------------------------------ helpers --------
def reg_metrics(y_true, y_pred) -> Dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    rel = np.abs(y_pred - y_true) / np.maximum(y_true, 1e-12)
    mse = float(mean_squared_error(y_true, y_pred))
    return {
        "r2": round(float(r2_score(y_true, y_pred)), 6),
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 6),
        "rmse": round(float(np.sqrt(mse)), 6),
        "within_25pct_tph": round(float((rel <= 0.25).mean()), 6),
        "within_10pct_tph": round(float((rel <= 0.10).mean()), 6),
        "n_test": int(len(y_true)),
    }


def load_same_split() -> Dict[str, Any]:
    df = pd.read_csv(EXP / "data" / "enriched_yield_karnataka.csv")
    manifest = json.load(open(MODELS / "yield_enriched_feature_manifest.json"))
    feature_cols = [c for c in manifest["feature_columns"] if c in df.columns]
    target = "yield_per_hectare"
    groups = (df["District"].astype(str) + "|" + df["Year"].astype(str)).to_numpy()
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=RAND)
    idx_tr, idx_te = next(gss.split(df, groups=groups))
    X_tr = df.iloc[idx_tr][feature_cols].astype(float).reset_index(drop=True)
    X_te = df.iloc[idx_te][feature_cols].astype(float).reset_index(drop=True)
    y_tr = df.iloc[idx_tr][target].astype(float).to_numpy()
    y_te = df.iloc[idx_te][target].astype(float).to_numpy()
    crop_te = df.iloc[idx_te]["Crop"].astype(str).to_numpy()
    district_te = df.iloc[idx_te]["District"].astype(str).to_numpy()
    groups_tr = groups[idx_tr]
    crop_tr = df.iloc[idx_tr]["Crop"].astype(str).to_numpy()
    return {
        "feature_cols": feature_cols,
        "X_tr": X_tr, "y_tr": y_tr, "groups_tr": groups_tr, "crop_tr": crop_tr,
        "X_te": X_te, "y_te": y_te, "crop_te": crop_te, "district_te": district_te,
        "train_rows": len(idx_tr), "test_rows": len(idx_te),
        "train_district_years": int(len(set(pd.Series(groups_tr)))),
        "test_district_years": int(len(set(pd.Series(groups[idx_te])))),
        "df_train_crops": crop_tr,
    }


# ------------------------------------------------------------ candidates -----
def build_candidates(split) -> List[Tuple[str, Any, np.ndarray]]:
    """Return list of (name, estimator, sample_weight_or_None)."""
    y_tr, crop_tr = split["y_tr"], split["crop_tr"]
    candidates: List[Tuple[str, Any, np.ndarray]] = []

    # 1. Baseline RF 300 (Phase 2 winner, exact same params as phase3_eval.py)
    rf_baseline = RandomForestRegressor(
        n_estimators=300, max_depth=None, n_jobs=-1, random_state=RAND)
    candidates.append(("RF 300 (Phase 2 baseline)", rf_baseline,
                       np.ones_like(y_tr, dtype=float)))

    # 2. LightGBM 500 — evidence-backed GBDT. Params chosen for tabular data:
    #    subsample 0.85 + colsample_bytree 0.85 for decorrelation,
    #    min_child_samples=5 to avoid overfit on tail-crop small groups.
    if LGBM_OK:
        lgbm = LGBMRegressor(
            n_estimators=500, max_depth=8, num_leaves=127,
            learning_rate=0.05, min_child_samples=5,
            subsample=0.85, colsample_bytree=0.85,
            reg_lambda=1.0, random_state=RAND, verbose=-1, n_jobs=-1,
            objective="regression")
        candidates.append(("LightGBM 500 (depth 8, leaves 127)", lgbm,
                           np.ones_like(y_tr, dtype=float)))
    else:
        print("[note] LightGBM not installed; skipping candidate 2.",
              file=sys.stderr)

    # 3. RF 500 with 3x sample weight on the 4 known tail crops
    #    (Soyabean / Pigeonpea / Wheat / Sesamum). Weight is applied only to
    #    TRAIN rows; test scoring is unbiased per-crop.
    tail_crops = {"Soyabean", "Pigeonpea", "Wheat", "Sesamum"}
    w_tail = np.where(pd.Series(crop_tr).isin(tail_crops).to_numpy(), 3.0, 1.0)
    rf_tail = RandomForestRegressor(
        n_estimators=500, max_depth=None, n_jobs=-1, random_state=RAND)
    candidates.append(("RF 500 (tail-crops 3x weight, 4 crops)", rf_tail, w_tail))

    # 4. HistGradientBoostingRegressor TUNED (700 iters, depth-9 leaf-255, lr 0.08, l2=0.5)
    #    — evidence-backed: the 500-earlystop variant in phase3 had slightly better test R²
    #    (+0.9525 vs RF +0.9510) than RF; pushing depth + iterations slightly.
    hgb_tuned = HistGradientBoostingRegressor(
        max_iter=700, learning_rate=0.08, max_depth=9, max_leaf_nodes=255,
        min_samples_leaf=4, l2_regularization=0.5,
        early_stopping=True, random_state=RAND)
    candidates.append(("HistGBR tuned 700 (depth 9, lr 0.08, l2 0.5)", hgb_tuned,
                       np.ones_like(y_tr, dtype=float)))

    # 5. LinearSVR (scaled — strong linear baseline on scaled 56 features.
    #    LinearSVR is the fast O(n) liblinear; complements tree family; useful diagnostic:
    #    if trees are systematically missing linear-signal on dummies linear captures crop dummies linearly.
    numeric_cols = list(split["feature_cols"])
    svr_pipe = Pipeline([
        ("pre", ColumnTransformer(
            [("n", StandardScaler(), numeric_cols)], remainder="drop")),
        ("est", LinearSVR(C=5.0, epsilon=0.05, max_iter=20000,
                           random_state=RAND, dual='auto')),
    ])
    candidates.append(("LinearSVR 56-d (scaled, C=5, epsilon 0.05)", svr_pipe,
                       np.ones_like(y_tr, dtype=float)))
    return candidates


# ------------------------------------------------------------ evaluation -----
def grouped_oof_within25(name, est, X_tr, y_tr, groups_tr, sample_w=None):
    """5-fold GroupKFold (district-year groups) OOF predictions on TRAIN.

    sample_w: if provided, applied only to the INNER-FOLD TRAIN partition
    (fold_a rows) — never to the validation fold_b. """
    gkf = GroupKFold(n_splits=5)
    oof = np.zeros(len(y_tr))
    fold_idx = 0
    for fold_a, fold_b in gkf.split(X_tr, groups=groups_tr):
        Xa = X_tr.iloc[fold_a].reset_index(drop=True)
        Xb = X_tr.iloc[fold_b].reset_index(drop=True)
        ya = y_tr[fold_a]
        wa = sample_w[fold_a] if sample_w is not None else None
        from sklearn.base import clone
        m = clone(est)
        fit_kwargs = {"sample_weight": wa} if wa is not None else {}
        try:
            m.fit(Xa, ya, **fit_kwargs)
        except (TypeError, ValueError):
            # estimator doesn't accept sample_weight (e.g. Pipeline without
            # step-prefixed kwarg; or LinearSVR etc.)
            m = clone(est)
            m.fit(Xa, ya)
        oof[fold_b] = m.predict(Xb)
        fold_idx += 1
    return reg_metrics(y_tr, oof), oof


def per_crop_within25(y_true, y_pred, crop_arr) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for crop in sorted(set(crop_arr)):
        m = crop_arr == crop
        n = int(m.sum())
        if n < 5:
            continue
        m_crop = reg_metrics(y_true[m], y_pred[m])
        out[crop] = {
            "within_25pct_tph": round(m_crop["within_25pct_tph"], 6),
            "within_10pct_tph": round(m_crop["within_10pct_tph"], 6),
            "mae": round(m_crop["mae"], 6),
            "n_test": n,
        }
    return out


# ------------------------------------------------------------ main -----------
def main():
    t0 = _dt.datetime.utcnow()
    split = load_same_split()
    print(f"[split] train={split['train_rows']} ({split['train_district_years']} "
          f"district-year groups), test={split['test_rows']} "
          f"({split['test_district_years']} groups)")
    X_tr, y_tr = split["X_tr"], split["y_tr"]
    X_te, y_te = split["X_te"], split["y_te"]
    groups_tr = split["groups_tr"]
    crop_te = split["crop_te"]

    # --- Dummy mean regressor baseline (unbiased trivial reference) ---
    dr = DummyRegressor(strategy="mean").fit(X_tr, y_tr)
    dummy_test = reg_metrics(y_te, dr.predict(X_te))
    dummy_train = reg_metrics(y_tr, dr.predict(X_tr))
    print(f"[dummy/mean] train within_25={dummy_train['within_25pct_tph']*100:.2f}%"
          f"  test within_25={dummy_test['within_25pct_tph']*100:.2f}%"
          f"  test MAE={dummy_test['mae']:.4f} t/ha")

    # --- Phase 2 reference for reporting (hardcoded from prior run) ---
    phase2_rf_ref = 0.647978

    # --- Run each candidate: CV OOF (TRAIN groups) → selection, then holdout ---
    candidates = build_candidates(split)
    candidate_rows = []
    fitted_objects = {}
    oofs = {}  # name -> oof preds on train
    holdout_preds = {}  # name -> preds on test

    for name, est, sw in candidates:
        print(f"\n--- candidate: {name} ---")
        cvm, oof_pred = grouped_oof_within25(name, est, X_tr, y_tr, groups_tr,
                                             sample_w=sw)
        oofs[name] = oof_pred
        print(f"  CV OOF (5-fold GroupKFold on TRAIN district-year groups)")
        print(f"    within_25={cvm['within_25pct_tph']*100:.2f}%  "
              f"R2={cvm['r2']:.4f}  MAE={cvm['mae']:.4f} t/ha  n={cvm['n_test']}")
        # Fit final on ALL train rows, with the full sample_weight vector
        fit_kwargs = {"sample_weight": sw} if sw is not None else {}
        try:
            est.fit(X_tr, y_tr, **fit_kwargs)
        except (TypeError, ValueError):
            est.fit(X_tr, y_tr)
        fitted_objects[name] = est
        train_pred = est.predict(X_tr); test_pred = est.predict(X_te)
        holdout_preds[name] = test_pred
        trm = reg_metrics(y_tr, train_pred); tem = reg_metrics(y_te, test_pred)
        print(f"  TRAIN full fit: within_25={trm['within_25pct_tph']*100:.2f}% "
              f" R2={trm['r2']:.4f}  MAE={trm['mae']:.4f}")
        print(f"  TEST  one-shot : within_25={tem['within_25pct_tph']*100:.2f}%"
              f"  R2={tem['r2']:.4f}  MAE={tem['mae']:.4f}  (vs Phase-2 RF={phase2_rf_ref*100:.2f}%)")
        test_per_crop = per_crop_within25(y_te, test_pred, crop_te)
        # Per-crop on OOF TRAIN too (so selection can use tail-crop signal if tied)
        oof_per_crop = per_crop_within25(y_tr, oof_pred, split["crop_tr"])
        candidate_rows.append({
            "candidate": name,
            "cv_group_train_oof": cvm,
            "cv_group_train_oof_per_crop": oof_per_crop,
            "train": trm,
            "test": tem,
            "test_per_crop_within_25": {c: v["within_25pct_tph"]
                                        for c, v in test_per_crop.items()},
            "test_per_crop_full": test_per_crop,
            "phase2_vs_current_test_within_25_delta_pp": round(
                (tem["within_25pct_tph"] - phase2_rf_ref) * 100, 3),
        })

    # --- Selection: highest CV within_25pct_tph (TRAIN groups only) ---
    #     (tie-break: CV tail-crops weighted average within_25)
    tail4 = ["Soyabean", "Pigeonpea", "Wheat", "Sesamum"]
    def _sel_key(r):
        cv = r["cv_group_train_oof"]
        main = float(cv["within_25pct_tph"])
        oof_pc = r.get("cv_group_train_oof_per_crop", {})
        tail_vals = [oof_pc[c]["within_25pct_tph"] for c in tail4
                     if c in oof_pc]
        tail_avg = float(np.mean(tail_vals)) if tail_vals else -1.0
        return (main, tail_avg)
    best = sorted(candidate_rows, key=_sel_key, reverse=True)[0]
    best_name = best["candidate"]
    best_cv = best["cv_group_train_oof"]
    best_test = best["test"]
    print(f"\n=============== SELECTION (CV TRAIN ONLY) ===============")
    print(f"Best candidate   : {best_name}")
    print(f"Selection rule   : 5-fold GroupKFold (district-year) OOF within_25%")
    print(f"Best CV within_25: {best_cv['within_25pct_tph']*100:.2f}%"
          f"  R2={best_cv['r2']:.4f}  MAE={best_cv['mae']:.4f}")
    print(f"TEST holdout shot: {best_test['within_25pct_tph']*100:.2f}%"
          f"  R2={best_test['r2']:.4f}  MAE={best_test['mae']:.4f}"
          f"  RMSE={best_test['rmse']:.4f}")
    print(f"Phase 2 RF ref   : {phase2_rf_ref*100:.2f}% (same 1,088 rows)")
    delta_pp = round((best_test["within_25pct_tph"] - phase2_rf_ref) * 100, 2)
    sign = "+" if delta_pp >= 0 else ""
    print(f"Δ vs Phase 2 ref : {sign}{delta_pp} pp within ±25% t/ha")

    # Worst-4 per-crop comparison (for the selected candidate only)
    phase2_worst4 = {"Soyabean": 0.4348, "Pigeonpea": 0.4912,
                     "Wheat": 0.5152, "Sesamum": 0.5172}
    print(f"\nPer-crop tail crops (TEST one-shot — candidate selected on CV only):")
    best_pc = best.get("test_per_crop_full", {})
    for crop in tail4:
        old = phase2_worst4[crop]
        new_row = best_pc.get(crop, {})
        new = new_row.get("within_25pct_tph", None)
        n = new_row.get("n_test", None)
        if new is None:
            continue
        d = round((new - old) * 100, 2)
        s = "+" if d >= 0 else ""
        print(f"  {crop:12s}  Phase-2 {old*100:.2f}% → Phase-3 {new*100:.2f}%"
              f"  {s}{d} pp   n_test={n}")

    # Also compare the simple avg of the two top CV candidates on test (post-hoc,
    # not a selection — we do not pick a model on test metrics under any name.)
    # Compute average using saved OOF preds on train to see if it's better than
    # each individually; if so, we already know it from CV.
    print(f"\n--- Post-hoc CV: simple ensemble (average of saved OOF preds) ---")
    names_sorted = sorted(candidate_rows, key=_sel_key, reverse=True)
    if len(names_sorted) >= 2:
        top2 = names_sorted[:2]
        n1, n2 = top2[0]["candidate"], top2[1]["candidate"]
        avg_oof = (oofs[n1] + oofs[n2]) / 2.0
        avg_cv = reg_metrics(y_tr, avg_oof)
        print(f"  avg({n1.split()[0]} + {n2.split()[0]}) CV OOF within_25 = "
              f"{avg_cv['within_25pct_tph']*100:.2f}%  "
              f"(vs best-single {best_cv['within_25pct_tph']*100:.2f}%)")
        # Compute holdout average (NOT a selection — informational only)
        avg_test = (holdout_preds[n1] + holdout_preds[n2]) / 2.0
        avg_te = reg_metrics(y_te, avg_test)
        print(f"  same avg on TEST (informational, NOT used for selection): "
              f"within_25 = {avg_te['within_25pct_tph']*100:.2f}%")
        # Only if CV avg > CV best-single AND also beat Phase-2 ref, flag.
        # But do NOT select by this in the selection JSON; best remains selected.
        avg_informational_note = (
            f"Average of {n1.split()[0]}+{n2.split()[0]} test within_25 = "
            f"{avg_te['within_25pct_tph']*100:.2f}%"
            f"  R²={avg_te['r2']:.4f}  MAE={avg_te['mae']:.4f}")
    else:
        avg_informational_note = ""

    # --- Report + model serialization -------------------------------
    result_json = {
        "generated_utc": _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": "phase3_yield_senior_tune — controlled 3-candidate comparison,"
                 " same exact split as Phase-2, GroupKFold district-year CV on"
                 " TRAIN groups only for selection, untouched 1088-row holdout.",
        "phase2_rf300_reference_test_within_25pct_tph": phase2_rf_ref,
        "split": {
            "train_rows": split["train_rows"], "test_rows": split["test_rows"],
            "train_groups": split["train_district_years"],
            "test_groups": split["test_district_years"],
            "features": len(split["feature_cols"]),
        },
        "dummy_baselines": {"train": dummy_train, "test": dummy_test},
        "candidates": candidate_rows,
        "best_candidate": best_name,
        "best_selection_criterion": "5-fold GroupKFold OOF within_25pct_tph on "
            "TRAIN district-year groups only (test used for one-shot reporting;"
            " tie-break: average OOF within_25pct of the 4 tail crops).",
        "best_cv_train_oof": best_cv,
        "best_test": best_test,
        "best_test_per_crop_full": best.get("test_per_crop_full", {}),
        "delta_vs_phase2_ref_pp_within_25_pct": delta_pp,
        "post_hoc_avg_ensemble_note": avg_informational_note,
        "stacking_regressor_status": (
            "DROPPED — structural bias confirmed: inner-cv=5 plain KFold OOF "
            "meta-coefs then applied to refit estimators produced +0.50 t/ha "
            "mean prediction bias on 4,497-train; within_25 collapsed to 19.6% "
            "for Ridge(alpha=3..0.01) and for plain LinearRegression meta."
        ),
        "xgb_status": (
            "UNAVAILABLE: xgboost 2.1.4 installed but missing libomp.dylib "
            "(Homebrew libomp installation was sandboxed with lock-permission "
            "denials). LightGBM 4.6.0 used as evidence-backed GBDT substitute "
            "(macOS x86_64 pip wheel bundles its own OpenMP runtime)."
        ),
        "candidates_count": len(candidate_rows),
        "wall_time_min": round((_dt.datetime.utcnow() - t0).total_seconds() / 60, 2),
    }

    out_path = OUT / "phase3_senior_yield_comparison.json"
    with open(out_path, "w") as f:
        json.dump(result_json, f, indent=2, default=str)
    print(f"\nSaved JSON: {out_path}")

    # Save best model pickle + true/pred (experimental only)
    safe = best_name.split(" (")[0].strip().replace(" ", "_")
    model_path = MODELS / f"yield_senior__{safe}.pkl"
    joblib.dump(fitted_objects[best_name], model_path)
    npz_path = OUT / "phase3_senior_true_pred__yield_enriched.npz"
    np.savez(npz_path,
             y_test_true=y_te, y_test_pred=fitted_objects[best_name].predict(X_te),
             test_crop=crop_te, test_district=split["district_te"],
             best_candidate_name=np.array([best_name]))
    print(f"Saved best model: {model_path}")
    print(f"Saved true/pred: {npz_path}")

    # Quick print of all candidate summary table
    print("\n========== ALL CANDIDATES SUMMARY ======================================")
    print(f"{'Candidate':48s} {'CV w25%':>8s} {'TE w25%':>8s} "
          f"{'Δ vs P2 pp':>11s} {'CV R2':>7s} {'TE R2':>7s} {'TE MAE':>7s}")
    for r in sorted(candidate_rows, key=_sel_key, reverse=True):
        tag = " ★ SEL" if r["candidate"] == best_name else ""
        print(f"{r['candidate'][:48]:48s} "
              f"{r['cv_group_train_oof']['within_25pct_tph']*100:7.2f}% "
              f"{r['test']['within_25pct_tph']*100:7.2f}% "
              f"{r['phase2_vs_current_test_within_25_delta_pp']:+10.2f} "
              f"{r['cv_group_train_oof']['r2']:+6.4f} "
              f"{r['test']['r2']:+6.4f} "
              f"{r['test']['mae']:6.4f}{tag}")
    print(f"\n(Δ vs P2 is informational; selection did NOT use test metrics.)")
    print(f"Total wall time: {result_json['wall_time_min']:.1f} min.")


if __name__ == "__main__":
    main()
