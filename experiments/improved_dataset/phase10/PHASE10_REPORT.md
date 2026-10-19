# Phase 10 — Error Analysis & Model Improvement Attempt

**Objective:** Find a reproducible, leakage-safe improvement to the F3 yield-regression model via error analysis and data-validity investigation.

**Date:** 2026-06-10
**Dataset:** `data/enriched_yield_karnataka.csv` (5,585 rows × 64 cols, 30 districts, 20 crops, 2000–2017)
**Baseline (F3):** 742/1,088 = **68.20%** within ±25% on frozen holdout; **69.54%** CV OOF

---

## 1. Final Decision

**RETAIN F3.** No tested hypothesis improved the grouped out-of-fold (OOF) within-±25% metric.

| Model | CV ±25% | Δ vs F3 | CV ±10% | CV MAE | CV R² |
|---|---|---|---|---|---|
| **F3 baseline** | **69.54%** | 0.00 | 36.05% | 0.2373 | 0.9475 |
| H1: Variance stretch | 64.95% | −4.58 | 33.67% | 0.2599 | 0.9378 |
| H2: Isotonic calibration | 67.38% | −2.16 | 33.00% | 0.2474 | 0.9430 |
| H3: Linear recalibration (a·x+b) | 68.27% | −1.27 | 34.42% | 0.2443 | 0.9445 |
| H4: `squared_error` loss | 68.96% | −0.58 | 35.31% | 0.2401 | 0.9458 |

All differences are within the CV noise (F3 grouped-CV std ≈ 2.63 pp). The `squared_error` loss reduced range compression but traded it for worse tolerance accuracy.

**Dominant failure mode:** Range compression from `HistGradientBoostingRegressor(loss='absolute_error')`. Low yields (0–0.5 t/ha) are 70% overpredicted; high yields (5+ t/ha) are underpredicted (bias −0.299 t/ha). However, the compressed predictions actually serve the ±25% tolerance metric better than de-compressed ones, because the tolerance band is narrowest at low yields and compression keeps predictions near the mean.

**Data limitation:** District-level aggregate yield data (ICRISAT) with static climate normals and subdivision-level rainfall cannot support accuracy beyond ~69–70% within ±25%. The per-crop, per-district cell counts are too small (median 17 rows over 18 years) to learn fine-grained yield variation.

---

## 2. Data Validity Audit

**Target:** `yield_per_hectare = Yield_Tonnes / Area_Hectares` (verified identical to precomputed column). Units: t/ha. Range: 0.018–14.23 t/ha, mean 1.40 t/ha.

| Check | Result |
|---|---|
| Exact duplicate rows | 0 |
| Duplicate (District, Year, Crop) keys | 0 |
| Missing values in features or target | 0 |
| `yield < 0.05` t/ha | 10 rows (0.18%) — genuine low-production records |
| `yield == 0` | 0 |
| `Area_Hectares` min | 10.0 (no division-by-zero) |
| Target leakage in 56 base features | None (`yield_per_hectare`, `log_yield_per_hectare`, `Yield_Tonnes` excluded) |
| `Area_Hectares` as feature | Legitimate (known at sowing time) |
| `year_offset`, `log_area_hectares` | Verified correct |
| `rain_*` features | Static climate normals (constant across years within district) — no leakage |
| Dynamic rainfall features | Subdivision-level IMD data, 7 features, joined by district→subdivision mapping — no leakage |

**No suspicious features requiring removal.**

---

## 3. F3 Out-of-Fold Error Analysis

Grouped OOF: `GroupKFold(n_splits=5)` on `District|Year` groups within the 80% training split.

### 3.1 Overall CV OOF metrics

| Metric | Value |
|---|---|
| Within ±25% | 3,127 / 4,497 = **69.54%** |
| Within ±10% | 1,621 / 4,497 = **36.05%** |
| MAE | 0.2373 t/ha |
| RMSE | 0.4450 t/ha |
| R² | 0.9475 |
| Mean bias (pred − true) | −0.0069 t/ha |

### 3.2 By actual-yield range (strongest signal)

| Range (t/ha) | n | ±25% | Bias (pred−true) | Overpred % |
|---|---|---|---|---|
| 0–0.5 | 1,249 | 54.7% | +0.084 | 70% |
| 0.5–1.0 | 1,590 | 72.7% | +0.014 | 48% |
| 1.0–2.0 | 891 | 72.5% | −0.063 | 35% |
| 2.0–3.0 | 321 | 81.3% | −0.040 | 47% |
| 3.0–5.0 | 213 | 81.7% | −0.095 | 32% |
| 5.0+ | 233 | 88.8% | −0.299 | 41% |

