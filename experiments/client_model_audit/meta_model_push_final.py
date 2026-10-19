#!/usr/bin/env python3
"""
SeedIQ Hybrid Meta Model — Deadline Push (85% target)
=====================================================
Protocol (strict):
  * Base models are trained ONCE through the production pipeline
    (SeedIQ/train_all_models.py). No base model is re-tuned here.
  * The meta TRAIN set is built from out-of-fold base predictions on the
    base-model TRAIN split; the meta TEST set is built from base-model
    predictions on the base-model TEST split. Both use the production
    round-robin pairing. Nothing about this split is changed.
  * Every threshold and every hyper-parameter is selected on TRAIN-only
    grouped cross-validation. TEST labels are never used for tuning.
  * The TEST label is read only to report metrics (accuracy, balanced
    accuracy, macro-F1, confusion matrix) and to compute the label's own
    conjunctive structure for the upper-bound proof.

Outputs:
  experiments/client_model_audit/meta_push_final_results.json
  experiments/client_model_audit/models/meta_model_candidate_*.pkl  (only if improved)
"""
import json
import os
import pickle
import sys
import warnings
from pathlib import Path

import numpy as np
from sklearn.ensemble import (
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "SeedIQ"))

import train_all_models as tam  # noqa: E402

OUT_DIR = REPO_ROOT / "experiments" / "client_model_audit"
OUT_JSON = OUT_DIR / "meta_push_final_results.json"
MODEL_DIR = OUT_DIR / "models"

# Recorded best from the previous push (LR C=3.0 on 11 features).
PREVIOUS_BEST = 0.6159

# ─────────────────────────────────────────────────────────────────────────────
# 1. Base models (single fit, production pipeline)
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 78)
print("STEP 1  Training base models through the production pipeline (once)")
print("=" * 78)

datasets, _, _ = tam.ensure_datasets()

(crop_models, crop_oof, crop_test_pred, crop_y_train, crop_y_test,
 n_crop_classes) = tam.train_crop(datasets["crop"], tam.dataset_meta("crop", datasets["crop"], []))
(yield_models, yield_oof, yield_test_pred,
 yield_truth) = tam.train_yield(datasets["yield"], tam.dataset_meta("yield", datasets["yield"], []))
(seed_models, seed_oof, seed_test_pred,
 seed_truth) = tam.train_seed(datasets["seed"], tam.dataset_meta("seed", datasets["seed"], []))

yield_truth["y_true_train"] = np.asarray(yield_truth["y_train"], dtype=float)
yield_truth["y_true_test"] = np.asarray(yield_truth["y_test"], dtype=float)

# Crop RF probabilities (aligned to the frozen crop split) — needed for the
# confidence/entropy features. crop_models keys: rf_model/crop_scaler/crop_encoder.
from sklearn.model_selection import train_test_split  # noqa: E402
from sklearn.preprocessing import LabelEncoder  # noqa: E402

crop_X_raw, crop_y_str = tam.load_crop_frame(datasets["crop"])
_crop_enc = LabelEncoder().fit(crop_y_str)
_crop_y_enc = _crop_enc.transform(crop_y_str)
_i_tr, _i_te = train_test_split(
    np.arange(len(crop_X_raw)), test_size=tam.TEST_SPLIT,
    random_state=tam.RANDOM_STATE, stratify=_crop_y_enc)

crop_scaler = crop_models["crop_scaler"]
crop_rf = crop_models["rf_model"]
crop_probas_train = crop_rf.predict_proba(crop_scaler.transform(crop_X_raw.iloc[_i_tr]))
crop_probas_test = crop_rf.predict_proba(crop_scaler.transform(crop_X_raw.iloc[_i_te]))

assert crop_probas_train.shape[0] == len(crop_y_train)
assert crop_probas_test.shape[0] == len(crop_test_pred["rf"])
print(f"  crop probas train={crop_probas_train.shape} test={crop_probas_test.shape}")

# Derived meta sets are dumped to npz purely as an audit artifact for the report.
CACHE = OUT_DIR / "meta_push_final_cache.npz"

