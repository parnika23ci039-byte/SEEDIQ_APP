# Phase 12 — Senior Audit, Error Decomposition, and One Justified Improvement

**Date:** 2026-10-11
**Baseline:** F3 (0.8·HistGBR(base) + 0.2·HistGBR(base+subdivision rainfall), per crop; Chickpea RF specialist)
**Objective:** improve F3's 69.54% grouped-OOF / 68.20% frozen-holdout within-±25% result.
**Outcome:** **RETAIN F3.** The single pre-registered intervention improved the primary metric by only **+0.27 pp** (3/5 folds) and worsened ±10% and MAE — below the pre-stated acceptance gate. The audit also found a **reproducibility defect**: F3's published baseline is stack-dependent (sklearn 1.9.1 vs the production-pinned 1.6.1), which is larger than the effect of the tested intervention.

---

## 1. Audit — every claim verified with code and data

| Check | Evidence | Verdict |
|---|---|---|
| **Training target vs served target** | F3 trains on `yield_per_hectare` (t/ha). Production `LogPerHaRegressor` fits `log(Yield_Tonnes/Area_Hectares)` and returns total tonnes; `POST /api/yield-prediction` reports `units="tonnes per hectare"` and `total_tonnes = per_ha × area`, explicitly labelled an extrapolation. Relative error is area-invariant, so the ±25% metric is comparable. | **Aligned** (no unit mismatch) |
| **Real ICRISAT vs synthetic** | All 5,585 rows of `data/enriched_yield_karnataka.csv` match `SeedIQ/data/yield_icrisat_karnataka.csv` exactly (area and production identical on every row; 5,585/5,585 source rows present). 19 districts, 22 crops, 2000–2017. Synthetic rows: **0**. | **Separated** |
| **`yield_per_hectare` = production / area** | max abs deviation from `Yield_Tonnes/Area_Hectares` = 1.8e-15. Yield range 0.018–14.23 t/ha, median 0.74. No zero or negative yields; min area 10 ha (no division by zero). | **Consistent** |
| **Prediction-time features** | F3's 56/63 features are: area, log-area, year offset, per-district soil and monthly/quarterly/annual rainfall normals, 7 dynamic subdivision-rainfall features, 22 crop dummies — all district-year quantities known when predicting a district-year row. One documented limitation: IMD rainfall ends 2015, so 2016–17 rows (10.0%) reuse 2015 values. | **Verified** (with stated limitation) |
| **Leakage** | 0 exact duplicates; 0 duplicate (District, Year, Crop); 0 missing values; target and its logs excluded from the feature list; district statics are constant within district (max distinct values per district = 1) so they carry no year-specific target information. | **None found** |
| **Folds** | `GroupKFold(5)` on `District|Year`; frozen holdout `GroupShuffleSplit(0.2, rs=42)` on the same groups. Recomputing F3 reproduces the stored Phase 10 OOF to 1.8e-15 and the 742/1088 holdout exactly. | **Reproducible** (see §4 for the stack caveat) |
| **±25% metric at zero/near-zero** | `|pred−true| / max(|true|, 1e-12)`; no zero actuals exist; 10 rows < 0.05 t/ha (0.22%) cannot pass by construction and are counted as failures, identically in phases 10, 11, 12. | **Consistent** |

**No defect was found in the target definition, units, provenance, duplicates, leakage or fold construction.**

---

## 2. Error decomposition (grouped OOF, n = 4,497, baseline 69.54%)

| Actual band (t/ha) | n | pass ±25% | failures | overpredicted | bias |
|---|---:|---:|---:|---:|---:|
| **0–0.5** | **1,315** | **54.30%** | **601** | **70.0%** | **+0.087** |
| 0.5–1.0 | 1,635 | 73.39% | 435 | 46.0% | +0.004 |
| 1.0–2.0 | 793 | 72.64% | 217 | 35.6% | −0.064 |
| 2.0–3.0 | 311 | 82.96% | 53 | 47.9% | −0.022 |
| 3.0–5.0 | 211 | 81.52% | 39 | 30.8% | −0.130 |
| 5.0+ | 232 | 89.22% | 25 | 41.4% | −0.286 |

