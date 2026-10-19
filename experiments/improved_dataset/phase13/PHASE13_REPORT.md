# Phase 13 — Reproducibility and Data-Driven Improvement

**Date:** 2026-10-11
**Objective:** establish a reproducible production baseline before any further model improvement.
**Outcome:** one supported environment chosen and verified; F3 runs **identical twice** on the pinned stack; three production-versus-evaluation discrepancies documented; single most valuable next data action named. **No accuracy claims.**

---

## 1. Verified environment (Task 1)

### The three stacks actually in play

| Role | Interpreter | scikit-learn | numpy / pandas / scipy | Evidence |
|---|---|---|---|---|
| **Training (production artifact)** | not recorded by the trainer (provenance gap) | **1.6.1** (embedded `_sklearn_version` inside the pickle) | not recorded | pickle bytes of `models/yield_prediction/randomforest_model.pkl` (sha256 `2ab7377c…`) |
| **Evaluation (phases 6–12)** | Homebrew `python3` — py **3.14.6** | **1.9.1** | 2.5.3 / 3.0.6 / 1.18.1 | Phase 12 reproduced the published constants 69.5352% / 742-1088 **only** on this stack |
| **Serving** | Railway py **3.11.17** (`.python-version`) | **1.6.1** (`SeedIQ/requirements.txt` pin) | 2.0.2 / 2.3.3 / 1.13.1 | requirements pin + its comment; local dev venv runs the same numeric stack on py3.9.6 |

**Chosen supported environment (documented):** `.freebuff/venv` — Python 3.9.6, **scikit-learn 1.6.1**, numpy 2.0.2, pandas 2.3.3, scipy 1.13.1.
Why: it is the pin declared in `SeedIQ/requirements.txt` **and** the only local stack under which the committed production artifact unpickles; it is already installed, so no package was installed, upgraded or downgraded.

Residual risk (recorded, not hidden): `.python-version` pins **3.11.17** for deployment while the local venv is **3.9.6** — the numeric stack matches exactly, the Python minor differs. Unifying that would require installing a new interpreter, which this phase deliberately did not do.

### Artifact compatibility — measured both ways

| Load attempt | Result |
|---|---|
| pinned stack (chosen env) | **loads, zero warnings**, class `yield_model.LogPerHaRegressor` → `HistGradientBoostingRegressor(loss=squared_error, max_iter=400, lr=0.08, rs=42)`, 23 features; smoke predict 1000 ha Rice → **1999.86 t** total |
| evaluation stack (sklearn 1.9.1) | **fails**: `ModuleNotFoundError: No module named '_loss'` (+ `InconsistentVersionWarning: unpickle 1.6.1 with 1.9.1`) |

So evaluation and serving **cannot share an environment today**: the artifact is 1.6.1-only, the experiment track is 1.9.1-only. Unifying requires either re-serializing the artifact under one stack (a deliberate, re-validated change — not done here) or pinning the experiment track to 1.6.1.

### Production model vs the evaluated F3 — NOT the same model

| Aspect | Production (served) | Evaluated F3 | Same? |
|---|---|---|---|
| Training code | `SeedIQ/train_all_models.py::train_yield` → `make_yield_model()` | `experiments/improved_dataset/phase10/phase10_error_analysis.py::f3_oof` | **No** |
| Model / loss | one global HistGBR, `squared_error`, 400 iters, on `log(Yield_Tonnes/Area)` | per-crop HistGBR, `absolute_error`, 200 iters, 0.8·A+0.2·B blend + Chickpea RF | **No** |
| Data file | `SeedIQ/data/yield_icrisat_karnataka.csv` (5,585 rows) | `experiments/.../data/enriched_yield_karnataka.csv` (same 5,585 ICRISAT rows + soil/rain/year columns) | rows yes / file no |
| Feature schema | **23** columns: Area + 22 crop dummies (no District/Year/soil/rain) | **56** base (63 with dynamic rainfall), district-conditioned | **No** |
| Target | `Yield_Tonnes` (district total, log-fitted) | `yield_per_hectare` (raw t/ha) | **No** |
| Holdout rows | 4423/1162, 69 test groups (matches registry) | 4497/1088, 69 test groups | **No — only 10 of 69 test groups overlap** |
| Reported metric | R² 0.9088 on **tonnes** (registry test) | within ±25% on **t/ha** (68.20% eval stack / 68.01% pinned stack) | incomparable |