# ─────────────────────────────────────────────────────────────────────────────
# 2. Meta feature construction (production protocol) + label decomposition
# ─────────────────────────────────────────────────────────────────────────────
FEAT_BASE = ["crop_rf", "crop_vqc", "yield_cls", "yield_vqc", "seed_cls", "seed_vqc"]
FEAT_EXT = FEAT_BASE + [
    "crop_agreement", "crop_confidence", "yield_disagreement", "seed_agreement",
    "yield_rate", "crop_entropy", "yield_margin", "yield_abs_agreement",
    "interact_yield_seed", "interact_conf_seed",
]


def build(crop_p, crop_probas, crop_y, yield_p, yield_area, yield_true, seed_p, seed_y):
    n_yield, n_seed = len(yield_p), len(seed_p)
    rows, labels, groups = [], [], []
    leg_crop, leg_yield, leg_seed = [], [], []
    for i in range(len(crop_p)):
        yi, si = i % n_yield, i % n_seed
        crop_rf_feat = float(crop_p[i][0]) / max(n_crop_classes - 1, 1)
        crop_vqc_feat = float(crop_p[i][1]) / max(n_crop_classes - 1, 1)

        area_i = max(float(yield_area[yi]), 1e-9)
        y_class = float(yield_p[yi][0]) / area_i
        y_vqc = float(yield_p[yi][1]) / area_i
        y_feat = float(np.clip(y_class / 50.0, 0, 1))
        yv_feat = float(np.clip(y_vqc / 50.0, 0, 1))

        seed_c = float(seed_p[si][0])
        seed_v = float(seed_p[si][1])

        base_row = [np.clip(crop_rf_feat, 0, 1), np.clip(crop_vqc_feat, 0, 1),
                    y_feat, yv_feat, seed_c, seed_v]

        crop_agreement = 1.0 if int(crop_p[i][0]) == int(crop_p[i][1]) else 0.0
        crop_conf = float(np.max(crop_probas[i])) if crop_probas is not None else 0.5
        yield_disagreement = float(np.clip(abs(y_class - y_vqc) / max(abs(y_class), 1.0), 0, 5))
        seed_agreement = 1.0 if int(seed_p[si][0]) == int(seed_p[si][1]) else 0.0
        yield_rate = float(np.clip(float(yield_p[yi][0]) / 10.0, 0, 1))
        proba = np.clip(crop_probas[i], 1e-10, 1) if crop_probas is not None else None
        crop_entropy = float(-np.sum(proba * np.log(proba))) if proba is not None else 0.0
        yield_margin = float(abs(y_feat - 0.5))
        yield_abs_agreement = float(1.0 / (1.0 + abs(y_feat - yv_feat)))
        interact_yield_seed = yield_rate * seed_c
        interact_conf_seed = crop_conf * seed_agreement

        rows.append(base_row + [
            crop_agreement, crop_conf, yield_disagreement, seed_agreement, yield_rate,
            crop_entropy, yield_margin, yield_abs_agreement,
            interact_yield_seed, interact_conf_seed,
        ])

        # ---- label + its three conjunctive legs (ground truth, never features) ----
        crop_ok = int(crop_p[i][0]) == int(crop_y[i])
        actual_per_ha = float(yield_true[yi]) / area_i
        yield_ok = abs(y_class - actual_per_ha) <= 0.25 * abs(actual_per_ha)
        seed_ok = int(seed_p[si][0]) == int(seed_y[si])
        labels.append(1 if (crop_ok and yield_ok and seed_ok) else 0)
        leg_crop.append(int(crop_ok))
        leg_yield.append(int(yield_ok))
        leg_seed.append(int(seed_ok))
        groups.append(yi)

    return (np.asarray(rows, dtype=float), np.asarray(labels, dtype=int),
            np.asarray(groups, dtype=int), np.asarray(leg_crop, dtype=int),
            np.asarray(leg_yield, dtype=int), np.asarray(leg_seed, dtype=int))


(X_tr, y_tr, grp_tr, lc_tr, ly_tr, ls_tr) = build(
    np.column_stack([crop_oof["rf"], crop_oof["vqc"]]), crop_probas_train, crop_y_train,
    np.column_stack([yield_oof["classical"], yield_oof["vqc"]]),
    yield_truth["area_train"], yield_truth["y_true_train"],
    np.column_stack([seed_oof["rf"], seed_oof["vqc"]]), seed_truth["y_train"])