**Systematic overprediction at low yields, underprediction at high yields** — textbook range compression.

### 3.3 By crop

| Crop | n | ±25% | ±10% | MAE | Bias |
|---|---|---|---|---|---|
| Sugarcane | 252 | 85.3% | 50.0% | 1.085 | −0.010 |
| Rice | 273 | 85.0% | 66.3% | 0.238 | +0.011 |
| Maize | 269 | 73.6% | 40.5% | 0.534 | +0.003 |
| Chickpea | 228 | 70.6% | 31.6% | 0.121 | −0.006 |
| Groundnut | 268 | 68.3% | 34.0% | 0.170 | −0.011 |
| Cotton | 211 | 65.9% | 30.3% | 0.083 | −0.014 |
| Minor Pulses | 269 | 59.9% | 26.0% | 0.101 | −0.005 |
| Pigeonpea | 246 | 59.3% | 25.6% | 0.144 | −0.009 |
| Sesamum | 227 | 58.6% | 28.6% | 0.142 | −0.005 |

**Worst crops:** Sesamum (58.6%), Pigeonpea (59.3%), Minor Pulses (59.9%) — all low-yield crops with high variance.
**Best crops:** Sugarcane (85.3%), Rice (85.0%) — high-yield, low-relative-variance crops.

Sugarcane has the highest **absolute** MAE (1.085 t/ha) but the best **relative** accuracy because its mean yield is ~8 t/ha (±25% = ±2 t/ha band).

### 3.4 By year

| Year | n | ±25% | Bias |
|---|---|---|---|
| 2003 | 248 | 51.9% | +0.020 |
| 2016 | 267 | 49.8% | −0.015 |
| 2002 | 272 | 63.6% | +0.009 |
| 2009 | 250 | 63.2% | +0.012 |

Years 2003 and 2016 are drought years in Karnataka — the model fails to capture extreme yield drops.

### 3.5 Relative-error distribution

| Quantile | Relative error |
|---|---|
| Median | 0.122 |
| P75 | 0.364 |
| P90 | 0.905 |
| P95 | 1.574 |
| P99 | 4.087 |
| % > 0.5 (50% off) | 30.2% |
| % > 1.0 (100% off) | 16.7% |

### 3.6 Near-zero targets

- 9 rows with `yield < 0.05` t/ha (0.20% of OOF set)
- **0/9 within ±25%** — any positive prediction vastly exceeds a near-zero true value
- These are genuine low-production records (e.g., Kodagu 2013 Oilseeds: 0.034 t/ha), not data errors
- They disproportionately inflate relative-error metrics but have minimal impact on MAE/RMSE

---

## 4. Hypothesis Tests

All hypotheses were evaluated with **grouped OOF** (`GroupKFold(n_splits=5)` on `District|Year`). Calibration parameters were fit **inside each training fold** to avoid leakage. The frozen holdout (20%) is reported for reference only.

### H1: Per-crop variance stretch

**Motivation:** Range compression → multiply each crop's predictions by (yield_std / pred_std).

**Result:** CV ±25% = 64.95% (**−4.58 pp**). Over-corrected; predictions became too extreme, especially for crops with small samples where the std ratio was unstable.

### H2: Per-crop isotonic calibration

**Motivation:** Monotonic mapping from predicted to true yield, fit per crop on training fold.

**Result:** CV ±25% = 67.38% (**−2.16 pp**). Isotonic regression overfits on small per-crop samples (98–273 rows) and the correction does not generalize to held-out folds.

### H3: Per-crop linear recalibration (a·x + b)

**Motivation:** Simpler than isotonic; fit slope and intercept per crop on training fold.

**Result:** CV ±25% = 68.27% (**−1.27 pp**). Still overfits; the slope/intercept estimates are noisy on small samples.

### H4: `squared_error` loss (root-cause fix)

**Motivation:** `absolute_error` loss predicts the conditional median, compressing the range. `squared_error` predicts the conditional mean, which should preserve range.

**Result:** CV ±25% = 68.96% (**−0.58 pp**). Range compression **was** reduced (Sugarcane: yield_std/pred_std 1.377 → 1.172; Cotton: 1.908 → 1.425), but the tolerance metric worsened slightly. The de-compressed predictions are more sensitive to outlier yields (drought years), increasing MAE. The net effect on ±25% is negative, though within CV noise.

---

## 5. Why No Improvement Was Found

1. **Range compression is the core issue, but fixing it doesn't help the ±25% metric.** The ±25% band is narrowest at low yields (where compression overpredicts) and widest at high yields (where compression underpredicts). De-compression helps the high end but hurts the low end more.

