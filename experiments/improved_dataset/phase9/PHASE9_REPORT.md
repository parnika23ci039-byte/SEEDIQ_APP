# Phase 9 Report — Weather-Enhanced Yield Prediction

**Date:** 2026-10-11
**Objective:** Improve the F3 yield-prediction baseline using genuine historical weather data from Open-Meteo.
**Outcome:** Weather features did **not** improve the model. The unchanged F3 baseline remains the best validated candidate.

---

## 1. Verified Baseline (F3, Phase 6)

The baseline was reproduced exactly against the frozen holdout split:

| Metric | Value |
|---|---|
| Rows evaluated | 1,088 |
| Within ±25% | **742 / 1,088 = 68.1985%** |
| Within ±10% | 395 / 1,088 = 36.3051% |
| MAE | 0.2378 t/ha |
| RMSE | 0.4045 t/ha |
| R² | 0.9589 |

**Definition of tolerance metrics:** A prediction is "within ±X%" when `|pred − true| / max(|true|, 1e-12) ≤ X`. Near-zero actual yields are handled by the `1e-12` floor; no rows are excluded.

The F3 structure: `0.8 × HistGBR(base_features) + 0.2 × HistGBR(base + subdivision dynamic rainfall)`, with Chickpea predictions replaced by a RandomForest specialist (`n_estimators=300, max_depth=8`).

Split: `GroupShuffleSplit(test_size=0.2, random_state=42)` on `District|Year` groups. No group overlap between train and holdout.

---

## 2. Weather Data (Open-Meteo ERA5)

| Property | Value |
|---|---|
| Source | Open-Meteo Historical Weather API (Archive endpoint) |
| Dataset | ERA5 (ECMWF Reanalysis v5) |
| Districts | 19 Karnataka districts |
| Date range | 2000-01-01 to 2017-12-31 (6,575 days/district) |
| Variables | `precipitation_sum` (mm), `temperature_2m_max/min/mean` (°C) |
| Missing values | 0 / 124,925 (0.000%) |
| Duplicate dates | 0 |

**Coordinates:** District headquarters (well-documented geographic coordinates).

**Limitation (stated accurately):** Open-Meteo ERA5 is reanalysis/weather-model data, **not** guaranteed ground-station observations. ERA5-Land precipitation returned `None` for Karnataka grid points, so ERA5 was used for all variables for consistent coverage. Spatial resolution ≈ 0.25° (~31 km).

**Raw data:** `phase9/data/raw_weather/{district}.json` (one JSON per district, full API response).
**Processed data:** `phase9/data/openmeteo_daily_weather_karnataka.csv` (124,925 daily rows).
**Provenance:** `phase9/data/openmeteo_weather_provenance.json`.

---

## 3. Engineered Weather Features (15)

All features aggregated from daily to **District-Year**:

| Feature | Unit | Agronomic rationale |
|---|---|---|
| `wx_annual_rain` | mm | Total annual water availability |
| `wx_kharif_rain` | mm | Southwest monsoon (Jun-Sep) rainfall — main Kharif growing season |
| `wx_rabi_rain` | mm | Northeast monsoon (Oct-Dec) rainfall — Rabi season |
| `wx_summer_rain` | mm | Pre-monsoon (Mar-May) rainfall |
| `wx_winter_rain` | mm | Winter (Jan-Feb) rainfall |
| `wx_annual_tmean` | °C | Mean annual temperature — heat/cold stress |
| `wx_kharif_tmean` | °C | Kharif-season mean temperature |
| `wx_rabi_tmean` | °C | Rabi-season mean temperature |
| `wx_annual_tmax` | °C | Mean daily max — heat exposure |
| `wx_annual_tmin` | °C | Mean daily min — cold exposure |
| `wx_rainy_days` | count | Days with precip ≥ 2.5 mm — rainfall distribution |
| `wx_extreme_rain_days` | count | Days with precip ≥ 50 mm — flood/damage risk |
| `wx_max_daily_rain` | mm | Single-day extreme rainfall |
| `wx_gdd_base10` | °C-days | Growing degree days (Σ max(0, tmean−10)) — heat accumulation |
| `wx_diurnal_range` | °C | Mean(tmax−tmin) — temperature variability |