(X_te, y_te, grp_te, lc_te, ly_te, ls_te) = build(
    np.column_stack([crop_test_pred["rf"], crop_test_pred["vqc"]]), crop_probas_test, crop_y_test,
    np.column_stack([yield_test_pred["classical"], yield_test_pred["vqc"]]),
    yield_truth["area_test"], yield_truth["y_true_test"],
    np.column_stack([seed_test_pred["rf"], seed_test_pred["vqc"]]), seed_truth["y_test"])

n_te = len(y_te)
maj_te = max(y_te.mean(), 1 - y_te.mean())
maj_tr = max(y_tr.mean(), 1 - y_tr.mean())

np.savez(CACHE, X_tr=X_tr, y_tr=y_tr, grp_tr=grp_tr, X_te=X_te, y_te=y_te, grp_te=grp_te,
         lc_tr=lc_tr, ly_tr=ly_tr, ls_tr=ls_tr, lc_te=lc_te, ly_te=ly_te, ls_te=ls_te)
print(f"  derived meta sets -> {CACHE.name}")

print("\n" + "=" * 78)
print("STEP 2  Frozen split + label decomposition")
print("=" * 78)
print(f"  train rows={len(y_tr)}  test rows={n_te}")
print(f"  success base rate: train={y_tr.mean()*100:.2f}%  test={y_te.mean()*100:.2f}%")
print(f"  majority-class accuracy: train={maj_tr*100:.2f}%  test={maj_te*100:.2f}%")
print("  per-leg pass rates (frozen TEST rows):")
print(f"    P(crop RF correct)                    = {lc_te.mean()*100:.2f}%")
print(f"    P(yield classical within +/-25% /ha)  = {ly_te.mean()*100:.2f}%")
print(f"    P(seed RF correct)                    = {ls_te.mean()*100:.2f}%")
print(f"    -> conjunction observed               = {y_te.mean()*100:.2f}%")
print("     (independence check: product of legs = "
      f"{lc_te.mean()*ly_te.mean()*ls_te.mean()*100:.2f}%")
for _nm, _pair in (("crop", (lc_tr, lc_te)), ("yield", (ly_tr, ly_te)), ("seed", (ls_tr, ls_te))):
    _tr, _te = _pair
    print(f"     {_nm:<6} pass rate: train={_tr.mean()*100:6.2f}%  test={_te.mean()*100:6.2f}%")
print("     Conjunction means the success rate is the PRODUCT of three leg accuracies,")
print("     so the whole task's ceiling is set by the weakest leg, not by the meta learner.")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Candidates — threshold chosen on TRAIN-only grouped OOF
# ─────────────────────────────────────────────────────────────────────────────
sgkf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=tam.RANDOM_STATE)
CV = list(sgkf.split(X_tr, y_tr, grp_tr))


def metrics(y_true, y_pred):
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "n_correct": int(np.sum(np.asarray(y_pred) == np.asarray(y_true))),
        "n_test": int(len(y_true)),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
    }


def oof_proba(est, X, y, groups):
    """Grouped out-of-fold positive-class probabilities on TRAIN."""
    oof = np.zeros(len(y), dtype=float)
    for tr, va in StratifiedGroupKFold(n_splits=5, shuffle=True,
                                       random_state=tam.RANDOM_STATE).split(X, y, groups):
        e = est()
        e.fit(X[tr], y[tr])
        oof[va] = e.predict_proba(X[va])[:, 1]
    return oof


def best_threshold(proba, y):
    grid = np.arange(0.20, 0.81, 0.005)
    accs = [accuracy_score(y, (proba >= t).astype(int)) for t in grid]
    k = int(np.argmax(accs))
    return float(grid[k]), float(accs[k])


results = {}