**Largest avoidable failure subgroup: the 0–0.5 t/ha band — 29% of rows but 601/1,370 = 43.9% of all failures, 54.3% within ±25%, 70% overpredicted (bias +0.087 t/ha).**

- Weakest crops: Sesamum 58.6% (n=227), Pigeonpea 59.3%, Minor Pulses 59.9%, Safflower 61.5%, Linseed 64.3%. Strongest: Sugarcane 85.3%, Rice 85.0%. Together the five weakest crops hold 28% of all failures.
- Weakest years: 2016 (49.8%), 2003 (51.9%), 2017 (62.1%) — drought/shock years, where the model cannot see the shock (subdivision-level annual rainfall only, and 2016–17 are stale).
- Weakest districts: Dharwad 61.1%, Hassan 62.0% — no single district is a data anomaly.

**Model error vs missing information.** The year-to-year relative spread of low-yield district-crop series (median CV 0.34) is *wider than the ±25% tolerance band*, and a constant district-crop median misses 49.6% of low-band rows; 516 of 1,370 failures are within 10 pp of the boundary (297 within 5 pp). The failure structure is therefore dispersion-dominated, not a systematic placement defect — quantified in §3.

---

## 3. The one experiment — metric-aligned log-space centering

**Hypothesis (single, pre-registered).** ±25% is multiplicative, so the pass set is `pred ∈ [0.75·y, 1.25·y]`, i.e. a log-error interval `[ln 0.75, ln 1.25] = [−0.2877, +0.2231]` that is **asymmetric**. For a symmetric-in-log error distribution the hit rate is maximized by centering log-predictions at the interval midpoint:

```
K = exp((ln 0.75 + ln 1.25)/2) = sqrt(0.9375) = 0.9682458…
```

`K` comes from the metric definition alone — **nothing is fitted on data** (no leakage), and the candidate is `pred_candidate = K · pred_F3` on identical rows and identical folds.

| Metric (grouped OOF) | F3 baseline | Candidate | Δ |
|---|---:|---:|---:|
| **Within ±25%** | **69.5352%** | **69.8021%** | **+0.2669 pp** |
| Within ±10% | 36.0463% | 34.0672% | −1.9791 pp |
| MAE (t/ha) | 0.237308 | 0.240809 | +0.003501 |
| RMSE (t/ha) | 0.445019 | 0.453248 | +0.008229 |
| R² | 0.947486 | 0.945526 | −0.001960 |
| Bias (t/ha) | −0.006869 | −0.050953 | −0.044084 |
| Frozen holdout ±25% (reference) | 68.1985% (742/1088) | 68.3824% (744/1088) | +0.1839 pp |

Fold-by-fold (within ±25%): base `[66.59, 68.04, 69.44, 74.39, 69.22]`, candidate `[68.15, 67.04, 70.78, 73.27, 69.78]` — **3 of 5 folds improved**. 112 rows entered the band, 100 left.

Subgroups: the intended target moved — `yield<0.5` **+2.01 pp** (54.68 → 56.69), Rice +0.73, 2003 +0.53 — but the gain is offset elsewhere: Pigeonpea −2.85, Sesamum −0.88, 2016 −0.88, yield≥5 −0.86, Sugarcane −0.80.

**Acceptance gate (stated before running):** meaningful Δ ≥ 1.0 pp ✗ (achieved +0.27), improvement in ≥ 4/5 folds ✗ (3/5), no unacceptable regression ✓. **→ RETAIN F3.**

**Placement ceilings (diagnostics, OOF only — not used for selection).**
- Empirical optimal *global* factor on the same OOF: `k = 0.966` → 70.0022% (**+0.467 pp**) — i.e. the whole global-recentering family tops out below the gate.
- In-sample oracle ceiling for *any* per-crop multiplicative correction: 71.2253% (**+1.690 pp**).
- Honest cross-fitted per-crop correction: 68.8014% (**−0.734 pp**) — per-crop factors do not transfer.
- Phase 10/11 already measured the remaining placement family: isotonic −2.16, linear −1.27, variance stretch −4.58, log target −0.67, squared-error loss −0.58 pp.

