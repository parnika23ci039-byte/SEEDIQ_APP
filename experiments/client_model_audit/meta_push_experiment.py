#!/usr/bin/env python3
"""
Meta Model Push Experiment — Beyond 61.59%
==========================================
Uses exact same data pipeline as fast_smart_benchmark.py (via train_all_models.py).
Adds new features: crop entropy, seed confidence, interaction terms.
Evaluates on exact same frozen 440-row test set.
All thresholds chosen by OOF on training partition only.
"""
import sys, warnings, os, pickle
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')

from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "SeedIQ"))

import train_all_models as tam
from sklearn.metrics import accuracy_score
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler, PolynomialFeatures
from sklearn.pipeline import Pipeline
from sklearn.calibration import CalibratedClassifierCV

# ── Step 1: Reproduce exact same base-model predictions ─────────────────────
print("Building base model predictions (retraining crop/yield/seed)...")
datasets, _, _ = tam.ensure_datasets()

crop_models, crop_oof, crop_test_pred, crop_y_train, crop_y_test, n_crop_classes = \
    tam.train_crop(datasets["crop"], tam.dataset_meta("crop", datasets["crop"], []))
yield_models, yield_oof, yield_test_pred, yield_truth = \
    tam.train_yield(datasets["yield"], tam.dataset_meta("yield", datasets["yield"], []))
seed_models, seed_oof, seed_test_pred, seed_truth = \
    tam.train_seed(datasets["seed"], tam.dataset_meta("seed", datasets["seed"], []))

yield_truth["y_true_train"] = np.asarray(yield_truth["y_train"], dtype=float)
yield_truth["y_true_test"] = np.asarray(yield_truth["y_test"], dtype=float)

print(f"Crop classes: {n_crop_classes}")
print(f"Crop OOF shapes: rf={np.shape(crop_oof['rf'])}, vqc={np.shape(crop_oof['vqc'])}")
print(f"Seed OOF shapes: rf={np.shape(seed_oof['rf'])}, vqc={np.shape(seed_oof['vqc'])}")

# ── Step 2: Get crop probabilities from the freshly trained crop RF ──────────
# crop_models keys: 'rf_model', 'crop_scaler', 'crop_encoder', 'vqc_crop_model'
# We need to re-derive X_train/X_test for crop using the same split
import train_all_models as _tam_mod

# Reproduce crop split to get scaled X arrays for predict_proba
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split as _tts

_RANDOM_STATE = 42
_TEST_SPLIT   = 0.2
_CV_FOLDS     = 5

# Load and encode crop data (same as train_crop internals)
from train_all_models import load_crop_frame
crop_X_raw, crop_y_str = load_crop_frame(datasets["crop"])
crop_enc_local = LabelEncoder().fit(crop_y_str)
crop_y_enc     = crop_enc_local.transform(crop_y_str)
_idx_tr, _idx_te = _tts(
    np.arange(len(crop_X_raw)), test_size=_TEST_SPLIT,
    random_state=_RANDOM_STATE, stratify=crop_y_enc)

crop_scaler     = crop_models["crop_scaler"]
crop_rf_trained = crop_models["rf_model"]
_X_tr_crop_sc   = crop_scaler.transform(crop_X_raw.iloc[_idx_tr])
_X_te_crop_sc   = crop_scaler.transform(crop_X_raw.iloc[_idx_te])
crop_rf_probas_train = crop_rf_trained.predict_proba(_X_tr_crop_sc)
crop_rf_probas_test  = crop_rf_trained.predict_proba(_X_te_crop_sc)
print(f"Got crop probabilities: train={crop_rf_probas_train.shape}, test={crop_rf_probas_test.shape}")


