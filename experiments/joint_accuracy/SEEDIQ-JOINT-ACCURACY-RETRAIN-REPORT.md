# SeedIQ — Existing-Data Joint-Accuracy Retraining Report

Generated 2026-10-09 19:36:45 by `run_experiment.py` (stages: baseline → candidates → final).

**Status: 90% NOT ACHIEVED on existing data — and the joint rate itself is NOT EVALUABLE on these separate test sets.**

## 1. Headline: baseline vs retrained (untouched test split)

| Metric | Baseline (deployed artifacts) | Retrained candidate | Delta |
|---|---|---|---|
| Crop accuracy | 99.32% | 99.32% | -0.00 pp |
| Yield within ±25% | 49.74% | 51.46% | +1.72 pp |
| Yield R² (district totals) | 0.9088 | 0.8934 | -0.0154 |
| Seed accuracy | 90.00% | 90.00% | +0.00 pp |
| Meta-classifier accuracy | NOT EVALUABLE | NOT EVALUABLE | n/a |
| **Joint success** | **NOT EVALUABLE** | **NOT EVALUABLE** | n/a |

**Joint success is NOT EVALUABLE.** The crop, yield and seed test sets share no sample identifier (no common key column). No row of one set is the same sample as a row of another, so a joint-success rate cannot be computed from these separate test sets. Reporting a paired/round-robin figure would fabricate rows that exist nowhere in the data.

Per-source TEST rows: {'crop': 440, 'yield': 1162, 'seed': 20}. Each figure below is measured on its own model's test split and is valid only as a marginal rate:

- Crop accuracy: 99.32% → 99.32%
- Yield within ±25%: 49.74% → 51.46%
- Seed accuracy: 90.00% → 90.00%
- Independence product of the candidate marginals: 46.00% — an ASSUMPTION, not a measurement, since it multiplies rates from different splits.

### What was removed and why

The previous version of this experiment reported a joint-success figure on 440 rows built by cycling the 20 seed test rows across the 440 crop rows (`seed row i mod 20`) and pairing them with yield row `i`. Those rows exist nowhere in the data: each 'joint row' combined three unrelated samples, the seed pass/fail pattern repeated about 22 times (effective n = 20), and yield rows 440-1161 never entered the figure. The same round-robin triples were also used to train and score the meta-classifier, so its accuracy measured the fabricated pairing rather than the models.

Both are now hard-failed in code: `joint_metrics.joint_success_report` counts only rows genuinely joined on a shared sample key and returns NOT EVALUABLE otherwise, `run_experiment.build_aligned_joint` feeds it the real test splits, and no meta model is fitted. `experiments/joint_accuracy/artifacts/meta_candidate.pkl` (trained on those triples) is deleted.

### Per-class detail, untouched test split

Crop — 22 classes, 440 rows (macro precision 99.35%, macro recall 99.32%, macro F1 99.32%):

| class | support | precision | recall | F1 |
|---|---|---|---|---|
| apple | 20 | 1.0000 | 1.0000 | 1.0000 |
| banana | 20 | 1.0000 | 1.0000 | 1.0000 |
| blackgram | 20 | 1.0000 | 0.9500 | 0.9744 |
| chickpea | 20 | 1.0000 | 1.0000 | 1.0000 |
| coconut | 20 | 1.0000 | 1.0000 | 1.0000 |
| coffee | 20 | 1.0000 | 1.0000 | 1.0000 |
| cotton | 20 | 1.0000 | 1.0000 | 1.0000 |
| grapes | 20 | 1.0000 | 1.0000 | 1.0000 |
| jute | 20 | 0.9524 | 1.0000 | 0.9756 |
| kidneybeans | 20 | 1.0000 | 1.0000 | 1.0000 |
| lentil | 20 | 1.0000 | 0.9500 | 0.9744 |
| maize | 20 | 0.9524 | 1.0000 | 0.9756 |
| mango | 20 | 1.0000 | 1.0000 | 1.0000 |
| mothbeans | 20 | 0.9524 | 1.0000 | 0.9756 |
| mungbean | 20 | 1.0000 | 1.0000 | 1.0000 |
| muskmelon | 20 | 1.0000 | 1.0000 | 1.0000 |
| orange | 20 | 1.0000 | 1.0000 | 1.0000 |
| papaya | 20 | 1.0000 | 1.0000 | 1.0000 |
| pigeonpeas | 20 | 1.0000 | 1.0000 | 1.0000 |
| pomegranate | 20 | 1.0000 | 1.0000 | 1.0000 |
| rice | 20 | 1.0000 | 0.9500 | 0.9744 |
| watermelon | 20 | 1.0000 | 1.0000 | 1.0000 |

