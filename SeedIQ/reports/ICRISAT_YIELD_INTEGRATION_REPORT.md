# ICRISAT Yield Integration — Final Report

**Task:** Integrate the real ICRISAT Karnataka district-level yield dataset into SeedIQ, remove `Season` as a required yield feature, and update every dependent layer consistently.

**Run of record:** `RUN-20261007-200925` (9 registry entries) · reproducibility check `RUN-20261007-184352`
**Status:** Implementation complete. 29/29 verification checks pass (exit 0). 5/5 API probes pass. No source dataset modified. **Nothing committed, pushed, deployed, or built.**

---

## 1. Executive summary

The synthetic yield dataset has been replaced by a real, documented dataset derived from `data/ICRISAT-District Level Data.csv` (Karnataka, 19 districts, 2000–2017). `Season` is no longer a yield feature anywhere in the stack — it was not invented, inferred, or faked. The yield contract is now `Crop + Area_Hectares → Yield_Tonnes` (district total). Training, preprocessing, the Flask API, the quantum module, the model registry, provenance, the published feature manifest, and the Android client all consume the same 23-column, season-less feature frame.

Two consequences are reported honestly rather than papered over:

1. **The meta model dropped from 64.32% to 57.27% test accuracy.** This is a methodology/data change, not a regression to be chased. The yield leg changed from synthetic field-scale rows to real district/year aggregates.
2. **The quantum (VQC) yield model is accurate on district totals but unreliable per hectare.** Classical is therefore the user-facing headline number; quantum is retained and explicitly labelled experimental.

---

## 2. Scope and constraints honored

| Constraint | Status |
|---|---|
| Do not touch crop dataset | ✅ `data/Crop_recommendation.csv` byte-identical |
| Do not touch seed dataset | ✅ `data/seed_viability_data.csv` byte-identical |
| Never overwrite the ICRISAT source | ✅ `data/ICRISAT-District Level Data.csv` byte-identical |
| Never manufacture/infer `Season` | ✅ No `Season` column exists in the derived data or any feature frame |
| Do not change the meta target | ✅ Verified unchanged in code, registry, and `reports/retrain_report.json` |
| Do not claim ICRISAT is field-level | ✅ All provenance/semantics text says district/year/crop aggregate |
| Do not commit / push / deploy / build APK | ✅ None performed |
| No unrelated endpoint changes | ✅ Only yield + quantum-ml yield paths changed |

---

## 3. Phase 1 — Pre-change inspection and baseline snapshot

Before any edit, a SHA-256 snapshot of the 10 load-bearing artifacts was written to `/tmp/hashes_before.json`: the four datasets, `xgb_model.pkl`, `vqc_model.pkl`, `rf_model.pkl`, `meta_model.pkl`, `vqc_yield_model.pkl`, and `yield_prediction/randomforest_model.pkl`. `git status`/`git diff` were recorded at the same time so post-run change attribution is exact (see §16).

---

## 4. Phase 2 — Real ICRISAT dataset construction

`build_icrisat_yield_dataset()` in `train_all_models.py` (≈line 287) reads the wide source and melts the complete `<CROP> AREA`, `<CROP> PRODUCTION`, `<CROP> YIELD` triples into a long table.

**Unit conversions (applied explicitly):**

| Source column | Source unit | Converted to | Operation |
|---|---|---|---|
| AREA | 1000 ha | hectares | ×1000 |
| PRODUCTION | 1000 tons | tonnes | ×1000 |
| YIELD | kg per ha | t/ha | ÷1000 — **cross-check only, not a feature** |

The published YIELD column is used only to validate the area/production consistency; it never becomes a model input and no value is imputed.

**Output:** `data/yield_icrisat_karnataka.csv` with columns `Crop, District, Year, Area_Hectares, Yield_Tonnes`.

**Safety behavior:** the source file is opened read-only; the derived file is never overwritten unless explicitly forced (`force=False` default); validation raises on empty output, duplicate keys, presence of a `Season` column, or missing required values.

| | path | bytes | sha256 (16) |
|---|---|---|---|
| Source (read-only) | `data/ICRISAT-District Level Data.csv` | 207,425 | `e35cb82699fcb34c` |
| Derived (active) | `data/yield_icrisat_karnataka.csv` | 224,521 | `ab26727463a3390d` |

---

## 5. Phase 2b — Measured dataset composition and validation

All figures below are **measured at runtime**, not assumed from the prior audit:

- **5,585 usable rows**
- **22 crops** (23 source crop groups yield 22 with usable area/production)
- **19 districts**
- **18 years, 2000–2017**
- **0 duplicate (District, Crop, Year) keys**
- **0 NaNs** in any required column
- **No `Season` column**
- min `Area_Hectares` = 10.0 ha; min `Yield_Tonnes` = 10.00 t
- classification: `dataset_synthetic = false`, provenance `provided (ICRISAT — ICRISAT-District Level Data.csv)`

**Unit-consistency cross-check** (derived `Yield_Tonnes / Area_Hectares` vs published YIELD ÷1000):

| metric | value |
|---|---|
| median relative error | 2.99e-06 |
| 99th percentile | 0.0525 |
| max | 0.625 |
| rows with >1% deviation | 126 / 5,585 |

The 126 rows are attributed to rounding in the source's published YIELD column, not to a conversion error — the median error is essentially zero.

---

## 6. Phase 3 — Yield contract change

**Old:** `Crop + Season + Area_Hectares → Yield_Tonnes (plot total)`
**New:** `Crop + Area_Hectares → Yield_Tonnes (district total)`

Feature frame = **23 columns**: `Area_Hectares` + one one-hot dummy per crop (22). `drop_first` is off. There is **no** `Season_Rabi`/`Season_Zaid` column and no substitute feature. `Year` and `District` were **not** added — the approved change is the minimum one, and the existing client contract cannot carry `District` without a breaking redesign.

The trained RF reports `n_features_in_ == 23`, and the published manifest agrees.

---

## 7. Phase 4 — `train_all_models.py` changes

Every yield-related path was updated: `ICRISAT_SOURCE_FILENAME`/`YIELD_DERIVED_FILENAME` constants, `build_icrisat_yield_dataset()`, `ensure_datasets()`, the dataset-quality probe's yield branch, `dataset_meta()` (file-identity-based provenance), `load_yield_frame()`, `yield_feature_columns()` / `yield_one_hot()` / `publish_yield_manifest()`, `train_yield()`, and the meta training input construction. Crop and seed training logic were not changed.

**Published manifest** — `models/yield_feature_manifest.json` (1,627 B, sha16 `ed00853b0500a39e`): `feature_columns` (23), `crop_options` (22), `input_schema: [Crop, Area_Hectares]`, `target`, `season_required: false`, `season_deprecated: true`, `dataset`, `dataset_provenance`, `dataset_synthetic: false`, `records: 5585`, `districts: 19`, `years: 18`, and a `semantics` string stating the data is district-level annual aggregate — **not field-level and not live**.

`random_state=42` is used throughout.

---

## 8. Phase 4b — Leakage-safe grouped evaluation

Because the data is district/year aggregate, rows sharing a district-year are correlated evidence and must not be split independently. Two defences were added:

- **Split:** `GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)` grouped by `District|Year`
  → **273 train groups / 69 test groups; 4,423 train rows / 1,162 test rows; zero group overlap (verified).**
- **CV:** `GroupKFold(5)` grouped by district-year (`cv_regressor_grouped`), on TRAIN only.
- **Hyper-parameter selection:** `GridSearchCV` on TRAIN only with `GroupKFold(3)`. Selected `{rf__n_estimators: 200, rf__max_depth: None, rf__min_samples_leaf: 1}`.
- **Preprocessing:** the `StandardScaler` is fitted on TRAIN only — check 26 proves its learned mean matches the train-only statistic and differs from the full-data statistic.

A `DummyRegressor` train-mean baseline is computed so the model's lift over "predict the mean" is explicit.

---

## 9. Phase 4c — Yield metrics (measured, final implementation)

**Yield RF (`yield_prediction/randomforest_model.pkl`, 23 features, 5,585 records):**

| leg | R² | MAE (t) | RMSE (t) |
|---|---|---|---|
| train | 0.9876 | 5,400.9 | 15,977.0 |
| CV (GroupKFold-5) | **0.9068 ± 0.0160** | — | — |
| test | **0.8909** | 17,381.3 | 42,209.6 |
| baseline (train-mean) | **−0.000528** | — | — |

- row count **5,585** · crop count **22** · district count **19** · year count **18**
- provenance `provided (ICRISAT — ICRISAT-District Level Data.csv)` · `dataset_synthetic = false`
- target `Yield_Tonnes (district total)`

**Against the prior reference** (CV ≈ 0.9032, test ≈ 0.9254, baseline ≈ −0.0015): CV is comparable (0.9068), test is lower (0.8909). This is expected — the evaluation target changed from synthetic field-scale rows to real district aggregates and the split is now group-honest. No tuning was performed to chase the old number.

---

## 10. Phase 4d — Full-run metrics, all legs

Run `RUN-20261007-200925`, 9 entries:

| model | leg | train | CV | test |
|---|---|---|---|---|
| crop RF | Crop | 100.00% | 99.26% | 99.32% (F1 99.32) |
| crop VQC | Crop | 92.27% | 86.99% | 87.73% |
| yield RF | Yield (district total) | R² 0.9876 | R² 0.9068 | R² 0.8909 |
| yield GBR (xgb slot) | Yield (district total) | R² 0.9591 | R² 0.9111 | R² 0.9035 |
| yield VQC | Yield (district total) | R² 0.9772 | R² 0.9014 | R² 0.9107 |
| seed RF | Viable | 100.00% | 95.00% | 90.00% |
| seed SVM | Viable | 95.00% | 93.75% | 85.00% |
| seed VQC | Viable | 93.75% | 90.00% | 85.00% |
| meta | Hybrid-stack success | 58.24% | 57.39% | 57.27% (F1 47.48) |

**Dataset scan:** crop `provided` (2,200 rec, input-only CV 0.582); yield `data/yield_icrisat_karnataka.csv` **`provided`** (5,585 rec, 4 features, input-only CV 0.891, 681 duplicate feature vectors); seed `synthetic` (100 rec). `data_integrity`: `synthetic_domains: ["seed"]`, `real_data_domains: ["crop","yield"]`, `synthetic_fallback_allowed: false`.

**Reproducibility:** Run 1 (`RUN-20261007-184352`) and Run 2 (`RUN-20261007-200925`) produced **byte-identical train and test metrics for all 9 entries** (123.4 s run time).

---

## 11. Phase 5 — Meta model handling and provenance

**Target unchanged** (verified in code, registry, and `reports/retrain_report.json`):

> success = crop RF correct **AND** yield classical within ±25% **AND** seed RF correct

Registry `target` string: `"Hybrid-stack success (three user-facing classical outputs correct)"`.

**Composite provenance** now recorded in the meta entry:

```
Stacked OOF/TEST predictions from base models trained on:
  crop  = provided
  yield = provided (ICRISAT — ICRISAT-District Level Data.csv)
  seed  = synthetic-generated
```

A new `dataset_composition` field was added by extending `register_model(dataset_composition=…)` and `train_meta(feature_composition=…)`, written on every registry entry:

```json
{ "crop":  {"provenance": "provided", "synthetic": false},
  "yield": {"provenance": "provided (ICRISAT …)", "synthetic": false},
  "seed":  {"provenance": "synthetic-generated", "synthetic": true},
  "any_synthetic": true,
  "note": "…dataset_synthetic=true above means 'at least one input leg is synthetic', not that the whole stack is synthetic." }
```

**Schema consistency:** the pre-existing boolean rule (`dataset_synthetic = "synthetic" in provenance.lower()`) is unchanged, so the meta entry still reports `dataset_synthetic: true` — it now means *at least one input leg is synthetic (seed), not the whole stack*. This is the existing schema's meaning, restated; no contradictory semantics were invented. Yield entries carry `dataset_composition: null`.

**Methodology change, stated plainly:** the yield leg moved from synthetic field-style data to real district/year aggregate data and the CV scheme moved to grouped folds. The old 64.32% meta test accuracy is **not comparable**. New meta: train 58.24% / CV 57.39% / test 57.27%, F1 47.48, test base rate 0.4364 (CV base 0.4619, lift 0.1119). 96% was not pursued.

---

## 12. Phase 6 — `app.py` changes

All yield feature construction paths were updated to read the published manifest at inference and validate `len(columns) == model.n_features_in_`; on mismatch it falls back to `LEGACY_YIELD_FEATURE_COLUMNS` (7-col, the only place the old `Season_*` dummies remain, for defensive compatibility only).

**`/api/yield-prediction`**
- accepts `{crop, area_hectares}`; `season` is **optional and ignored** (deprecated), producing an explicit note:
  > `season` is deprecated and ignored: the yield model is trained on annual district-level crop statistics and has no season input.
- response shape: `{contract, crops, market_analysis, result}`
- `contract`: `{inputs: ['Crop','Area_Hectares'], season_required: false, season_deprecated: true, crops: [22], dataset, dataset_provenance, dataset_synthetic: false, semantics}`
- `result`: `{classical, quantum, ensemble, quantum_available, quantum_experimental, quantum_note, units: 'tonnes per hectare'}`

**`/api/quantum-ml`** — reads `area_hectares` (falls back to legacy `area`); no `season`.