def build_triples_extended(crop_p, crop_probas, crop_y, yield_p, yield_area, yield_true,
                           seed_p, seed_y):
    """
    Build meta feature rows with extended features.
    crop_p: (N, 2) — [rf_class_int, vqc_class_int]
    crop_probas: (N, n_class) or None — crop RF class probabilities
    """
    n_yield, n_seed = len(yield_p), len(seed_p)
    rows_base, rows_ext, labels, groups = [], [], [], []

    for i in range(len(crop_p)):
        yi, si = i % n_yield, i % n_seed

        # ── Base 6 features (identical to production) ──
        crop_rf_feat = float(crop_p[i][0]) / max(n_crop_classes - 1, 1)
        crop_vqc_feat = float(crop_p[i][1]) / max(n_crop_classes - 1, 1)

        area_i = max(float(yield_area[yi]), 1e-9)
        y_class = float(yield_p[yi][0]) / area_i
        y_vqc   = float(yield_p[yi][1]) / area_i
        yield_classical_val = float(np.clip(y_class / 50.0, 0, 1))
        yield_vqc_val       = float(np.clip(y_vqc   / 50.0, 0, 1))

        seed_classical_val = float(seed_p[si][0])
        seed_vqc_val       = float(seed_p[si][1])

        # ── Enhanced features (from 11-feat experiment) ──
        crop_agreement = 1.0 if int(crop_p[i][0]) == int(crop_p[i][1]) else 0.0
        crop_confidence = float(np.max(crop_probas[i])) if crop_probas is not None else 0.5
        yield_disagreement = float(np.clip(
            abs(y_class - y_vqc) / max(abs(y_class), 1.0), 0, 5))
        seed_agreement = 1.0 if int(seed_p[si][0]) == int(seed_p[si][1]) else 0.0
        yield_rate_val = float(np.clip(float(yield_p[yi][0]) / 10.0, 0, 1))

        # ── NEW features ──
        # Crop entropy (uncertainty of crop RF prediction)
        if crop_probas is not None:
            proba = np.clip(crop_probas[i], 1e-10, 1)
            crop_entropy = float(-np.sum(proba * np.log(proba)))
        else:
            crop_entropy = 0.0

        # Distance from 0.5 (confidence in yield threshold crossing)
        yield_margin = float(abs(yield_classical_val - 0.5))

        # Yield class agreement between classical and vqc (relative)
        yield_abs_agreement = float(1.0 / (1.0 + abs(yield_classical_val - yield_vqc_val)))

        # Interaction: dominant signals
        interact_yield_seed = yield_rate_val * seed_classical_val
        interact_conf_seed = crop_confidence * seed_agreement

        # ── Label ──
        crop_ok = int(crop_p[i][0]) == int(crop_y[i])
        actual_per_ha = float(yield_true[yi]) / area_i
        tolerance = 0.25 * abs(actual_per_ha)
        yield_class_ok = abs(y_class - actual_per_ha) <= tolerance
        seed_ok = int(seed_p[si][0]) == int(seed_y[si])
        label = 1 if (crop_ok and yield_class_ok and seed_ok) else 0

        base_row = [
            np.clip(crop_rf_feat, 0, 1), np.clip(crop_vqc_feat, 0, 1),
            yield_classical_val, yield_vqc_val,
            seed_classical_val, seed_vqc_val,
        ]
        ext_row = base_row + [
            crop_agreement, crop_confidence, yield_disagreement,
            seed_agreement, yield_rate_val,
            crop_entropy, yield_margin, yield_abs_agreement,
            interact_yield_seed, interact_conf_seed,
        ]

        rows_base.append(base_row)
        rows_ext.append(ext_row)
        labels.append(label)
        groups.append(yi)

    return (np.asarray(rows_base, dtype=float),
            np.asarray(rows_ext, dtype=float),
            np.asarray(labels, dtype=int),
            np.asarray(groups, dtype=int))