Crop confusion matrix (22x22, rows = actual, columns = predicted, in the class order of the table above) is stored as `crop_test_confusion_matrix` in `results/final.json`.

Seed viability (synthetic labels), 20 rows:

| class | support | precision | recall | F1 |
|---|---|---|---|---|
| Non-Viable | 13 | 0.9231 | 0.9231 | 0.9231 |
| Viable | 7 | 0.8571 | 0.8571 | 0.8571 |

No meta-classifier confusion matrix exists: with no aligned joint rows there are no joint labels to predict.

## 2. Which component limits joint success

The numbers in this section are INDEPENDENCE BOUNDS computed from the marginal component rates of section 1, not a measured joint rate (which is not evaluable here).

- To reach 90% with the other two components unchanged, the required single-component pass rates would be: crop 1.94, yield 1.01, seed 1.76 (values > 1 are impossible).
- Joint if yield never failed: 89.39%; if seed never failed: 51.11%; if crop never failed: 46.32%.
- Yield is the binding constraint: even a perfect seed model leaves joint at 51.11% because the ±25% yield condition alone caps it.

### Where the ±25% yield condition fails (candidate)

| Actual per-ha band (t/ha) | rows | within ±25% |
|---|---|---|
| [0.0, 0.5) | 358 | 27.93% |
| [0.5, 1.0) | 401 | 63.34% |
| [1.0, 2.0) | 212 | 53.77% |
| [2.0, 5.0) | 136 | 63.97% |
| [5.0, inf) | 55 | 78.18% |

Area-free reference (per-crop train-derived constant): 46.47% on the yield test split.

### Why the ±25% condition saturates (measured, not assumed)

- 1056 yield rows in 388 groups share an identical (Crop, Area_Hectares) input with at least one other row while carrying different district-year yields. 185 test rows sit in such groups and 161 test rows have their exact input vector present in TRAIN.
- Identical inputs must receive an identical prediction, so an oracle per-(Crop, Area) constant is bounded by 99.05% (1151/1162) — but that counts the single-row groups as free passes, so only 11 test rows are provably impossible. Input collisions are NOT the binding constraint.
- The binding evidence is the in-sample fit: the selected yield model reaches 62.47% ±25% on the rows it was TRAINED on (R² 0.9542) versus 51.46% in test. A model that cannot exceed ~62% on its own training rows is limited by the spread of the label at fixed inputs, not by overfitting or insufficient tuning.
- The same conclusion from per-crop spread: the TRAIN p75/p25 per-hectare ratio runs 1.43–1.89 across crops, i.e. the middle half of district-year yields already spans far more than the ±25% tolerance at fixed crop and area.
- Reaching 90% joint success therefore requires new INPUTS (district, season, weather, soil) or real field-level yield data — not a better model on the existing table. And even a perfect yield model would leave joint at 89.39% while crop and seed stay where they are.

## 3. Candidate selection (all on TRAIN only)

**Crop** — selected `RandomForest(600, depth=None, leaf=1, max_features=0.5, balanced)`
 (mean StratifiedKFold(5) accuracy on TRAIN).
**Yield** — selected `quantile tau=0.5634 on log-per-ha, +per-crop area rank feature shrunk toward the crop train geomean (w=0.85)`
 (OOF +/-25% hit rate (GroupKFold(5) by district-year on TRAIN)).
**Seed** — selected `RandomForest(300, depth=None, balanced)`
 (mean StratifiedKFold(5) accuracy on TRAIN).
**Meta** — NOT EVALUABLE. The meta-classifier's target IS the three-condition joint label, so scoring it requires the same genuinely aligned rows the joint metric requires. None exist in these separate test sets.