Season definitions use standard Indian meteorological seasons (not invented crop calendars).

**No leakage:** All weather features are historical observations for the same District-Year as the yield target. No future weather, production, or post-harvest information is used.

---

## 4. Candidate Comparison

All candidates use the identical 1,088-row frozen holdout and the same grouped CV protocol (GroupKFold(5) on training District-Year groups).

| # | Candidate | ±25% | ±10% | MAE | RMSE | R² | Δ±25% (pp) | CV ±25% |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A | **F3 baseline (unchanged)** | **68.20%** | 36.31% | 0.2378 | 0.4045 | 0.9589 | **0.00** | 69.54% |
| B | F3 + weather (both branches) | 63.51% | 32.44% | 0.2576 | 0.4279 | 0.9541 | −4.69 | 65.62% |
| C | F3 + weather + rainfall anomaly | 63.97% | 33.09% | 0.2576 | 0.4357 | 0.9524 | −4.23 | 66.49% |
| D | Weather only in B branch (A unchanged) | 67.10% | 35.85% | 0.2375 | 0.4008 | 0.9597 | −1.10 | 69.40% |
| E | Weather in B, Chickpea RF on A | 67.10% | 35.66% | 0.2379 | 0.4010 | 0.9597 | −1.10 | 69.40% |
| F | B = base + district wx (no subdivision dyn_rain) | 66.91% | 35.48% | 0.2405 | 0.4031 | 0.9592 | −1.29 | 69.40% |
| G | Global Ridge residual correction | 65.72% | 32.90% | 0.2439 | 0.4049 | 0.9589 | −2.48 | 67.18% |
| H | Crop-specific Ridge residual correction | 65.44% | 33.46% | 0.2402 | 0.3947 | 0.9609 | −2.76 | 67.78% |

**Best validated candidate: A (unchanged F3 baseline) at 68.20% within ±25%.**

### CV fold variability (within-25% per fold, candidate A)

```
Fold 1: 66.59%   Fold 2: 68.04%   Fold 3: 69.44%   Fold 4: 74.39%   Fold 5: 69.22%
Mean: 69.54%   Std: 2.63%
```

The baseline is stable across folds. Weather-augmented candidates (B, C) showed lower mean CV scores with comparable variability, confirming the degradation is not a single-fold artifact.

---

## 5. Why Weather Did Not Help

1. **Weak overall signal.** All 15 weather features have |correlation with yield| < 0.10 across the full dataset. Yield is dominated by crop type and district effects, which the existing features already capture.

2. **ERA5 vs. IMD rainfall mismatch.** ERA5 district-level annual rainfall correlates only **0.32–0.65** with the existing IMD subdivision-level rainfall *within* each subdivision. This suggests ERA5's ~31 km grid may not resolve Karnataka's complex topography (Western Ghats) accurately enough to beat the coarser but ground-station-based IMD subdivision data.

3. **Crop-specific overfitting.** The F3 model trains one HistGBR per crop (15–340 training rows/crop). Adding 15 weather features to these small datasets causes overfitting, especially for Chickpea (RF specialist dropped from 72.4% to 62.1%) and Safflower (73.3% → 53.3%).

4. **Residual correction also failed.** Even using weather only to correct F3's OOF residuals (Ridge, both global and per-crop) degraded performance, confirming the weather signal is too weak/noisy to extract a useful correction.

---

## 6. Per-Crop Baseline Performance (Candidate A)

Selected crops (full breakdown in `phase9_consolidated_results.json`):

| Crop | ±25% | Crop | ±25% |
|---|---:|---|---:|
| Sugarcane | 89.39% | Pigeonpea | 54.39% |
| Rice | 86.96% | Cotton | 55.10% |
| Rapeseed/Mustard | 81.82% | Pearl Millet | 57.14% |
| Chickpea | 72.41% | Kharif Sorghum | 57.14% |
| Groundnut | 70.15% | Soyabean | 52.17% |

The weakest crops (Soyabean 52%, Pigeonpea 54%, Cotton 55%) are the most challenging; weather did not improve them.

---

## 7. Data Limitations & Client Target

