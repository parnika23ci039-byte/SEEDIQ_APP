# SeedIQ Phase 13 — Reproducibility and Data-Driven Improvement

**Prepared:** 2026-10-11  
**Role:** senior ML engineer  
**Status:** complete, read-only on prior artifacts  
**Previous phase:** Phase 12 (`experiments/improved_dataset/phase12/`)  

**Objective:** establish a reproducible production baseline and identify the single highest-value next data improvement, using only existing evidence. No new model experiments, no package installs/downloads, no overwrite of the production model or Phase 12 results.

---

## Task 1 — Environment discrepancy

### 1.1 Three environments are in play

| Role | Python | scikit-learn | numpy | pandas | Where recorded |
|---|---|---|---|---|---|
| Training/evaluation track (Phase 9–12 headline numbers) | 3.14.6 | 1.9.1 | 2.5.3 | 3.0.6 | Phase 12 results JSON, `environment.*` |
| Pinned serving stack (requirements.txt) | 3.9.6 locally; 3.11.17 on Railway | 1.6.1 | 2.0.2 | 2.3.3 | `SeedIQ/requirements.txt`, Phase 13 results JSON |
| Training provenance for the served artifact | not recorded | embedded in pickle = 1.6.1 | — | — | pickle bytes + Phase 13 results JSON |

The evaluation track and the serving stack are **different scikit-learn versions**. They are not interchangeable: the committed production artifact does not even load under the newer stack.

### 1.2 Artifact compatibility

- `SeedIQ/models/yield_prediction/randomforest_model.pkl`
  - sha256: `2ab7377c8e97fe4bcdbdf7205425947c2d961fbb729aa1bc7dab7d756413906b`
  - embedded sklearn version in pickle: `1.6.1`
  - class: `yield_model.LogPerHaRegressor`
  - wrapped regressor: `HistGradientBoostingRegressor(loss=squared_error, max_iter=400, learning_rate=0.08, random_state=42)`
  - loads under the pinned stack: **yes**, smoke predict OK (1000 ha rice → 1999.86 total tonnes)
  - loads under the evaluation stack (sklearn 1.9.1 via `/usr/local/bin/python3`): **no**, `ModuleNotFoundError: No module named '_loss'`
- `SeedIQ/models/crop_recommendation/randomforest_model.pkl`
  - `RandomForestClassifier(random_state=42)`, 7 features, 5 classes
  - loads under the pinned stack with an sklearn version inconsistency warning (pickled under 1.9.0, loaded under 1.6.1) — loads, but provenance-inconsistent
- `SeedIQ/models/seed_viability/randomforest_model.pkl`
  - `RandomForestClassifier(class_weight='balanced', max_depth=6, n_estimators=200, n_jobs=-1, random_state=42)`, 2 features `Moisture_Level, Weight_g`, classes `[0, 1]`
  - loads under pinned stack, same sklearn version warning
- `SeedIQ/models/meta_model.pkl`
  - `RandomForestClassifier(max_depth=3, min_samples_leaf=5, n_estimators=100, random_state=42)`, 6 features, classes `[0, 1]`
  - loads under pinned stack; **no feature names stored**; sklearn version warning present
  - trained with synthetic/rule-generated binary labels (see below), not a real outcome

### 1.3 Was the production yield model trained with the same code/data/schema as the evaluated F3?

**No.** Phase 13 documents the following verified differences:

| Aspect | Production model | Evaluated F3 |
|---|---|---|
| Training code | `SeedIQ/train_all_models.py::train_yield -> make_yield_model()` | `experiments/improved_dataset/phase10/phase10_error_analysis.py::f3_oof` |
| Model class and loss | `LogPerHaRegressor` wrapping `HistGradientBoostingRegressor(loss=squared_error, max_iter=400, lr=0.08)` on `log(Yield_Tonnes/Area_Hectares)` | per-crop `HistGradientBoostingRegressor(loss=absolute_error, max_iter=200, lr=0.05, depth=6)` blend `0.8*A + 0.2*B`, Chickpea RF specialist; raw t/ha target |
| Data file | `SeedIQ/data/yield_icrisat_karnataka.csv` (5,585 rows; source-district names) | `experiments/improved_dataset/data/enriched_yield_karnataka.csv` (5,585 rows; renamed districts + soil/rain/year features) |
| Feature schema | 23 columns: `Area_Hectares` + 22 crop dummies, no District/Year/soil/rain | 56 base columns (63 with dynamic rainfall): district-conditioned features |
| Target | `Yield_Tonnes` (district total) | `yield_per_hectare` (from log fit, exp inverse) |
| Evaluation protocol | GroupShuffleSplit(0.2, rs=42) on (District, Year); GroupKFold(5) CV on train; metrics on total tonnes (R²) | same splitter family but different label spellings → different groups; grouped OOF on train + frozen holdout; metrics on ±25% t/ha |
| Holdout rows | 1162 test rows, 69 test groups (registry: 4423 train / 1162 test) | 1088 test rows, 69 test groups (Phase 9–12) |
| Test group overlap | 10 groups overlap | — |
| Registry test R² (tonnes) | ≈ 0.9088 | — |
| F3 holdout ±25% (t/ha) | — | 68.1985% |

The district-name spellings differ between the two tables, so even with identical splitter parameters the seeded permutation selects different district-year groups. Therefore the two holdouts are not the same rows, and the two models are not directly comparable.

**Verdict:** the served production yield model is **not** the same artifact as the F3 evaluated through Phase 9–12. The Phase 9–12 numbers describe an experimental per-crop model, not the production model.

### 1.4 Were Phase 9–11 improvement claims valid under a single consistent environment?

**Internally, yes; across stacks, not established.**

- Phase 9–11 JSON results **do not record an interpreter/library version**.
- Their shared baseline constants (69.5352% OOF, 742/1088 holdout) reproduce **only** on the evaluation stack (py3.14.6 / sklearn 1.9.1). The pinned serving stack gives 68.4679% OOF / 740 holdout on the identical code.
- That means all three phases ran on **one consistent environment** (the newer stack), so their relative deltas are internally valid there.
- What does **not** transfer:
  - The absolute metric levels (the serving stack scores lower by ~1.07 pp OOF and 2 rows on holdout)
  - Any delta smaller than the measured stack gap, unless re-measured under one pinned stack

Phase 12 measured one candidate under both stacks: +0.267 pp on the evaluation stack vs +0.222 pp on the pinned stack — suggesting deltas are more stable than levels, but n=1. Phase 13 deliberately does **not** run new candidates, so no Phase 9–11 claim is certified under the serving stack here.

### 1.5 Training provenance gap

- Neither `training_registry.json` nor the registry's per-run records record the training Python/library versions.
- The only machine-readable training provenance for the served artifact is the sklearn version embedded in the pickle (1.6.1).
- This is a real gap: we know the artifact's sklearn version but not the full training environment.

---

## Task 2 — Reproducible baseline

### 2.1 Chosen environment

**Pinned serving stack**, because it is the only local environment under which the committed production artifact unpickles, and it is already installed — no package change.

Recorded versions:

- executable: `/Users/apple/SeedIQ/.freebuff/venv/bin/python`
- Python: 3.9.6
- scikit-learn: 1.6.1
- numpy: 2.0.2
- pandas: 2.3.3
- scipy: 1.13.1
- platform: macOS-15.7.9-x86_64-i386-64bit

Dependency files:

- `SeedIQ/requirements.txt` — pins numpy 2.0.2, pandas 2.3.3, scipy 1.13.1, scikit-learn 1.6.1, xgboost 2.1.4, joblib 1.5.3; comment explains the pin exists because committed artifacts were serialized with sklearn 1.6.1 and sklearn >= 1.7 removed the private `_loss` module the yield pickle references
- root `.python-version`: 3.11.17 (Railway)
- root `requirements.txt`: `-r SeedIQ/requirements.txt`