**Conclusion:** placement for this metric is exhausted; the residual is conditional dispersion (information), not calibration error.

---

## 4. Cross-environment reproducibility finding (audit)

The published F3 baseline is reproducible **only on one local stack**. The same script, same data, same folds:

| Stack | Make-up | OOF ±25% | Holdout ±25% | Candidate OOF |
|---|---|---|---|---|
| Homebrew `python3` (experiment track) | py3.14.6, sklearn **1.9.1**, numpy 2.5.3, pandas 3.0.6 | **69.5352%** | 68.1985% (742) | 69.8021% (+0.267 pp) |
| Repo venv (production pin) | py3.9.6, sklearn **1.6.1**, numpy 2.0.2, pandas 2.3.3 | **68.4679%** | 68.0147% (740) | 68.6902% (+0.222 pp) |

- Library version alone moves the F3 baseline by **−1.07 pp OOF** (−0.18 pp holdout). Phases 9–11 were run on the Homebrew stack; production pins scikit-learn 1.6.1 (the version its pickles were serialised with).
- The tested candidate's ±25% gain is similar in both stacks (+0.27 / +0.22 pp) — but **the candidate remains below the gate in both**, so the decision is stack-robust.
- Implication: any Phase 9–11 candidate delta smaller than ~1 pp is not trustworthy until re-measured under a single pinned stack; the experiment track should pin the same stack as serving (or explicitly record it).

---

## 5. Root cause (verified) and why the accepted answer is “retain”

1. **No pipeline defect was found** — target, units, provenance, features, leakage and folds all check out; the published baseline reproduces exactly on the stack that produced it.
2. **The residual error is dispersion/information-limited.** 44% of failures sit in the <0.5 t/ha band, whose year-to-year relative spread (~34%) exceeds the ±25% tolerance band; the available district-year features cannot resolve it, and every placement correction is already exhausted (global optimal +0.47 pp; per-crop oracle ceiling +1.69 pp; honest per-crop fitting loses).
3. **The largest measured effect in this phase is not a modelling gain but an environment mismatch** (1.07 pp between experiment and serving stacks) — larger than any candidate tested in phases 9–11.

---

## 6. Next concrete data requirement

1. **Field-/block-level yield observations** — the target is a district aggregate whose year-to-year dispersion exceeds the tolerance band; no feature engineering recovers sub-aggregate variation.
2. **District-resolution *observed* rainfall for the target year** (including 2016–17, currently stale 2015 values) plus crop calendars to align weather with growing windows — this is the only route into the 2003/2016/2017 failures.
3. **Irrigation / soil-moisture covariates** for the five weakest rainfed crops (Sesamum, Pigeonpea, Minor Pulses, Safflower, Linseed), which hold 28% of all failures.
4. **Protocol fix (non-data):** pin one library stack for experiments and serving; re-baseline phases 9–11 deltas under it.

---

## 7. Reproduction

```bash
cd /Users/apple/SeedIQ/experiments/improved_dataset/phase12
/usr/local/bin/python3 phase12_audit_and_metric_aligned_centering.py
```

The script re-runs the audit, the error decomposition, the single experiment and the cross-environment probe. Outputs `results/phase12_results.json`. The production-stack cross-check runs automatically via the venv interpreter.

## 8. Files created (nothing existing was modified)

| File | Description |
|---|---|
| `phase12/phase12_audit_and_metric_aligned_centering.py` | Audit + error analysis + the one experiment + environment probe |
| `phase12/results/phase12_results.json` | All audit checks, error cuts, metrics, diagnostics, decision |
| `phase12/PHASE12_REPORT.md` | This report |

**Exploratory screening disclosure (transparency, not part of the pre-registered experiment).** Two alternative candidates were screened on the grouped-OOF selection metric during the audit — the frozen holdout was never used for selection: (a) causal persistence features (lag-1/lag-2 district-crop yield): **66.40% (−3.14 pp)**; (b) a pooled low-yield specialist over the six weakest crops: **68.53% (−1.00 pp)**. Both were measured worse and were not adopted; the single pre-registered experiment above is the metric-aligned centering. Prior phase families (weather, calibration, log target, squared loss, per-crop model selection) had already been measured worse in phases 9–11.