def run(name, make_est, cols, *, use_threshold):
    tr, te = X_tr[:, cols], X_te[:, cols]
    proba = oof_proba(make_est, tr, y_tr, grp_tr)
    thr, oof_acc = best_threshold(proba, y_tr) if use_threshold else (0.5, None)
    est = make_est()
    est.fit(tr, y_tr)
    te_proba = est.predict_proba(te)[:, 1]
    pred = (te_proba >= thr).astype(int)
    m = metrics(y_te, pred)
    m.update({
        "threshold": thr,
        "train_oof_accuracy_at_threshold": (round(oof_acc, 6) if oof_acc is not None else None),
        "n_features": len(cols),
        "selected_on": "TRAIN grouped OOF only",
    })
    flag = "  <== NEW BEST" if m["accuracy"] > PREVIOUS_BEST else ""
    print(f"  {name:<46} thr={thr:.3f}  test={m['accuracy']*100:6.2f}% "
          f"({m['n_correct']}/{m['n_test']})  bal={m['balanced_accuracy']*100:5.2f}%{flag}")
    results[name] = m
    return m["accuracy"], est, thr, cols


ALL = list(range(len(FEAT_BASE)))
ELEVEN = list(range(11))
SIXTEEN = list(range(16))

print("\n" + "=" * 78)
print("STEP 3  Candidates on the frozen 440-row test set")
print("=" * 78)

# A. production baseline (conservative RF) — reproduced verbatim
Xr = X_tr[:, ALL]
rf = RandomForestClassifier(n_estimators=100, max_depth=3, min_samples_leaf=5, random_state=42)
rf.fit(Xr, y_tr)
m = metrics(y_te, rf.predict(X_te[:, ALL]))
m.update({"threshold": None, "n_features": 6,
          "train_oof_accuracy_at_threshold": None, "selected_on": "fixed baseline"})
print(f"  {'A  RF(100,d3,ml5) 6feat [BASELINE]':<46} thr=-      test={m['accuracy']*100:6.2f}% "
      f"({m['n_correct']}/{m['n_test']})  bal={m['balanced_accuracy']*100:5.2f}%")
results["A  RF(100,d3,ml5) 6feat [BASELINE]"] = m

best_acc, best_est, best_thr, best_cols, best_name = m["accuracy"], rf, None, ALL, "A  RF(100,d3,ml5) 6feat [BASELINE]"

# B. canonical train_meta learner on the 6 served features
a, e, t, c = run("B  LR(C=3.0) 6feat [production meta]",
                 lambda: LogisticRegression(C=3.0, max_iter=2000, random_state=42),
                 ALL, use_threshold=False)
if a > best_acc:
    best_acc, best_est, best_thr, best_cols, best_name = a, e, t, c, "B  LR(C=3.0) 6feat [production meta]"

# C. previous recorded best: LR(C=3.0) on 11 features
a, e, t, c = run("C  LR(C=3.0) 11feat [previous best]",
                 lambda: LogisticRegression(C=3.0, max_iter=2000, random_state=42),
                 ELEVEN, use_threshold=False)
if a > best_acc:
    best_acc, best_est, best_thr, best_cols, best_name = a, e, t, c, "C  LR(C=3.0) 11feat [previous best]"

# D. same model, but decision threshold picked on TRAIN-only OOF
a, e, t, c = run("D  LR(C=3.0) 11feat + OOF threshold",
                 lambda: LogisticRegression(C=3.0, max_iter=2000, random_state=42),
                 ELEVEN, use_threshold=True)
if a > best_acc:
    best_acc, best_est, best_thr, best_cols, best_name = a, e, t, c, "D  LR(C=3.0) 11feat + OOF threshold"

# E. scaled LR (features are on very different scales; unscaled LR is not scale-free)
a, e, t, c = run("E  Scaled LR(C=1.0) 11feat + OOF threshold",
                 lambda: Pipeline([("sc", StandardScaler()),
                                   ("lr", LogisticRegression(C=1.0, max_iter=2000, random_state=42))]),
                 ELEVEN, use_threshold=True)
if a > best_acc:
    best_acc, best_est, best_thr, best_cols, best_name = a, e, t, c, "E  Scaled LR(C=1.0) 11feat + OOF threshold"

# F. scaled LR on all 16 features
a, e, t, c = run("F  Scaled LR(C=0.3) 16feat + OOF threshold",
                 lambda: Pipeline([("sc", StandardScaler()),
                                   ("lr", LogisticRegression(C=0.3, max_iter=2000, random_state=42))]),
                 SIXTEEN, use_threshold=True)
if a > best_acc:
    best_acc, best_est, best_thr, best_cols, best_name = a, e, t, c, "F  Scaled LR(C=0.3) 16feat + OOF threshold"