Residual risk, recorded not ignored: the local venv is Python 3.9.6 with the same pinned numeric stack as the Railway 3.11.17 deployment; the Python minor differs but the sklearn/numpy/pandas/scipy pins match.

### 2.2 What was rerun

Two deterministic F3 runs using:

- data: `experiments/improved_dataset/data/enriched_yield_karnataka.csv`
- seed: 42
- folds: `GroupKFold(5)` on `District|Year` for OOF, plus `GroupShuffleSplit(test_size=0.2, random_state=42)` holdout
- evaluation code: read-only import of `phase10_error_analysis.f3_oof / f3_predict`

The two runs are independent Python process invocations with identical inputs, not two predictions from the same fitted object.

### 2.3 Grouped OOF — kept separate from holdout

| Metric | Run 1 | Run 2 | Identical? |
|---|---|---|---|
| rows | 4497 | 4497 | — |
| within ±25% | 3079 / 4497 = 68.4679% | 3079 / 4497 = 68.4679% | yes |
| within ±10% | 1606 / 4497 = 35.7127% | 1606 / 4497 = 35.7127% | yes |
| MAE (t/ha) | 0.243649 | 0.243649 | yes |
| MSE (t/ha) | 0.213202 | 0.213202 | yes |
| RMSE (t/ha) | 0.461738 | 0.461738 | yes |
| R² | 0.943466 | 0.943466 | yes |
| bias | −0.005511 | −0.005511 | yes |
| max abs prediction deviation | 2.22e-16 | 2.22e-16 | yes (identical within 1e-12) |

### 2.4 Frozen holdout — kept separate from OOF

| Metric | Run 1 | Run 2 | Identical? |
|---|---|---|---|
| rows | 1088 | 1088 | — |
| within ±25% | 740 / 1088 = 68.0147% | 740 / 1088 = 68.0147% | yes |
| within ±10% | 399 / 1088 = 36.6728% | 399 / 1088 = 36.6728% | yes |
| MAE (t/ha) | 0.238545 | 0.238545 | yes |
| MSE (t/ha) | 0.166196 | 0.166196 | yes |
| RMSE (t/ha) | 0.407671 | 0.407671 | yes |
| R² | 0.958313 | 0.958313 | yes |
| bias | −0.012377 | −0.012377 | yes |
| max abs prediction deviation | 2.22e-16 | 2.22e-16 | yes (identical within 1e-12) |

### 2.5 Reproducibility verdict

**Pass.** On the pinned serving stack, F3 rerun twice with identical data, seed, folds, and evaluation code produces identical predictions and identical metrics within numerical tolerance for both the grouped OOF and the frozen holdout. Each is reported separately and never merged.

Note: these numbers (68.4679% OOF / 740 holdout) are the **pinned-stack** values, which are lower than the 69.5352% / 742 headline from the evaluation stack. This is the environment effect documented in Task 1.

---

## Task 3 — Highest-value next data improvement

### 3.1 Source and method

Read-only analysis of Phase 12 results: `experiments/improved_dataset/phase12/results/phase12_results.json`.

- total OOF rows: 4497
- total failures: 1370
- overall pass rate: 69.5352% within ±25%

The three largest failure clusters:

1. **Actual yield < 0.5 t/ha** — 1315 rows, 601 failures, 43.9% of all failures, 54.3% pass rate, 70% overpredicted, mean bias +0.087 t/ha. Upper bound if this subgroup reached the overall rate: +4.45 pp.
2. **Drought/shock years 2003 + 2016 + 2017** — 669 rows, 301 failures, 22.0% of all failures, pass rates 49.8–62.1%. Upper bound: +2.16 pp. The 2016–2017 subset also carries the forward-filled 2015 rainfall defect (480 OOF rows, 210 failures).
3. **Five weakest rainfed crops (Sesamum, Pigeonpea, Minor Pulses, Safflower, Linseed)** — 970 rows, 387 failures, 28.2% of all failures. Upper bound: +2.02 pp.