**Classical-is-user-facing (per your decision):** `ensemble = classical` (previously `(classical + quantum)/2`), and `quantum_experimental`/`quantum_note` were added. Effect on Rice @ 100 ha: `ensemble` dropped from 46.3 t/ha to **3.02 t/ha (= classical)**, quantum 89.59 t/ha still returned but flagged experimental, and `market_analysis.gross_revenue` fell from the inflated **₹101,860,000** to **₹6,644,000**. No unrelated endpoints were touched.

---

## 13. Phase 7 — `qml_model.py`

Verified to contain **no `season` reference** and no hardcoded yield feature assumptions (check 29). The quantum yield path now consumes exactly the same 23-column frame used in training; the projection layer is shaped `(23, 8)`. No fabricated predictions or confidence values were introduced, and existing artifact-loading behavior is preserved.

---

## 14. Phase 8 — Android and i18n

`seediq-mobile/app/yield-ai.tsx` now posts `{crop, area_hectares}`; `season` remains a local UI/report label only. The quantum badge renders **only when non-null** and uses the new key `yieldAi.quantumBadgeExperimental`; the report's `models` array includes quantum only when non-null.

New/updated i18n keys in `en.ts` / `hi.ts` / `kn.ts`:
- `yieldAi.quantumBadgeExperimental` — "Experimental: {value}" / "प्रायोगिक: {value}" / "ಪ್ರಯೋಗಾತ್ಮಕ: {value}"
- `report.modelQuantumVqr` — now appends "(experimental)" / "(प्रायोगिक)" / "(ಪ್ರಯೋಗಾತ್ಮಕ)"

Android DTO field names are unchanged; only the request body changed. `seediq-mobile/app/quantum.tsx` posts `{crop, area_hectares}` (FormData key `area_hectares`, season omitted). `npx tsc --noEmit` → **exit 0**.

---

## 15. Phase 9/10 — Registry and provenance review

Latest run holds 9 entries. Yield entries carry `provided (ICRISAT — ICRISAT-District Level Data.csv)` and `dataset_synthetic: false`. The `xgb_model.pkl` entry records `artifact_written: false` because the real artifact is preserved, not regenerated (XGBoost is unusable on this host — missing `libomp` — so the slot is filled by an sklearn `GradientBoostingRegressor`; the real 30,700,677-byte `xgb_model.pkl` is left untouched). The meta entry carries the composite provenance and the new `dataset_composition` described in §11. Registry is append-only (188 entries).

---

## 16. Phase 11 — Artifact safety (hash table)

`/tmp/hashes_before.json` (SHA-256) vs post-run state:

| artifact | Δ | before B | after B | sha16 |
|---|---|---|---|---|
| `data/ICRISAT-District Level Data.csv` | **UNCHANGED** | 207,425 | 207,425 | `e35cb82699fcb34c` |
| `data/crop_production_karnataka.csv` | **UNCHANGED** | 4,949 | 4,949 | `08e4f54c5cb8c4f4` |
| `data/seed_viability_data.csv` | **UNCHANGED** | 3,886 | 3,886 | `7bf4c361926b49a6` |
| `data/Crop_recommendation.csv` | **UNCHANGED** | 147,833 | 147,833 | `808e1d84a544647f` |
| `models/xgb_model.pkl` | **UNCHANGED** | 30,700,677 | 30,700,677 | `107eafea61136064` |
| `models/vqc_model.pkl` | **UNCHANGED** | 10,937 | 10,937 | `bb195757f8b3fa02` |
| `models/rf_model.pkl` | **UNCHANGED** | 6,780,597 | 6,780,597 | `2a64c17ab40170d2` |
| `models/meta_model.pkl` | CHANGED (expected) | 765 | 1,702 | `90751eace6b5cc7b` |
| `models/vqc_yield_model.pkl` | CHANGED (expected) | 293,686 | 336,899 | `d58b4a6307a1ab9a` |
| `models/yield_prediction/randomforest_model.pkl` | CHANGED (expected) | 195,025 | 72,944,686 | `27c67f777d99fc5f` |

New artifacts (not in pre-snapshot): `data/yield_icrisat_karnataka.csv` (224,521 B), `models/yield_feature_manifest.json` (1,627 B), `reports/retrain_report.json` (16,672 B).

The three CHANGED files are exactly the three the yield retrain is supposed to rewrite; the RF grew because it now holds 200 trees over 5,585 rows × 23 features. Everything else — all four source datasets and the preserved quantum/RF/xgb artifacts — is byte-identical.

**Git scope:** `SeedIQ/data/` has **zero** tracked changes. Modified tracked files are limited to the intended code/models/reports; `seediq-mobile/` is entirely untracked. All four datasets are untouched in git.

---