Yield candidates, ranked by OOF ±25% (train GroupKFold):

| Candidate | OOF ±25% | OOF R² |
|---|---|---|
| quantile tau=0.5634 on log-per-ha, +per-crop area rank feature | 54.58% | 0.9367 |
| absolute_error (median) on log-per-ha, base contract features | 54.28% | 0.9307 |
| quantile tau=0.5000 on log-per-ha, base contract features | 54.28% | 0.9307 |
| quantile tau=0.6000 on log-per-ha, base contract features | 54.15% | 0.9305 |
| quantile tau=0.5634 (+/-25% optimal) on log-per-ha, base contract features | 53.95% | 0.9330 |
| quantile tau=0.5634 on log-per-ha, +log(area) feature | 53.95% | 0.9330 |
| squared_error on log-per-ha, base contract features | 51.98% | 0.9232 |
| squared_error on log-per-ha, +log(area) feature | 51.98% | 0.9232 |
| crop-constant train log-geomean (reference, no area response) | 50.73% | 0.9313 |

Shrinkage of the best base candidate toward the crop train geomean (OOF, train GroupKFold) — w=1.0 is the unshrunk base model:

| weight on base | OOF ±25% | OOF R² |
|---|---|---|
| 0.85 | 54.80% | 0.9391 |
| 1.00 | 54.58% | 0.9367 |
| 0.70 | 54.37% | 0.9403 |
| 0.50 | 53.83% | 0.9399 |
| 0.30 | 52.93% | 0.9377 |
| 0.00 | 50.73% | 0.9313 |

Area-free reference (`crop-constant train log-geomean (reference, no area response)`): train in-sample ±25% 50.73% — i.e. a model that ignores area already reaches roughly half coverage, so most of the coverage gap is the irreducible district-to-district spread at fixed crop and area.

The selected yield model is the shrunken variant; its reported test numbers in section 1 come from that exact fitted object, not from the unshrunk base candidate.

## 4. Leakage controls

- Crop retrained on shuffled train labels → test accuracy 3.64% (chance 4.55%).
- Yield retrained on shuffled train targets → test ±25% 7.49%.
- Seed retrained on shuffled train labels → test accuracy 50.00%.
- Splits: crop/seed train∩test = ∅, yield district-years disjoint — {'crop_train_test_disjoint': True, 'seed_train_test_disjoint': True, 'yield_district_years_disjoint': True, 'meta_feature_count': 6, 'meta_features_are_model_outputs_only': True}.
- The 6 meta features are base-model outputs only; no ground truth, actual yield, district or year enters them.

## 5. Limitations

- **Seed is synthetic.** The 100-row table has generated labels (logistic draw around a 12% moisture optimum). Any seed score measures generator approximation, not real viability; the 20-row test split also has ~±10 pp sampling noise.
- **Yield is district-year statistics, not field trials.** The served contract is Crop + Area only; district/season effects are irreducible with these inputs, which is why ±25% coverage saturates near half.
- **Joint success is NOT EVALUABLE from these three test sets.** They share no sample identifier, so no row carries crop, yield and seed ground truth for the same sample. Any joint number would have to be manufactured; none is reported here. A real joint rate needs a dataset in which all three quantities are measured on the same plot, or an explicit join key.
- **A perfect yield model would not reach 90%, even by the independence bound.** With crop at 99.32% and seed at 90.00%, driving yield within ±25% to 100% leaves the product at 89.39% — below 0.90. Reaching the target needs new INPUTS (district, season, weather, soil) or field-level measurements, not a better model on this table.
- The ±25% hit rate and R² are in tension: the τ=0.5634 quantile choice maximises coverage and may trade a little R² on district totals.

## 6. Reproduce

```bash
cd ~/SeedIQ
.freebuff/venv/bin/python experiments/joint_accuracy/run_experiment.py --stage all
```
Artifacts: candidate models in `experiments/joint_accuracy/artifacts/`, machine-readable results in `results/` (`data_audit.json`, `baseline.json`, `baseline_snapshot.json`, `candidates.json`, `final.json`, `experiment_log.txt`), preserved production copies in `baseline_artifacts/`. Production artifacts under `SeedIQ/models/` are untouched.