Two identical splitter calls (`GroupShuffleSplit(0.2, rs=42)` on `District|Year`) select different groups because district **label spellings differ** between the two tables (renamed vs ICRISAT names); `np.unique` sorts by label, so the seeded permutation lands on different district-years. Consequence: **the Phase 9–12 holdout is not the production holdout**, and the served artifact has never been scored with the within-±25% per-hectare protocol.

### Do the Phase 9–11 claims survive one consistent environment?

Scanned all their result JSONs (read-only): **none records an interpreter or library version**. All four share the constants `69.5352%` OOF and `742/1088`, which reproduce **only** on the 1.9.1 stack → phases 9, 10 and 11 all ran on that single stack.

- **Internally valid:** yes — each phase measured candidate vs baseline within one consistent environment, so the *retain-F3* decisions hold as reported.
- **Absolute values:** stack-specific (the pinned stack scores 68.4679% / 740 on identical code).
- **Small deltas:** not certifiable on the serving stack without re-measurement. Phase 12's one cross-stack data point (+0.267 vs +0.222 pp for the same candidate) suggests deltas are stabler than levels, but n=1.
- Per the constraint "no model experiments", this phase did **not** re-run phase 9–11 candidates.

---

## 2. Reproducible baseline (Task 2)

**Protocol:** one supported environment (pinned serving stack), same data
(`enriched_yield_karnataka.csv`), same seed (42), same folds
(`GroupKFold(5)` on `District|Year` for OOF; `GroupShuffleSplit(0.2, rs=42)`
for the holdout), same evaluation code (Phase 10's `f3_oof` / `f3_predict`,
imported read-only) — F3 run **twice** in the same process.

### Grouped OOF (80% training split, n = 4,497) — reported separately

| Metric | Run 1 | Run 2 | Δ |
|---|---:|---:|---:|
| Within ±25% | 3079/4497 = **68.4679%** | 3079/4497 = **68.4679%** | 0 |
| Within ±10% | 35.7127% | 35.7127% | 0 |
| MAE / RMSE / R² | 0.243649 / 0.461738 / 0.943466 | 0.243649 / 0.461738 / 0.943466 | 0 |
| max abs prediction deviation | — | — | **2.22e-16** |

### Frozen holdout (untouched 20%, n = 1,088) — reported separately

| Metric | Run 1 | Run 2 | Δ |
|---|---:|---:|---:|
| Within ±25% | 740/1088 = **68.0147%** | 740/1088 = **68.0147%** | 0 |
| Within ±10% | 36.6728% | 36.6728% | 0 |
| MAE / RMSE / R² | 0.238545 / 0.407671 / 0.958313 | 0.238545 / 0.407671 / 0.958313 | 0 |
| max abs prediction deviation | — | — | **2.22e-16** |

**Reproducibility result: PASS.** Both runs produce identical metric dicts and
predictions within 2.22e-16 (≈ machine epsilon; tolerance 1e-12).

**The reproducible production baseline is 68.4679% grouped OOF /
68.0147% frozen holdout on the pinned stack** — versus the Phase 12 headline
69.5352% / 68.1985% on the evaluation stack. The 1.07 pp OOF gap is purely
the library-stack difference (Phase 12 measured it; this phase re-confirms
both values from a clean double run).

---

## 3. Highest-value next data improvement (Task 3)

Quantified from the Phase 12 subgroup analysis (read-only). Bounds are
**upper limits, not predictions**: rows gained if a subgroup merely reached
the overall 68.47% pass rate. Subgroups overlap — do not sum.

| Missing-variable target (subgroup) | rows | failures (share) | upper-bound gain |
|---|---:|---:|---:|
| **Drought/shock years 2003+2016+2017** (observed rainfall) | 669 | 301 (22.0%) | **+2.16 pp** |
| five weakest rainfed crops (irrigation, soil moisture, sowing windows) | 970 | 387 (28.2%) | +2.02 pp |
| actual yield < 0.5 t/ha (field-level labels) | 1,315 | 601 (43.9%) | +4.45 pp |