## 17. Phase 12 — API probes (live Flask, PORT=5099, killed after)

5/5 returned HTTP 200:

| # | request | result |
|---|---|---|
| 1 | `POST /api/yield-prediction` season-less | 200 |
| 2 | `POST /api/yield-prediction` with `season=Rabi` | 200 |
| 3 | `POST /api/yield-prediction` legacy `{crop, area}` | 200 |
| 4 | `POST /api/quantum-ml` with `area_hectares` | 200 |
| 5 | `GET /api/model_metrics` | 200 |

Season-less vs season-supplied responses produce **identical predictions** — the only difference is the added deprecation note in `result.error`. This confirms `season` is accepted-but-ignored, not silently consumed.

---

## 18. Phase 13 — Verification suite

`/tmp/verify_icrisat.py` (needs `sys.path.insert(0, os.getcwd())` to unpickle `qml_model`-referencing artifacts):

> **SUMMARY: 29/29 checks passed — exit 0**  (output: `/tmp/verify_out2.txt`)

Coverage: source exists + SHA unchanged; derived exists with 5,585 rows / 0 dupes / 22 crops / 19 districts / 18 years 2000–2017; no `Season` column; no NaNs; positive area and yield; unit conversions matched 5,585/5,585 rows; manifest 23 cols with no Season; `input_schema` `[Crop, Area_Hectares]`; `season_required=false` / `season_deprecated=true`; dataset = ICRISAT-derived with `synthetic=false`; semantics states district-level / NOT field-level / NOT live; 22 `crop_options`; RF `n_features_in_ == 23`; pipeline steps `['scaler','rf']`; VQC projection shape `(23, 8)`; xgb SHA unchanged; meta artifact loads as `DecisionTreeClassifier`; latest-run yield entries ICRISAT + `synthetic=false`; meta composite provenance + composition; meta target unchanged; grouped split zero overlap; scaler fitted on TRAIN only; no fabricated `96.1%`/`94.2%`/live-telemetry strings; `app.py` builds no Season column; `qml_model.py` has no `season` reference.

Also passing: `python3 -m py_compile app.py train_all_models.py data_preprocessing.py` → OK; `npx tsc --noEmit` → exit 0.

---

## 19. Phases 14/15 — Limitations, honest disclosures, and remaining gaps

1. **The data is district/year/crop aggregate — not field-level, not season-resolved, not live.** It covers Karnataka 2000–2017 only. Predictions are estimates of annual district totals, and the API/manifest text says so explicitly.
2. **The quantum yield model is unreliable per hectare.** On district totals it is fine (grouped test R² 0.9107, MAE 16,377 t), but its per-hectare output has a test R² of **−102.16** (MAE 3.265 t/ha vs the RF's 0.416). Area-stratified test per-ha MAE — `<500 ha`: **VQC 19.203** vs RF 0.274; `500–5000 ha`: 0.911 vs 0.481; `>5000 ha`: 0.420 vs 0.426. Cause: the model predicts totals with a positive intercept, so dividing by small areas explodes (VQC per-ha predictions span −62.5 to +1,174.6 across all rows; RF spans 0.094–11.586). Real Rice per-ha median is 2.545 t/ha (n=342). This is why **classical is the user-facing figure and quantum is labelled experimental** — a disclosure, not a fix. A per-hectare-native quantum model is future work.
3. **Meta accuracy is not comparable to the prior run** (64.32% → 57.27%) because the yield leg's data and the CV scheme both changed. Documented as a methodology/data change; 96% was not chased.
4. **The seed leg remains synthetic.** `dataset_integrity` reports `synthetic_domains: ["seed"]` and `synthetic_fallback_allowed: false`, and the meta entry warns that seed metrics are synthetic. Meta `dataset_synthetic: true` reflects that (at least one leg), per the existing schema.
5. **`models/yield_season_encoder.pkl` is a stale legacy artifact** and is never read. It is left in place; nothing depends on it.

---

## Deliverables

| artifact | note |
|---|---|
| `data/yield_icrisat_karnataka.csv` | new derived dataset, 5,585 rows |
| `models/yield_feature_manifest.json` | new published contract manifest |
| `models/yield_prediction/randomforest_model.pkl` | retrained, 23 features |
| `models/vqc_yield_model.pkl` | retrained, projection (23, 8) |
| `models/meta_model.pkl` | retrained on the new yield leg |
| `reports/retrain_report.json` | run of record with derivation + integrity |
| `training_registry.json` | +9 entries (`RUN-20261007-200925`) |

**Nothing was committed, pushed, deployed, or built.** The work is on disk for your review.