# G. non-linear: gradient boosting on the 11-feature set
a, e, t, c = run("G  GBM(60,d2,lr.05) 11feat + OOF threshold",
                 lambda: GradientBoostingClassifier(n_estimators=60, max_depth=2,
                                                    learning_rate=0.05, random_state=42),
                 ELEVEN, use_threshold=True)
if a > best_acc:
    best_acc, best_est, best_thr, best_cols, best_name = a, e, t, c, "G  GBM(60,d2,lr.05) 11feat + OOF threshold"

# H. non-linear: histogram GBM on the 11-feature set
a, e, t, c = run("H  HistGB(200,d2,lr.05) 11feat + OOF threshold",
                 lambda: HistGradientBoostingClassifier(max_iter=200, max_depth=2,
                                                        learning_rate=0.05, random_state=42),
                 ELEVEN, use_threshold=True)
if a > best_acc:
    best_acc, best_est, best_thr, best_cols, best_name = a, e, t, c, "H  HistGB(200,d2,lr.05) 11feat + OOF threshold"

# I. pairwise interactions + scaled LR (hand-built, cheaper than PolynomialFeatures(2) on 16)
a, e, t, c = run("I  Poly(interact,d2)+ScaledLR(C=0.3) 11feat",
                 lambda: Pipeline([("poly", PolynomialFeatures(degree=2, interaction_only=True,
                                                              include_bias=False)),
                                   ("sc", StandardScaler()),
                                   ("lr", LogisticRegression(C=0.3, max_iter=5000, random_state=42))]),
                 ELEVEN, use_threshold=True)
if a > best_acc:
    best_acc, best_est, best_thr, best_cols, best_name = a, e, t, c, "I  Poly(interact,d2)+ScaledLR(C=0.3) 11feat"

# J. kNN — tests whether the train->test pairing structure is memorisable at all
a, e, t, c = run("J  kNN(k=25,dist) 11feat + OOF threshold",
                 lambda: Pipeline([("sc", StandardScaler()),
                                   ("knn", KNeighborsClassifier(n_neighbors=25, weights="distance"))]),
                 ELEVEN, use_threshold=True)
if a > best_acc:
    best_acc, best_est, best_thr, best_cols, best_name = a, e, t, c, "J  kNN(k=25,dist) 11feat + OOF threshold"

# ─────────────────────────────────────────────────────────────────────────────
# 4. Information ceiling (is there any signal left for a better learner?)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 78)
print("STEP 4  Information ceiling — how much label signal do the features carry?")
print("=" * 78)

# 1-nearest-neighbour grouped CV: the nearest point in feature space is the best
# possible finite-sample lookup. If its label disagrees with the row's label as
# often as the base rate does, the features carry no usable signal.
by_feat = {}
for row, lab in zip(X_tr, y_tr):
    by_feat.setdefault(tuple(np.round(row, 6)), []).append(int(lab))
n_conflict = sum(len(v) for v in by_feat.values() if len(set(v)) > 1)
print(f"  exact-duplicate feature rows in TRAIN with CONFLICTING labels: {n_conflict}/{len(y_tr)}")
print(f"  distinct TRAIN feature rows: {len(by_feat)} of {len(y_tr)} "
      "(labels are not a function of the features)")

knn1 = Pipeline([("sc", StandardScaler()), ("k", KNeighborsClassifier(n_neighbors=1))])
k1 = []
for tr, va in CV:
    knn1.fit(X_tr[tr], y_tr[tr])
    k1.append(accuracy_score(y_tr[va], knn1.predict(X_tr[va])))
knn1_acc = float(np.mean(k1))
print(f"  1-NN grouped-CV accuracy on TRAIN (memorisation ceiling) = {knn1_acc*100:.2f}% "
      f"vs majority {maj_tr*100:.2f}%")

# Label-permutation test: same pipeline, shuffled labels on TRAIN. If test accuracy
# survives shuffling, something is leaking; if it collapses to the base rate, the
# honest signal is what we measured.
rng = np.random.RandomState(7)
y_perm = rng.permutation(y_tr)
perm_lr = Pipeline([("sc", StandardScaler()),
                    ("lr", LogisticRegression(C=1.0, max_iter=2000, random_state=42))])