Stale-rainfall subset: **2016+2017 = 480 OOF rows, 210 failures**; the Phase 12
audit measured **10.04% of all rows** served 2015 subdivision rainfall for
2016–2017 via `Year.clip(upper=2015)` — the pipeline's only demonstrated data
defect (a silent forward-fill).

### Already on disk (no download needed)
| Dataset | Status |
|---|---|
| `phase9/data/openmeteo_daily_weather_karnataka.csv` (ERA5, 19 districts, 2000–2017) | **measured in Phase 9 — all candidates regressed the holdout (−1.10 to −4.69 pp)**; reanalysis, not observed truth |
| `SeedIQ/data/rainfall in india 1901-2015.csv` (IMD subdivision) | already in F3 branch B; ends 2015 |
| `SeedIQ/data/district wise rainfall normal.csv` (static normals) | already the static `rain_*` features |
| soil + ICRISAT area/production tables | already the label + area feature; same-year other-crop yields are target-derived (unusable pre-harvest); lagged own yields screened in Phase 12 → −3.14 pp |

### Must be collected (source + dependency requirement reported first — nothing downloaded)
1. **District-resolution observed monthly rainfall incl. 2016–2017** — IMD district
data; convenience mirror identified in Phase 11: Kaggle dataset
`dhamur/monthly-district-avg-rainfall-19012017indiacsv` (1901–2017).
**Dependencies: none new** (CSV read via the pinned pandas); prerequisite is
Kaggle API credentials (Phase 11's blocker) or direct IMD download. *Not downloaded.*
2. Irrigation / soil moisture — source candidates CGWB/IWMI/state irrigation
records; dependency TBD at sourcing; no install planned.
3. Crop calendars (ICAR/DES) — tabular, no new dependency expected.
4. Field-/block-level yields — institutional data sharing, not software.

### The single most valuable next action
> **Collect district-resolution *observed* rainfall for 2000–2017 (minimum
> 2016–2017) and replace the `Year.clip(upper=2015)` forward-fill with real
> observations — before any further model work.**

Why first: it is the only demonstrated data defect (10.04% of rows carry
2015 rainfall for later years); it targets the three worst years
(669 rows / 301 failures = 22.0% of all failures, bound +2.16 pp); it needs
no new dependency and no code change beyond the join; and the only
already-available alternative (ERA5) was **measured to hurt** in Phase 9.
Field-level yields carry a larger bound (+4.45 pp) but are the strategic
second step, requiring institutional sharing rather than a download.

---

## 4. Constraints honoured (machine-verified)

| Constraint | Evidence |
|---|---|
| no package install/upgrade/downgrade | none performed; chosen env already installed |
| no production model overwrite | artifact sha256 `2ab7377c…` recorded; not written |
| no production code alteration | only read `app.py` / `train_all_models.py` / `yield_model.py` |
| Phase 12 results not overwritten | sha256 `4264c85dcf…` identical before and after the run |
| no new model experiments | only F3 baseline determinism reruns; no candidates/tuning |
| no data downloads | none; sources and dependency requirements reported above |
| no invented observations / no silent forward-fill | forward-fill surfaced as a defect, not repeated |
| OOF kept separate from holdout | separate JSON sections and separate tables |

## 5. Reproduction

```bash
cd /Users/apple/SeedIQ/experiments/improved_dataset/phase13
/Users/apple/SeedIQ/.freebuff/venv/bin/python phase13_reproducible_baseline.py
```

The script re-runs the inventory, the artifact checks, both F3 runs and the
data-gap quantification and rewrites `results/phase13_results.json`.

## 6. Files created (nothing existing modified)

| File | Description |
|---|---|
| `phase13/phase13_reproducible_baseline.py` | the single script (Tasks 1–3) |
| `phase13/results/phase13_results.json` | all measurements, both runs, constraints |
| `phase13/PHASE13_REPORT.md` | this report |