2. **Per-crop calibration overfits.** With 98–273 rows per crop and high yield variance, the calibration parameters learned on training folds do not transfer to validation folds. The nested OOF evaluation exposed this.

3. **The data is near its accuracy ceiling.** District-level aggregate yields with static climate normals cannot capture field-level variation. The model already explains R² = 0.95 on OOF; the residual is irreducible noise from the aggregation.

4. **No data-quality defect was found.** The Sugarcane outliers (e.g., Bengaluru Urban 2007: 1.08 t/ha) are genuine drought-year records, not data-entry errors.

---

## 6. Recommendations for Future Work

1. **Field-level or sub-district data:** The current district-level aggregation is the primary ceiling. Block-level or village-level yield data would allow the model to learn finer patterns.

2. **Year-specific weather features:** The static `rain_*` climate normals and subdivision-level IMD rainfall cannot capture district-specific droughts (2003, 2016). District-level monthly rainfall would help.

3. **Crop-specific models for low-yield crops:** Sesamum, Pigeonpea, and Minor Pulses have <60% accuracy. A dedicated model per problematic crop, possibly with crop-specific features, might help.

4. **Quantile regression for range calibration:** Instead of post-hoc calibration, train a model that predicts the conditional distribution (quantiles) and use the median or mean as appropriate.

5. **Better handling of near-zero yields:** 9 near-zero targets (0.2% of data) all fail the ±25% metric. A two-stage model (classify "near-zero" first, then regress) could handle these.

---

## 7. Reproduction Commands

```bash
cd /Users/apple/SeedIQ/experiments/improved_dataset/phase10

# Full error analysis + 3 calibration hypotheses (generates all OOF predictions, JSON results)
python3 phase10_error_analysis.py

# squared_error loss experiment (H4) — run inline:
python3 -c "
import sys; sys.path.insert(0, '.')
from phase10_error_analysis import load_base, add_dynamic_rainfall, metrics_dict, BLEND_ALPHA, MIN_CROP_ROWS, RF_PARAMS, HISTGBR_PARAMS, DYN_FEATURES
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.model_selection import GroupShuffleSplit, GroupKFold
df, base = load_base(); df = add_dynamic_rainfall(df)
df['group_key'] = df['District']+'|'+df['Year'].astype(str)
y = df['yield_per_hectare'].values
tr, te = next(GroupShuffleSplit(1, 0.2, 42).split(df, y, df['group_key']))
dtr, ytr, gtr, ctr = df.iloc[tr].reset_index(drop=True), df.iloc[tr]['yield_per_hectare'].reset_index(drop=True), df.iloc[tr]['group_key'].reset_index(drop=True), df.iloc[tr]['Crop'].reset_index(drop=True)
fA, fB = base, base+[f for f in DYN_FEATURES if f not in base]
p = dict(HISTGBR_PARAMS); p['loss']='squared_error'
def fc(Xt,yt,ct,Xv,cv,fs):
    Xt,Xv=Xt[fs].copy(),Xv[fs].copy(); r=np.full(len(Xv),np.nan)
    for c in np.unique(cv):
        mt, mv = ct==c, cv==c
        if mt.sum()>=MIN_CROP_ROWS:
            m=HistGradientBoostingRegressor(**p); m.fit(Xt[mt],yt[mt]); r[mv]=m.predict(Xv[mv])
        else: r[mv]=yt[mt].mean() if mt.sum()>0 else yt.mean()
    return r
oA=oB=np.zeros(len(ytr))
for ft,fv in GroupKFold(5).split(dtr,ytr,gtr):
    oA[fv]=fc(dtr.iloc[ft],ytr.iloc[ft],ctr.iloc[ft],dtr.iloc[fv],ctr.iloc[fv],fA)
    oB[fv]=fc(dtr.iloc[ft],ytr.iloc[ft],ctr.iloc[ft],dtr.iloc[fv],ctr.iloc[fv],fB)
oC=BLEND_ALPHA*oA+(1-BLEND_ALPHA)*oB
print(metrics_dict(ytr.values, oC))
"
```

---

## 8. Files Created

| File | Description |
|---|---|
| `phase10/phase10_error_analysis.py` | Main script: data audit, F3 OOF error analysis, 3 calibration hypotheses |
| `phase10/results/phase10_f3_oof_predictions.csv` | 4,497 OOF rows (District, Year, Crop, yield, pred, residual, abs_residual) |
| `phase10/results/phase10_error_analysis.json` | Error analysis results (overall, by crop/year/range/district, outliers) |
| `phase10/results/phase10_hypothesis_results.json` | All hypothesis results + final decision |
| `phase10/PHASE10_REPORT.md` | This report |

No existing files were modified. No datasets, models, or production code were changed.