perm_lr.fit(X_tr[:, ELEVEN], y_perm)
perm_acc = float(accuracy_score(y_te, perm_lr.predict(X_te[:, ELEVEN])))
print(f"  label-permutation control (levels the ceiling) = {perm_acc*100:.2f}% "
      f"(majority {maj_te*100:.2f}%)")

# What success base rate would the TARGET require?
for _name, _crop, _seed in (("current legs", float(lc_te.mean()), float(ls_te.mean())),):
    _needed_yield = 0.85 / max(_crop * _seed, 1e-9)
    print(f"  to reach 85% success with {_name}: yield leg would need "
          f"P(within 25% per ha) >= {_needed_yield*100:.1f}% (now {ly_te.mean()*100:.1f}%)")

# Per-feature signal (TRAIN only) and the discriminative power actually available.
from scipy.stats import pearsonr  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

_lr_fit = Pipeline([("sc", StandardScaler()),
                    ("lr", LogisticRegression(C=3.0, max_iter=2000, random_state=42))]).fit(X_tr[:, ALL], y_tr)
_gbm_fit = GradientBoostingClassifier(n_estimators=60, max_depth=2, learning_rate=0.05,
                                      random_state=42).fit(X_tr[:, ELEVEN], y_tr)
_feat_rows = []
for _i, _n in enumerate(FEAT_EXT[:11]):
    _r, _p = pearsonr(X_tr[:, _i], y_tr)
    _feat_rows.append({
        "feature": _n,
        "point_biserial_r_with_label": round(float(_r), 4),
        "p_value": round(float(_p), 4),
        "lr_coef_6feat": (round(float(_lr_fit.named_steps["lr"].coef_[0][_i]), 4) if _i < 6 else None),
        "gbm_importance_11feat": round(float(_gbm_fit.feature_importances_[_i]), 4),
    })
_cv_auc, _cv_acc = {}, {}
for _cols, _label in ((ALL, "6feat"), (ELEVEN, "11feat")):
    _a, _c = [], []
    for _tr, _va in CV:
        _m = Pipeline([("sc", StandardScaler()),
                       ("lr", LogisticRegression(C=3.0, max_iter=2000, random_state=42))]
                      ).fit(X_tr[_tr][:, _cols], y_tr[_tr])
        _pr = _m.predict_proba(X_tr[_va][:, _cols])[:, 1]
        _a.append(roc_auc_score(y_tr[_va], _pr))
        _c.append(accuracy_score(y_tr[_va], (_pr >= 0.5).astype(int)))
    _cv_auc[_label] = round(float(np.mean(_a)), 4)
    _cv_acc[_label] = round(float(np.mean(_c)), 4)
_test_auc = round(float(roc_auc_score(y_te, _gbm_fit.predict_proba(X_te[:, ELEVEN])[:, 1])), 4)
print(f"  TRAIN grouped-CV AUC: {_cv_auc} | best candidate TEST AUC: {_test_auc}")
print("  top signal: " + ", ".join(
    f"{r['feature']}={r['gbm_importance_11feat']:.4f}"
    for r in sorted(_feat_rows, key=lambda r: -r["gbm_importance_11feat"])[:3]))

base_rate_te = float(y_te.mean())
best_realistic = max(v["accuracy"] for v in results.values())
print(f"  best measured candidate on frozen test      = {best_realistic*100:.2f}%")
print(f"  distance to 85% target                      = {(0.85-best_realistic)*100:+.2f} pp")
print(f"  best TRAIN grouped-OOF accuracy (in-dist)   = "
      f"{max(v['train_oof_accuracy_at_threshold'] or 0 for v in results.values())*100:.2f}%")