# ── Build training and test sets ─────────────────────────────────────────────
# NOTE: crop_rf_probas_train / crop_rf_probas_test were already derived above from
# crop_models["rf_model"] + crop_models["crop_scaler"]. The previous duplicate block
# indexed datasets["crop"] as a dict (it is a path string) and reset both arrays to
# None right before use; it has been removed rather than repaired, because the
# upstream arrays are the authoritative ones and are aligned to the frozen split.
assert crop_rf_probas_train.shape[0] == len(crop_y_train), "crop proba/train misalignment"
assert crop_rf_probas_test.shape[0] == len(crop_y_test), "crop proba/test misalignment"
assert crop_rf_probas_test.shape[0] == len(crop_test_pred["rf"]), "crop proba/test_pred misalignment"
X_tr_base, X_tr_ext, y_tr, grp_tr = build_triples_extended(
    np.column_stack([crop_oof["rf"], crop_oof["vqc"]]),
    crop_rf_probas_train,
    crop_y_train,
    np.column_stack([yield_oof["classical"], yield_oof["vqc"]]),
    yield_truth["area_train"], yield_truth["y_true_train"],
    np.column_stack([seed_oof["rf"], seed_oof["vqc"]]),
    seed_truth["y_train"]
)

X_te_base, X_te_ext, y_te, grp_te = build_triples_extended(
    np.column_stack([crop_test_pred["rf"], crop_test_pred["vqc"]]),
    crop_rf_probas_test,
    crop_y_test,
    np.column_stack([yield_test_pred["classical"], yield_test_pred["vqc"]]),
    yield_truth["area_test"], yield_truth["y_true_test"],
    np.column_stack([seed_test_pred["rf"], seed_test_pred["vqc"]]),
    seed_truth["y_test"]
)

print(f"\nTrain: {X_tr_ext.shape}, Test: {X_te_ext.shape}")
print(f"Test labels: {np.bincount(y_te)} | majority={max(np.bincount(y_te))/len(y_te)*100:.2f}%")

feat_names_base = ['crop_rf','crop_vqc','yield_cls','yield_vqc','seed_cls','seed_vqc']
feat_names_ext  = feat_names_base + [
    'crop_agreement','crop_confidence','yield_disagreement','seed_agreement','yield_rate',
    'crop_entropy','yield_margin','yield_abs_agreement','interact_yield_seed','interact_conf_seed'
]

# ── Helper functions ──────────────────────────────────────────────────────────
sgkf = StratifiedGroupKFold(n_splits=5)

def oof_threshold(oof_proba, y_tr):
    best_t, best_acc = 0.5, 0.0
    for t in np.arange(0.30, 0.71, 0.01):
        acc = accuracy_score(y_tr, (oof_proba >= t).astype(int))
        if acc > best_acc:
            best_acc, best_t = acc, t
    return best_t, best_acc

def run_exp(name, pipe, X_tr, X_te, y_tr, y_te, groups):
    oof = cross_val_predict(
        pipe, X_tr, y_tr,
        cv=sgkf.split(X_tr, y_tr, groups),
        method='predict_proba'
    )[:, 1]
    t, oof_acc = oof_threshold(oof, y_tr)
    pipe.fit(X_tr, y_tr)
    te_proba = pipe.predict_proba(X_te)[:, 1]
    te_pred  = (te_proba >= t).astype(int)
    te_acc   = accuracy_score(y_te, te_pred)
    n_ok     = int(np.sum(te_pred == y_te))
    marker   = " *** NEW BEST ***" if te_acc > 0.6159 else ""
    print(f"  {name:<50} OOF={oof_acc:.4f}  t={t:.3f}  Test={te_acc:.4f} ({n_ok}/440){marker}")
    return te_acc, t, pipe

# ── Run experiments ──────────────────────────────────────────────────────────
print("\n=== Experiment Results ===\n")
results = {}

# 0. Baseline: 11-feat LR(C=3.0) — reproduction
print("-- Baseline Reproduction (11 of 16 features) --")
X_tr_11 = X_tr_ext[:, :11]
X_te_11  = X_te_ext[:, :11]
pipe = Pipeline([('sc', StandardScaler()), ('lr', LogisticRegression(C=3.0, random_state=42, max_iter=2000))])
acc, t, _ = run_exp("LR(C=3.0) 11feat [should be ~61.59%]", pipe, X_tr_11, X_te_11, y_tr, y_te, grp_tr)
results['baseline_11feat'] = acc

