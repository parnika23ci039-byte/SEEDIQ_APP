# Phase 11 — Log-Target Transformation Experiment

**Date:** 2026-10-11
**Objective:** Improve the F3 yield-regression model's within-±25% metric via one evidence-based, leakage-safe correction.
**Outcome:** **RETAIN F3.** The tested hypothesis did not improve the model.

---

## 1. Data Availability Check (Step 1)

### Locally available rainfall data

| Dataset | Resolution | Years | Source | Status |
|---|---|---|---|---|
| `SeedIQ/data/rainfall in india 1901-2015.csv` | IMD **subdivision** (3 Karnataka subdivisions) | 1901–2015 | IMD ground observations | Already used by F3 (B branch, 20% weight) |
| `SeedIQ/data/district wise rainfall normal.csv` | District **static normals** (long-term avg) | n/a | IMD | Static — cannot be used as yearly observations |
| `phase9/data/openmeteo_daily_weather_karnataka.csv` | District daily (19 districts) | 2000–2017 | ERA5 reanalysis (not ground truth) | Phase 9 showed no improvement |

### Bounded attempt to obtain district-level IMD rainfall

- Searched for IMD district-level monthly rainfall. Found Kaggle dataset `dhamur/monthly-district-avg-rainfall-19012017indiacsv` (exact coverage needed).
- **Blocker:** Download requires Kaggle API authentication; no credentials available locally. Direct HTTP download returns a login page.
- IMD gridded 0.25° rainfall (1901–2017) exists at Stanford EarthWorks but is in GRD/ASCII binary format requiring non-trivial geospatial processing.
- **Decision:** District-level ground-observed rainfall is **not available**. Per the protocol, do not manufacture a candidate from reanalysis data. Fall back to the OOF-based error-subgroup correction.

---

## 2. Hypothesis (Step 2 — single test)

### Largest actionable error subgroup (from Phase 10 OOF)

**Low-yield overprediction** is the largest single error source:
- 1,249 rows with `yield < 0.5 t/ha` (27.8% of training rows)
- Only **54.7%** within ±25% (vs 69.5% overall)
- **70% overpredicted** (mean bias +0.084 t/ha)

**Root cause:** Range compression from `HistGradientBoostingRegressor(loss='absolute_error')` on the right-skewed yield distribution. The model predicts the conditional median, which shrinks predictions toward the crop mean.

### Correction tested

**Predict `log1p(yield)` instead of `yield`, then `expm1` the predictions.**