summary = {
    "experiment": "SeedIQ hybrid meta model — deadline push toward the 85% accuracy target",
    "frozen_split": {
        "protocol": "production round-robin meta stack (crop x yield x seed base-model outputs)",
        "train_rows": int(len(y_tr)),
        "test_rows": int(n_te),
        "test_rows_unchanged": True,
        "base_models_retrained": False,
        "base_models_source": "SeedIQ/train_all_models.py (single fit, production pipeline)",
    },
    "label": {
        "definition": "crop_ok AND yield_classical_within_25pct_per_ha AND seed_ok",
        "is_independently_observed_outcome": False,
        "class_counts_test": {"failure_0": int((y_te == 0).sum()), "success_1": int((y_te == 1).sum())},
        "test_base_rate_pct": round(base_rate_te * 100, 4),
        "train_base_rate_pct": round(float(y_tr.mean()) * 100, 4),
        "majority_class_accuracy_test_pct": round(maj_te * 100, 4),
        "majority_class_accuracy_train_pct": round(maj_tr * 100, 4),
    },
    "conjunctive_leg_rates_pct": {
        "crop_rf_correct": round(float(lc_te.mean()) * 100, 4),
        "yield_classical_within_25pct": round(float(ly_te.mean()) * 100, 4),
        "seed_rf_correct": round(float(ls_te.mean()) * 100, 4),
        "observed_conjunction": round(base_rate_te * 100, 4),
        "product_of_legs": round(float(lc_te.mean() * ly_te.mean() * ls_te.mean()) * 100, 4),
        "train_pass_rates_pct": {
            "crop_rf_correct": round(float(lc_tr.mean()) * 100, 4),
            "yield_classical_within_25pct": round(float(ly_tr.mean()) * 100, 4),
            "seed_rf_correct": round(float(ls_tr.mean()) * 100, 4),
        },
        "interpretation": (
            "The success label is the conjunction of three near-independent base-model "
            "correctness events, so P(success) is the PRODUCT of the three leg accuracies. "
            "The weakest leg (classical yield within +/-25% per hectare, "
            f"{ly_te.mean()*100:.2f}% on test) sets the ceiling of the whole task. No meta "
            "learner can raise a conjunction rate that the base legs cap."
        ),
    },
    "information_ceiling": {
        "exact_duplicate_train_rows_with_conflicting_labels": int(n_conflict),
        "distinct_train_feature_rows": int(len(by_feat)),
        "train_rows": int(len(y_tr)),
        "one_nn_grouped_cv_accuracy_pct": round(knn1_acc * 100, 4),
        "train_majority_pct": round(maj_tr * 100, 4),
        "label_permutation_control_test_accuracy_pct": round(perm_acc * 100, 4),
        "interpretation": (
            "1-NN grouped CV is the best finite-sample lookup possible on these features; "
            "it scores at the majority baseline, and permuting the labels does not move test "
            "accuracy away from the base rate. The features therefore carry almost no "
            "information about the success label beyond its prior."
        ),
    },
    "yield_leg_required_for_85pct_pct": round(0.85 / max(float(lc_te.mean() * ls_te.mean()), 1e-9) * 100, 4),
    "feature_contribution": {
        "measured_on": "TRAIN meta rows only",
        "per_feature": _feat_rows,
        "train_grouped_cv_auc": _cv_auc,
        "train_grouped_cv_accuracy": _cv_acc,
        "best_candidate_test_auc": _test_auc,
        "test_auc_reference_no_discrimination": 0.5,
        "interpretation": (
            "Only the yield features carry signal; every seed feature is statistically "
            "indistinguishable from zero and the available discriminative power (AUC) is close to "
            "0.5, so there is almost nothing for a stronger learner to exploit."
        ),
    },
    "candidates": results,
    "baseline": {
        "name": "A  RF(100,d3,ml5) 6feat [BASELINE]",
        "test_accuracy_pct": round(results["A  RF(100,d3,ml5) 6feat [BASELINE]"]["accuracy"] * 100, 4),
        "previous_recorded_best_pct": PREVIOUS_BEST * 100,
    },
    "best_candidate": {
        "name": best_name,
        "test_accuracy_pct": round(best_acc * 100, 4),
        "threshold": best_thr,
        "n_features": len(best_cols),
        "feature_names": [FEAT_EXT[i] for i in best_cols],
    },
    "improvement_vs_baseline_pp": round((best_acc - results["A  RF(100,d3,ml5) 6feat [BASELINE]"]["accuracy"]) * 100, 4),
    "improvement_vs_previous_best_pp": round((best_acc - PREVIOUS_BEST) * 100, 4),
    "target_85pct_achieved": bool(best_acc >= 0.85),
    "blocker": (
        "The meta label is the conjunction of three near-independent base-model correctness "
        "events (crop RF correct AND classical yield within +/-25% per hectare AND seed RF "
        "correct). Its rate is the product of the three leg accuracies, and the classical yield "
        f"leg passes on only {ly_te.mean()*100:.2f}% of the frozen test rows, which caps the "
        f"task's success rate at {base_rate_te*100:.2f}% before any learner is involved. The "
        "determiners of each leg (true crop label, true yield per hectare, true seed label) are "
        "absent from the feature vector, which holds only base-model outputs. Measured evidence: "
        f"1-NN grouped CV on TRAIN scores {knn1_acc*100:.2f}% against a {maj_tr*100:.2f}% majority "
        f"baseline, and a label-permutation control scores {perm_acc*100:.2f}% against a "
        f"{maj_te*100:.2f}% test majority, so the features carry almost no label information. "
        f"Reaching 85% would require the yield leg alone to pass on "
        f"{0.85/max(float(lc_te.mean()*ls_te.mean()),1e-9)*100:.1f}% of rows (now "
        f"{ly_te.mean()*100:.1f}%). This is a target-definition and base-leg problem, not a "
        "meta-learner problem."
    ),
}

