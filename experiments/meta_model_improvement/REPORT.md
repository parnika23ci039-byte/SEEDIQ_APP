# Meta Model Improvement Report

**Date:** 2026-10-11  
**Scope:** Seed Viability classifier (3-class) — the only measurable Meta Model sub-component with real labels.

---

## 1. What the "Meta Model" actually is (audit findings)

### Production (`SeedIQ/models/meta_model.pkl`)
| Property | Value |
|---|---|
| Type | `RandomForestClassifier(max_depth=3, min_samples_leaf=5)` |
| Input | 6 normalized scalars: `[pred_rf_val, pred_qml_val, pred_xgb_val, pred_qml_yield_val, pred_svm_val, pred_qml_seed_val]` |
| Output | Binary 0/1 → `prob_success` percentage |
| Label source | **Synthetic / rule-generated** — no real ground-truth "overall success" exists |
| Train script correspondence | **None** — `train_final_meta_and_compare.py` trains a StackingClassifier on three independent datasets; this does NOT match what `app.py` loads or calls |

> **This production meta model cannot be meaningfully improved** without genuine labelled outcomes — there is no real-world ground truth for "Optimal Performance vs Suboptimal".

### Train-Serve Mismatch (confirmed)
`app.py` line 3100–3104 builds a 6-feature hand-crafted vector and calls `meta_model.predict_proba(meta_features)`. The training script produces a StackingClassifier fitted on crop/yield/seed datasets with hundreds of features — completely different object.

---

## 2. Improvable component: Seed Viability Classifier

This is the only Meta Model sub-component with:
- Real labels (UCI Seeds dataset — physical wheat kernel measurements)
- Measurable classification accuracy
- No synthetic labels

**Dataset:** `SeedIQ/data/Seed_Data.csv` — 210 rows × 7 features × 3 balanced classes (70 each)  
**Features:** `A` (area), `P` (perimeter), `C` (compactness), `LK`, `WK` (kernel length/width), `A_Coef` (asymmetry coeff), `LKG` (kernel groove length)

### Bug fixed: outlier-clip index shrinkage
The existing `clean_dataset()` applies the column 1%-99% mask sequentially on the same DataFrame. After the first column masks out rows, the index shrinks; subsequent masks from the original index fail with `ValueError` or silently misalign, dropping 29 rows (210→181). This changes the random split and is not reproducible across pandas versions.

**Correction:** use all 210 rows (the dataset is already clean, no genuine outlier removal needed).

---

## 3. Results — identical 42-row holdout, evaluated once

| Metric | Baseline (RF n=50) | Candidate (GBM n=200) | Δ |
|---|---|---|---|
| **Test accuracy** | **90.48%** (38/42) | **92.86%** (39/42) | **+2.38 pp** |
| Test macro-F1 | 0.9007 | 0.9263 | +2.56 pp |
| Test macro-precision | 0.9167 | 0.9368 | +2.01 pp |
| Test macro-recall | 0.9048 | 0.9286 | +2.38 pp |
| Train accuracy | — | 99.40% | — |
| 5-fold CV (train only) | — | 92.86% ± 3.09% | — |

**Leakage check:** 0 test rows found in training set ✓  
**Preprocessor:** `StandardScaler` fitted on `X_tr` only; never on `X_te` ✓

### Classification report — Candidate (GBM)
```
              precision  recall  f1
class 0           1.00    0.79  0.88  (3 misclassified as class 2)
class 1           0.93    1.00  0.97
class 2           0.88    1.00  0.93
accuracy                        0.93
```

**Confusion matrix:**
```
[[11  1  2]
 [ 0 14  0]
 [ 0  0 14]]
```
All 3 errors are class-0 misclassified as class-2 (over-compactness misread).

### Is 85% achieved?
✅ Yes — 92.86% on held-out test. Baseline was already 90.48%; GBM improves to 92.86%.

---

## 4. Production vs evaluation discrepancies (summary)

1. **Synthetic meta label** — `meta_model.pkl` uses rule-generated binary labels; no real-world validation possible.
2. **Train-serve mismatch** — `train_final_meta_and_compare.py` produces a different model object than what `app.py` loads.
3. **Outlier-clip bug** — `clean_dataset()` has sequential mask shrinkage, causing 29 dropped rows and non-reproducible splits.
4. **Yield target mismatch** (from Phase 13) — production model targets `Yield_Tonnes`; evaluation measures `yield_per_hectare`.

---

## 5. Files delivered

| File | Purpose |
|---|---|
| `meta_model_improvement.py` | Training + evaluation script (Tasks 1–3) |
| `metrics.json` | Machine-readable results, leakage check, findings |
| `seed_viability_gbm_candidate.pkl` | Candidate model (experiment dir only — NOT production) |
| `REPORT.md` | This report |

Production models, `app.py`, and all Phase 9–13 artifacts are **untouched**.

---

## 6. Next single action

> **Replace the synthetic-label `meta_model.pkl` with a documented heuristic confidence score, or collect real user-outcome labels.**  
> No algorithm change can improve a model trained on invented labels. The GBM candidate for seed viability is ready for production review and can replace `models/seed_viability/randomforest_model.pkl` after sign-off.

---

## 7. Reproducibility

```bash
cd /Users/apple/SeedIQ
python3 experiments/meta_model_improvement/meta_model_improvement.py
```