These bounds are **upper limits, not predictions**, and the subgroups overlap (the weak crops and the shock years sit inside the <0.5 t/ha band), so they must not be summed.

### 3.2 What is already available

All of the following are **already on disk and were already measured**:

- `experiments/improved_dataset/phase9/data/openmeteo_daily_weather_karnataka.csv` — ERA5 district daily rainfall+temperature, 19 districts, 2000–2017, 124,925 rows. Already measured in Phase 9; candidates B/C/D/E/F all regressed the holdout (−1.10 to −4.69 pp). It is reanalysis, not observed ground truth, and as-is does not add value.
- `SeedIQ/data/rainfall in india 1901-2015.csv` — IMD subdivision rainfall 1901–2015, 3 Karnataka subdivisions; already used by F3 branch B (20% weight); ends 2015.
- `SeedIQ/data/district wise rainfall normal.csv` — district long-term rainfall normals (static); already the static `rain_*` features in F3.
- Soil CSV + ICRISAT area/production tables — already the label + area feature. Same-year other-crop yields are target-derived (not pre-harvest usable); lagged own yields were screened in Phase 12 and measured −3.14 pp.

### 3.3 What must be collected

1. **District-resolution observed monthly rainfall for the target year, including 2016–2017**
   - Exact source: India Meteorological Department district rainfall data; the convenience mirror identified in Phase 11 is Kaggle dataset `dhamur/monthly-district-avg-rainfall-19012017indiacsv` (1901–2017 monthly district averages).
   - Dependency requirement: **none new** — CSV read with the already-pinned pandas. Only prerequisite is Kaggle API credentials (a Phase 11 blocker) or direct IMD open-data download.
   - Status: not downloaded in this phase.
   - What it fixes: removes the `Year.clip(upper=2015)` forward-fill defect (10.04% of all rows), and feeds the three worst years.

2. **Irrigation source/coverage and soil moisture**
   - Exact source: not identified in-repo; candidates include CGWB/IWMI groundwater levels, state irrigation department irrigated-area series.
   - Dependency requirement: TBD at sourcing; not assessed; no install planned.
   - What it addresses: the five weakest rainfed crops (387 failures, 28.2% of all).

3. **Crop calendar / sowing-harvest windows per district**
   - Exact source: ICAR / Directorate of Economics & Statistics crop calendars.
   - Dependency requirement: none expected (tabular CSV/PDF extract).
   - What it enables: seasonal rather than calendar-year rainfall sums aligned to growing windows.

4. **Field- or block-level yield observations**
   - Exact source: state agriculture department / district statistical handbooks; no public machine-readable source identified.
   - Dependency requirement: N/A — institutional data sharing, not software.
   - What it addresses: the dispersion itself — Phase 12's ceiling argument. This is the largest cluster (upper bound +4.45 pp) but needs institutional access, not a download.

### 3.4 Single most valuable next action

**Collect district-resolution observed rainfall for 2000–2017 (minimum 2016–2017) and replace the `Year.clip(upper=2015)` forward-fill with real observations — before any further model work.**

Why first:
- It is the only demonstrated data defect in the pipeline (10.04% of rows carry 2015 rainfall for later years).
- It targets the three worst years (669 rows / 301 failures = 22.0% of all failures).
- It needs no new dependency and no code change beyond the join.
- The only already-available alternative (ERA5) was measured to **hurt** in Phase 9.

Quantified upper bound: **+2.16 pp** if the shock-year subgroup reached the overall rate (upper limit, not a prediction).

Strategic second: field-/block-level yields address the largest cluster (upper bound +4.45 pp) but require institutional data sharing, not a download.

No downloads and no installs were performed in this phase.

---

## Constraints honored