**Client target (high accuracy, e.g., 90% within ±25%) is NOT supported by the current evidence.**

The F3 baseline at 68.20% is near the practical ceiling for this dataset. Key bottlenecks:

- **Aggregate data.** Yield is district-level annual production / area, not field-level. District averages smooth out the weather signal that would drive field-level predictions.
- **Weak weather signal.** Year-to-year weather variation explains little of the remaining yield variance after crop+district effects are removed.
- **Limited samples per crop.** 22 crops with 120–340 rows each constrain model complexity.

**Additional data needed to reach higher accuracy:**
1. **Field-level or block-level yield records** (not just district aggregates) — to capture local weather-yield relationships.
2. **Higher-resolution weather** (e.g., IMD gridded 0.25° or 0.5° rainfall, or station data) — ERA5 may not resolve Karnataka's microclimates.
3. **Soil moisture / irrigation data** — water availability, not just rainfall, drives yield.
4. **Crop calendars and sowing dates** — to align weather with actual growing windows per crop-district.
5. **More years** — 18 years (2000–2017) limits temporal weather variation per district.

---

## 8. Files Created

### Scripts
- `phase9/fetch_weather.py` — Open-Meteo data retrieval with validation
- `phase9/phase9_weather_yield.py` — Main experiment (candidates A, B, C)
- `phase9/phase9_variants.py` — Conservative integration variants (D, E, F)
- `phase9/phase9_residual.py` — Residual-correction variants (G, H)

### Data
- `phase9/data/openmeteo_daily_weather_karnataka.csv` — 124,925 daily rows (19 districts × 6,575 days)
- `phase9/data/openmeteo_weather_provenance.json` — Full provenance metadata
- `phase9/data/raw_weather/*.json` — 19 raw API responses

### Results
- `phase9/results/phase9_weather_yield_results.json` — Candidates A, B, C
- `phase9/results/phase9_variant_results.json` — Candidates D, E, F
- `phase9/results/phase9_residual_results.json` — Candidates G, H
- `phase9/results/phase9_feature_coverage_report.json` — Feature definitions, units, coverage
- `phase9/results/phase9_consolidated_results.json` — All candidates consolidated

### Report
- `phase9/PHASE9_REPORT.md` — This report

**No existing models, datasets, or experiment outputs were modified.**

---

## 9. Reproduction Commands

```bash
cd /Users/apple/SeedIQ/experiments/improved_dataset/phase9

# 1. Fetch weather data (19 districts, 2000-2017)
python3 fetch_weather.py

# 2. Main experiment (A, B, C) — baseline reproduction + weather features
python3 phase9_weather_yield.py

# 3. Conservative integration variants (D, E, F)
python3 phase9_variants.py

# 4. Residual-correction variants (G, H)
python3 phase9_residual.py
```

---

## 10. Final Summary

1. **Verified baseline:** F3 = 742/1,088 = **68.20%** within ±25%, MAE=0.2378, RMSE=0.4045, R²=0.9589. Reproduced exactly.

2. **Best candidate's measured metrics:** Unchanged F3 baseline — 68.20% within ±25%, 36.31% within ±10%, MAE=0.2378 t/ha, RMSE=0.4045 t/ha, R²=0.9589.

3. **Absolute improvement:** **+0.00 pp** (no weather candidate beat the baseline). The best weather candidate (D) was −1.10 pp.

4. **MAE/RMSE/R² changes vs. baseline:** Best weather candidate (D) had MAE −0.0003, RMSE −0.0037, R² +0.0008 — marginal regression-metric changes but worse tolerance accuracy.

5. **Grouped CV consistency:** Baseline CV mean 69.54% (std 2.63%). All weather candidates had lower CV means (65.62%–69.40%), so the holdout degradation is confirmed by CV, not a split artifact.

6. **Client target support:** The 90% target is **not supported** by current data. District-level aggregate yield + weak weather signal caps accuracy near 68%. Field-level data, higher-resolution weather, and soil moisture are needed.

7. **Remaining blockers:** (a) ERA5 weather signal too weak/noisy for this dataset; (b) aggregate (district-level) targets dilute weather-yield relationships; (c) limited per-crop sample sizes prevent complex weather-feature models.