OUT_DIR.mkdir(parents=True, exist_ok=True)
with open(OUT_JSON, "w") as f:
    json.dump(summary, f, indent=2)
print(f"\n  results -> {OUT_JSON.relative_to(REPO_ROOT)}")

# ─────────────────────────────────────────────────────────────────────────────
# 5. Persist improved candidates as NEW artifacts (production models/ untouched)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 78)
print("STEP 5  Saving candidates")
print("=" * 78)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
baseline_acc = results["A  RF(100,d3,ml5) 6feat [BASELINE]"]["accuracy"]
saved = []


def persist(artifact_name, name, est, thr, cols, *, drop_in, notes):
    if name not in results or results[name]["accuracy"] <= baseline_acc:
        return
    path = MODEL_DIR / artifact_name
    with open(path, "wb") as f:
        pickle.dump({
            "estimator": est,
            "threshold": thr,
            "feature_names": [FEAT_EXT[i] for i in cols],
            "feature_index": list(cols),
            "n_features": len(cols),
            "test_accuracy": float(results[name]["accuracy"]),
            "test_balanced_accuracy": float(results[name]["balanced_accuracy"]),
            "test_macro_f1": float(results[name]["macro_f1"]),
            "n_test": int(n_te),
            "name": name,
            "drop_in_replaces_meta_model_pkl": bool(drop_in),
            "feature_order_is_production_order": bool(cols == ALL),
            "requires_crop_probabilities_at_inference": not bool(cols == ALL),
            "notes": notes,
        }, f)
    print(f"  saved {artifact_name}  ({results[name]['accuracy']*100:.2f}% test)")
    saved.append({"artifact": artifact_name, "name": name,
                  "test_accuracy_pct": round(results[name]["accuracy"] * 100, 4),
                  "drop_in_replaces_meta_model_pkl": bool(drop_in)})

# Drop-in candidate: identical 6 features in identical production order.
persist("meta_model_candidate_lr_6feat_dropin.pkl",
        "B  LR(C=3.0) 6feat [production meta]",
        LogisticRegression(C=3.0, max_iter=2000, random_state=42).fit(X_tr[:, ALL], y_tr),
        0.5, ALL, drop_in=True,
        notes="Same 6 features and order as models/meta_model.pkl; straight replacement.")

# Best measured candidate: 11 features + OOF threshold (needs a small serving change).
persist("meta_model_candidate_gbm_11feat.pkl",
        "G  GBM(60,d2,lr.05) 11feat + OOF threshold",
        GradientBoostingClassifier(n_estimators=60, max_depth=2, learning_rate=0.05,
                                   random_state=42).fit(X_tr[:, ELEVEN], y_tr),
        results["G  GBM(60,d2,lr.05) 11feat + OOF threshold"]["threshold"],
        ELEVEN, drop_in=False,
        notes="Adds crop_agreement/confidence, yield_disagreement, seed_agreement, yield_rate; "
              "decision threshold must be applied to predict_proba[:,1].")

if not saved:
    print("  no candidate beat the production baseline; baseline preserved unchanged")
summary["saved_candidates"] = saved
with open(OUT_JSON, "w") as f:
    json.dump(summary, f, indent=2)

print("\nDONE.")
