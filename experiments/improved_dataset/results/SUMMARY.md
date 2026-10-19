# SeedIQ — Enriched Dataset + Experimental Retrain Summary

_Generated 2026-10-09T15:25:56Z_

## Dataset

- Rows (after join coverage drop): **5585**
- Feature width: **56** (Area_Hectares + log_area + year + soil NPK/pH/OC/one-hot + 12-month/quarterly/annual rainfall normals + crop dummies)
- Join: ICRISAT yield (5585 district×crop×year) ⟵ soil (31 districts) ⟵ IMD rainfall normals (30 Karnataka districts, one imputed from parent).
- Target: **yield_per_hectare = Yield_Tonnes / Area_Hectares** (tonnes/ha, matches ±25% tolerance and API units).
- Split: GroupShuffleSplit(0.2) on (District, Year) → 4476 train district-years / 1109 test district-years; groups are disjoint.

## Yield model — CV selection (GroupKFold(5) by district-year on TRAIN)

| Candidate | OOF ±25% | OOF R² |
|---|---|---|
| hgb_500_log | 66.76% | +0.9363 |
| gb_300_log | 65.60% | +0.9357 |
| rf_300_log | 65.00% | +0.9244 |
| et_400_log | 63.69% | +0.9148 |
| ridge_log | 50.23% | +0.8501 |
| crop_geomean_ref | 49.79% | +0.8547 |

## Yield model — untouched TEST split (evaluated once)

| Candidate | TEST ±25% | TEST R² | TEST MAE | TEST RMSE |
|---|---|---|---|---|
| hgb_500_log | 62.68% | +0.9439 | 0.2652 | 0.4730 |
| gb_300_log | 62.50% | +0.9401 | 0.2784 | 0.4885 |
| rf_300_log | 62.04% | +0.9343 | 0.2802 | 0.5118 |
| et_400_log | 61.86% | +0.9308 | 0.2863 | 0.5252 |
| crop_geomean_ref | 46.88% | +0.8824 | 0.3968 | 0.6846 |
| ridge_log | 45.50% | +0.8796 | 0.3981 | 0.6929 |

### Baseline comparison (from prior, 23-feature contract models)

- Baseline contract (23 features): within ±25% **49.74%**
- Prior best candidate (23 features + area rank shrunk): **51.46%**
- **Enriched dataset best (hgb_500_log): 62.68%**
- Δ over baseline contract: **+12.94 pp**
- TEST R²: +0.9439 | MAE: 0.2652 | RMSE: 0.4730

## Component marginals + joint-metric status

- Crop accuracy (unchanged Kaggle dataset, 99.32% in prior untouched test)
- Yield within ±25% enriched dataset TEST: **62.68%**
- Seed accuracy (unchanged 100 synthetic rows, 90.00%; labels are deterministic rule NOT measured)
- Independence product (assumption, NOT a measurement): 56.03%

**Joint accuracy: NOT EVALUABLE.**

The three test populations (crop recs, enriched yield district×year rows, seed viability) still describe unrelated samples: no shared plot / farm / sample_id join key exists. Per-crop alignment (join on Crop name) would pair a 'Rice soil NPK rec' row with a 'Rice Karnataka district-year' yield row — different populations, not the same underlying observation.  Reporting a joint rate would be fabrication.

- Even with yield perfect, crop 99.32% × seed 90.00% → 89.39% < 90% (independence bound, not measured).

## Best-model per-crop TEST coverage

| Crop | Rows | ±25% | True med t/ha | Pred med t/ha |
|---|---:|---:|---:|---:|
| Sesamum | 58 | 43.1% | 0.472 | 0.423 |
| Soyabean | 23 | 43.5% | 1.000 | 0.785 |
| Linseed | 23 | 47.8% | 0.316 | 0.282 |
| Sorghum | 51 | 51.0% | 1.035 | 1.002 |
| Wheat | 33 | 51.5% | 1.000 | 0.961 |
| Kharif Sorghum | 49 | 53.1% | 1.164 | 1.179 |
| Safflower | 30 | 53.3% | 0.586 | 0.658 |
| Rapeseed and Mustard | 33 | 54.5% | 0.288 | 0.299 |
| Pigeonpea | 57 | 56.1% | 0.470 | 0.507 |
| Cotton | 49 | 57.1% | 0.300 | 0.287 |
| Pearl Millet | 35 | 57.1% | 0.737 | 0.711 |
| Rabi Sorghum | 48 | 62.5% | 0.798 | 0.819 |
| Sunflower | 58 | 63.8% | 0.567 | 0.556 |
| Oilseeds | 57 | 64.9% | 0.633 | 0.644 |
| Minor Pulses | 68 | 66.2% | 0.354 | 0.386 |
| Castor | 48 | 66.7% | 0.800 | 0.748 |
| Groundnut | 67 | 67.2% | 0.791 | 0.707 |
| Finger Millet | 43 | 67.4% | 1.556 | 1.388 |
| Chickpea | 58 | 69.0% | 0.598 | 0.536 |
| Maize | 65 | 70.8% | 2.871 | 2.886 |
| Sugarcane | 66 | 81.8% | 8.361 | 8.101 |
| Rice | 69 | 84.1% | 2.494 | 2.430 |

## What was NOT changed (safety scope)

- Production models under `SeedIQ/models/` were NOT overwritten.
- `train_all_models.py`, `app.py`, Android payload and served contracts are unchanged.
- Joint metric remains NOT EVALUABLE (the required plot-level shared sample key does not exist locally).
- No APK, no Railway deploy, no model upload.

## Files written (experiments/improved_dataset/)

- `data/enriched_yield_karnataka.csv` — joined dataset (yield+soil+rainfall, target yield_per_hectare, all features).
- `models/yield_enriched_feature_manifest.json` — fixed feature order and width.
- `models/yield_best_hgb_500_log.pkl` — best candidate fitted object.
- `results/enriched_yield_predictions.npz` — best test predictions and aligned ground truth for audit.
- `results/cv_results.json` — CV per-candidate ranking.
- `results/provenance.json` — complete audit trail: sources, joins, splits, metrics.
- `results/summary.json` — machine-readable headline summary.
- `results/SUMMARY.md` — this human-readable report.