- No packages installed or upgraded.
- Production model not overwritten (`models/yield_prediction/randomforest_model.pkl` untouched; sha256 verified unchanged before and after this phase).
- Production code untouched.
- Phase 12 results not modified (sha256 identical before and after: `4264c85dcfe96660d38f73291e03068c793f4d130a9ab50bfabc4fe29416102a`).
- No new model experiments: only the F3 baseline determinism reruns; no candidates, no tuning, no accuracy claims.
- No data downloaded.

---

## Deliverables

- `experiments/phase13/phase13_reproducible_baseline.py` — the reproducible baseline script (read-only F3 rerun under the pinned stack).
- `experiments/phase13/results/phase13_results.json` — environment, reproducibility comparison, production-vs-F3 discrepancies, and the data-improvement analysis with quantified upper bounds.
- `experiments/phase13/PHASE13_REPORT.md` — this concise report.

---

## Final answers

1. **How much model training and improvement have we actually completed?**  
   We completed a real, measured improvement on seed viability (90.48% → 92.86% on a fixed 42-row holdout, meta_model_improvement) and strong crop-classification results on specific held-out splits (e.g., 0.993 macro-F1 on the joint-accuracy 22-crop test). For yield, the strongest verified results are the F3 baseline (68.20% holdout / 69.54% OOF within ±25%, R² 0.9589 / 0.9475) on the improved-dataset track and ~0.9088 R² on the served artifact's own test split in total tonnes. The served production yield model is a different artifact from the F3 evaluated in Phases 9–12.

2. **Which client-reported percentages are verified, unverified, or incomparable?**  
   Verified on our own pipeline/experiment (not necessarily the client's): seed viability 90.48% → 92.86%; F3 yield baseline 68.20% / 69.54%; crop 0.993 macro-F1 on the joint-accuracy split.  
   Unverified (no matching measurement in this repo): RF 92%, XGBoost 94%, SVM 89%, hybrid meta 96%, ~92/91/90/91% classification, yield MSE 0.05 / RMSE 0.22 / R² 0.95.  
   Incomparable (different task/target/split/unit): client yield R² 0.95 vs our served-artifact R² 0.9088 on total tonnes vs our F3 holdout R² 0.9589 on t/ha; client flat-accuracy percentages vs our ±25% tolerance; client crop 92% vs our 87.7% / 99.3% on different crop sets.

3. **What is our strongest reproducible result for each distinct model task?**  
   - Seed viability: 92.86% accuracy (39/42) on the meta_model_improvement 42-row holdout.  
   - Crop classification: 0.993 macro-F1 / 0.993 recall on the joint-accuracy 22-crop held-out test.  
   - Yield: 68.20% within ±25% on the F3 1088-row frozen holdout (R² 0.9589); or ~0.9088 R² on the served artifact's own 1162-row test split in total tonnes. These are different targets/splits and must not be mixed.

4. **Is the production hybrid Meta Model's claimed 96% accuracy reproducible?**  
   No. The production `models/meta_model.pkl` is a 6-feature, max-depth-3, 100-tree RandomForestClassifier with binary synthetic/rule-generated labels, served from a 6-scalar vector built at request time in `app.py`. It has no independent real-world outcome to validate against in this repository, and it does not match the stacking model produced by `train_final_meta_and_compare.py`. There is no measured 96% on any held-out real outcome for the production artifact in this repo. If the client's 96% came from a different dataset, a different meta definition, training accuracy, or a synthetic-label evaluation, it is not transferable to this production artifact as-is.

5. **What is the single highest-priority next action?**  
   Resolve the meta model before any further accuracy claims: define what "96%" was supposed to measure (dataset, outcome, split, metric), and either collect real labelled outcomes or document `prob_success` explicitly as a heuristic and align it with that definition. For yield, the single highest-value data action is to collect district-resolution observed rainfall for 2000–2017 (minimum 2016–2017) and replace the `Year.clip(upper=2015)` forward-fill, which is the only demonstrated pipeline data defect and targets the three worst years (upper bound +2.16 pp, upper limit not prediction). No downloads or installs were done in this phase; the rainfall source and its Kaggle-mirror provenance are reported above for the user to authorize before any download.