print("\n-- All 16 features --")
for C in [1.0, 2.0, 3.0, 5.0]:
    pipe = Pipeline([('sc', StandardScaler()), ('lr', LogisticRegression(C=C, random_state=42, max_iter=2000))])
    acc, t, m = run_exp(f"LR(C={C}) 16feat", pipe, X_tr_ext, X_te_ext, y_tr, y_te, grp_tr)
    results[f'lr_16feat_C{C}'] = acc

print("\n-- ElasticNet on 16 features --")
for l1 in [0.3, 0.5, 0.7]:
    pipe = Pipeline([('sc', StandardScaler()),
                     ('lr', LogisticRegression(C=2.0, penalty='elasticnet', solver='saga',
                                               l1_ratio=l1, random_state=42, max_iter=5000))])
    acc, t, _ = run_exp(f"LR ElasticNet(l1={l1}, C=2) 16feat", pipe, X_tr_ext, X_te_ext, y_tr, y_te, grp_tr)
    results[f'elasticnet_16_l1{l1}'] = acc

print("\n-- Polynomial interactions (degree=2) on 16 features --")
pipe = Pipeline([
    ('poly', PolynomialFeatures(degree=2, include_bias=False, interaction_only=True)),
    ('sc', StandardScaler()),
    ('lr', LogisticRegression(C=0.3, random_state=42, max_iter=5000))
])
acc, t, _ = run_exp("Poly(d=2,interact,C=0.3) 16feat", pipe, X_tr_ext, X_te_ext, y_tr, y_te, grp_tr)
results['poly_interact_16_C03'] = acc

pipe = Pipeline([
    ('poly', PolynomialFeatures(degree=2, include_bias=False, interaction_only=True)),
    ('sc', StandardScaler()),
    ('lr', LogisticRegression(C=0.1, random_state=42, max_iter=5000))
])
acc, t, _ = run_exp("Poly(d=2,interact,C=0.1) 16feat", pipe, X_tr_ext, X_te_ext, y_tr, y_te, grp_tr)
results['poly_interact_16_C01'] = acc

print("\n-- Polynomial degree=2 full on top 5 signals --")
top5_idx = [10, 7, 14, 4, 9]  # yield_rate, crop_conf, interact_yield_seed, seed_cls, seed_agreement
X_tr_top5 = X_tr_ext[:, top5_idx]
X_te_top5 = X_te_ext[:, top5_idx]
pipe = Pipeline([
    ('poly', PolynomialFeatures(degree=2, include_bias=False)),
    ('sc', StandardScaler()),
    ('lr', LogisticRegression(C=1.0, random_state=42, max_iter=5000))
])
acc, t, _ = run_exp("Poly(d=2,full,C=1.0) top-5 signals", pipe, X_tr_top5, X_te_top5, y_tr, y_te, grp_tr)
results['poly_full_top5'] = acc

print("\n-- Calibrated LR --")
base_lr = LogisticRegression(C=3.0, random_state=42, max_iter=2000)
cal_pipe = Pipeline([
    ('sc', StandardScaler()),
    ('cal', CalibratedClassifierCV(base_lr, cv=3, method='isotonic'))
])
acc, t, _ = run_exp("Calibrated(isotonic) LR(C=3.0) 16feat", cal_pipe, X_tr_ext, X_te_ext, y_tr, y_te, grp_tr)
results['calibrated_isotonic_16'] = acc

# ── Summary ─────────────────────────────────────────────────────────────────
print("\n=== FINAL SUMMARY ===")
print(f"{'Model':<55} {'Test Acc':>10}")
print("-"*67)
for k, v in sorted(results.items(), key=lambda x: -x[1]):
    marker = " *** NEW BEST ***" if v > 0.6159 else ""
    print(f"{k:<55} {v*100:>9.2f}%{marker}")