Rationale (distinct from Phase 10's failed approaches):
- Phase 10 tested **post-hoc** calibration on already-compressed OOF predictions (variance stretch, isotonic, linear) and a loss-function switch (`squared_error`). All failed — post-hoc calibration overfits per-crop samples, and `squared_error` trades range coverage for tolerance accuracy.
- The log transform is a **target-space** change, not post-hoc calibration. In log space, the yield distribution is approximately symmetric, so `absolute_error` (median) in log space maps to a geometric-median-like estimate that preserves the prediction range. The transform is row-wise with no fitted parameters → **no leakage, no per-crop overfitting**.
- All model fitting happens inside each `GroupKFold(5)` training fold. Baseline and candidate use identical folds and identical rows.

---

## 3. Results

### Overall grouped OOF (n = 4,497 training rows)

| Metric | F3 baseline | F3-log (candidate) | Δ |
|---|---:|---:|---:|
| **Within ±25%** | **69.54%** | 68.87% | **−0.67 pp** |
| Within ±10% | 36.05% | 35.60% | −0.45 pp |
| MAE (t/ha) | 0.2373 | 0.2376 | +0.0003 |
| RMSE (t/ha) | 0.4450 | 0.4451 | +0.0001 |
| R² | 0.9475 | 0.9476 | +0.0002 |
| Bias (t/ha) | −0.0069 | −0.0085 | −0.0016 |

### Per-fold variability (within-25%)

| Fold | F3 baseline | F3-log | Δ |
|---|---:|---:|---:|
| 1 | 66.59% | 66.37% | −0.22 pp |
| 2 | 68.04% | 66.04% | −2.00 pp |
| 3 | 69.44% | 70.56% | +1.11 pp |
| 4 | 74.39% | 72.83% | −1.56 pp |
| 5 | 69.22% | 68.56% | −0.67 pp |
| **Mean ± std** | **69.54 ± 2.63** | 68.87 ± 2.56 | −0.67 pp |

**Only 1 of 5 folds improved.** The change is not consistent.

### Range compression (yield_std / pred_std, lower = better)

| Crop | F3 baseline | F3-log |
|---|---:|---:|
| Sugarcane | 1.377 | 1.361 |
| Rice | 1.146 | 1.123 |
| Maize | 1.449 | 1.471 |
| Cotton | 1.908 | 1.896 |
| Groundnut | 1.221 | 1.223 |

Range compression was **barely reduced** (Sugarcane 1.377 → 1.361). The log transform did not decompress predictions meaningfully because the per-crop `absolute_error` models still predict the median within each crop.

### Subgroup breakdown (within-25%)

| Subgroup | n | F3 baseline | F3-log | Δ |
|---|---:|---:|---:|---:|
| yield < 0.5 t/ha | 1,249 | 54.7% | 54.2% | −0.5 pp |
| year 2003 (drought) | 189 | 51.9% | 50.8% | −1.1 pp |
| year 2016 (drought) | 227 | 49.8% | 48.9% | −0.9 pp |
| Sesamum | 227 | 58.6% | 57.7% | −0.9 pp |
| Pigeonpea | 246 | 59.3% | 58.1% | −1.2 pp |
| Minor Pulses | 269 | 59.9% | 58.0% | −1.9 pp |
| Sugarcane | 252 | 85.3% | 83.3% | −2.0 pp |
| Rice | 273 | 85.0% | 85.0% | 0.0 pp |

No subgroup improved meaningfully. Low-yield rows, drought years, and weak crops all got slightly worse.

---

## 4. Acceptance Gate

| Criterion | Threshold | Result |
|---|---|---|
| Δ within-25% ≥ 1.0 pp | meaningful margin | **−0.67 pp** ✗ |
| Improvement in ≥ 4 of 5 folds | consistency | **1 of 5** ✗ |
| No unacceptable regression (MAE ≤ 1.05×, R² ≥ −0.01) | other metrics | **Pass** ✓ |

**2 of 3 criteria failed → RETAIN F3.**

---

## 5. Why the log transform did not help

1. **Per-crop median prediction persists.** F3 fits a separate `HistGradientBoostingRegressor` per crop. Even in log space, `absolute_error` predicts the per-crop conditional median, which still compresses the range relative to the per-crop yield distribution.

2. **The compressed baseline is already near-optimal for ±25%.** The ±25% tolerance band is narrowest at low yields (where F3 overpredicts) and widest at high yields (where F3 underpredicts). Slight decompression helps the high-yield tail but hurts the much larger low-yield segment, netting negative.

3. **The irreducible error is in the data, not the model.** R² = 0.9475 on OOF means the model already captures nearly all explainable variance in district-level aggregate yields. The residual is dominated by aggregation noise and unmeasured field-level variation.

---

## 6. Data Limitations

1. **Rainfall resolution:** IMD rainfall is at subdivision level (3 subdivisions for 30 districts). District-level ground-observed monthly rainfall was unavailable (Kaggle requires auth; IMD gridded data is in GRD format).
2. **Rainfall temporal coverage:** IMD data ends at 2015; years 2016–2017 use clipped 2015 rainfall (stale features for 2 of 18 years).
3. **Aggregation ceiling:** District-level aggregate yields cannot capture field-level variation. This is the fundamental accuracy ceiling.
4. **Phase 9 confirmed:** ERA5 reanalysis rainfall/temperature features (district-level, full coverage) did not improve the metric.

---

## 7. Final Decision

**RETAIN F3 unchanged.** No measurable, consistent improvement was found.

- **Best verified model:** F3 (Phase 6/8/10 baseline)
- **Baseline vs candidate (grouped OOF within-25%):** 69.54% vs 68.87% (Δ = **−0.67 pp**)
- **Exact improvement:** −0.67 percentage points (candidate is worse)
- **Fold consistency:** 1 of 5 folds improved

---

## 8. Reproduction Command

```bash
cd /Users/apple/SeedIQ/experiments/improved_dataset/phase11
python3 phase11_log_target.py
```

Outputs:
- `results/phase11_oof_predictions.csv` — 4,497 OOF rows (baseline + candidate predictions, residuals)
- `results/phase11_results.json` — all metrics, fold results, subgroup analysis, decision

---

## 9. Files Created

| File | Description |
|---|---|
| `phase11/phase11_log_target.py` | Experiment script (imports F3 building blocks from Phase 10) |
| `phase11/results/phase11_oof_predictions.csv` | OOF predictions for baseline and candidate |
| `phase11/results/phase11_results.json` | Results JSON |
| `phase11/PHASE11_REPORT.md` | This report |

No existing files were modified. No datasets, models, or production code were changed.