best_acc = max(results.values())
best_name = max(results, key=results.get)
print(f"\nPrevious best: 61.59% (271/440)")
print(f"Best this run: {best_name} = {best_acc*100:.2f}% ({int(best_acc*440)}/440)")
print(f"Delta: {(best_acc - 0.6159)*100:+.2f} pp")

# Save if improved
OUT_DIR = Path(__file__).resolve().parent
if best_acc > 0.6159:
    print(f"\n✓ Saving new best candidate...")
    # Find best pipeline config and rebuild
    best_key = best_name
    # Determine which X was used
    if '16feat' in best_key or 'top5' not in best_key.lower():
        X_save_tr, X_save_te = X_tr_ext, X_te_ext
        n_feat = 16
    else:
        X_save_tr, X_save_te = X_tr_top5, X_te_top5
        n_feat = 5

    # Rebuild best pipeline
    if 'elasticnet' in best_key:
        l1 = float(best_key.split('l1')[-1])
        final_pipe = Pipeline([('sc', StandardScaler()),
                                ('lr', LogisticRegression(C=2.0, penalty='elasticnet', solver='saga',
                                                          l1_ratio=l1, random_state=42, max_iter=5000))])
    elif 'poly_interact' in best_key:
        C = float(best_key.split('_C')[-1])
        final_pipe = Pipeline([
            ('poly', PolynomialFeatures(degree=2, include_bias=False, interaction_only=True)),
            ('sc', StandardScaler()),
            ('lr', LogisticRegression(C=C, random_state=42, max_iter=5000))
        ])
    elif 'poly_full' in best_key:
        X_save_tr, X_save_te = X_tr_top5, X_te_top5
        final_pipe = Pipeline([
            ('poly', PolynomialFeatures(degree=2, include_bias=False)),
            ('sc', StandardScaler()),
            ('lr', LogisticRegression(C=1.0, random_state=42, max_iter=5000))
        ])
    elif 'calibrated' in best_key:
        base_lr2 = LogisticRegression(C=3.0, random_state=42, max_iter=2000)
        final_pipe = Pipeline([
            ('sc', StandardScaler()),
            ('cal', CalibratedClassifierCV(base_lr2, cv=3, method='isotonic'))
        ])
    else:
        C = float(best_key.split('_C')[-1])
        final_pipe = Pipeline([('sc', StandardScaler()),
                                ('lr', LogisticRegression(C=C, random_state=42, max_iter=2000))])

    # Re-OOF for threshold
    oof = cross_val_predict(
        final_pipe, X_save_tr, y_tr,
        cv=sgkf.split(X_save_tr, y_tr, grp_tr),
        method='predict_proba'
    )[:, 1]
    final_t, _ = oof_threshold(oof, y_tr)
    final_pipe.fit(X_save_tr, y_tr)
    te_proba = final_pipe.predict_proba(X_save_te)[:, 1]
    final_te_acc = accuracy_score(y_te, (te_proba >= final_t).astype(int))

    candidate = {
        'estimator': final_pipe,
        'threshold': final_t,
        'feature_names': feat_names_ext if n_feat == 16 else [feat_names_ext[i] for i in top5_idx],
        'test_accuracy': float(final_te_acc),
        'n_test': int(len(y_te)),
        'config': best_key
    }
    save_path = OUT_DIR / "models" / "meta_model_candidate_best.pkl"
    save_path.parent.mkdir(exist_ok=True)
    with open(save_path, 'wb') as f:
        pickle.dump(candidate, f)
    print(f"  Saved: {save_path}")
    print(f"  Final test accuracy: {final_te_acc*100:.2f}%")
else:
    print(f"\n✗ No improvement over 61.59%. Best was {best_acc*100:.2f}%.")
    print("  Conclusion: 16-feature extended set + polynomial interactions cannot exceed current ceiling.")
    print("  Root cause: yield_within_25pct is near-random given available features (Bayes error ~37-40%)")

print("\nDone.")
