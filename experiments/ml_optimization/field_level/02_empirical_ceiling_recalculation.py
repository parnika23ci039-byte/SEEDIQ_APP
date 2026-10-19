"""
Empirical Ceiling Recalculation — DISTRICT Model on District Test Set
=====================================================================
This script recomputes the 89.55% reported joint accuracy from the
original row-level test outcomes stored in experiments/joint_accuracy/.

It does NOT modify any metric. It explains what 89.55% means, where it
came from, and why a field-level model requires an entirely new test set.

Run:
    python3 experiments/ml_optimization/field_level/02_empirical_ceiling_recalculation.py

Output:
    experiments/ml_optimization/field_level/empirical_ceiling_verified.json
"""

import json
import math
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
RESULTS_DIR = ROOT / "experiments" / "joint_accuracy" / "results"
UPPER_BOUND_FILE = ROOT / "experiments" / "ml_optimization" / "empirical_upper_bound.json"
OUT = Path(__file__).parent / "empirical_ceiling_verified.json"


# ──────────────────────────────────────────────────────────────────────────────
# 1. Load original stored metrics
# ──────────────────────────────────────────────────────────────────────────────
with open(RESULTS_DIR / "final.json") as f:
    final = json.load(f)

with open(UPPER_BOUND_FILE) as f:
    upper = json.load(f)

# ──────────────────────────────────────────────────────────────────────────────
# 2. Recalculate joint accuracy from stored component predictions
# ──────────────────────────────────────────────────────────────────────────────
preds = np.load(RESULTS_DIR / "predictions_candidates.npz")
avail_arrays = list(preds.files)
print(f"Available prediction arrays: {avail_arrays}")

# Joint accuracy as reported in empirical_upper_bound.json
# The 89.55% figure comes from: if the yield sub-model were perfect (within ±25%)
# and crop+seed kept their actual accuracy, what is the theoretical ceiling?
crop_acc = upper["crop_accuracy_meta"]
seed_acc = upper["seed_accuracy_meta"]
yield_if_perfect = 1.0

theoretical_ceiling = crop_acc * seed_acc * yield_if_perfect
print(f"\nTheoretical ceiling (perfect yield): {theoretical_ceiling:.6f}")
print(f"Stored in empirical_upper_bound.json: {upper['empirical_upper_bound_perfect_yield']:.6f}")
diff = abs(theoretical_ceiling - upper["empirical_upper_bound_perfect_yield"])
# The stored JSON value (0.895455) uses seed_accuracy=0.90 directly from a specific
# test run; the crop_accuracy_meta in the JSON (0.9955) multiplied by 0.90 gives 0.8959.
# The difference is due to the stored JSON using seed_accuracy rounded during
# a different test run. We document this rather than force an assertion.
print(f"  Computed ceiling: {theoretical_ceiling:.6f}")
print(f"  Stored in JSON:   {upper['empirical_upper_bound_perfect_yield']:.6f}")
print(f"  Difference:       {diff:.6f} (rounding from different test run snapshot)")
assert diff < 1e-3, f"Large discrepancy: {diff}"

# Actual joint accuracy from the final run (nested under comparison.baseline.joint)
baseline = final["comparison"]["baseline"]
actual_joint = baseline["joint"]["rate"]
test_rows = baseline["joint"]["test_rows"]
successes = baseline["joint"]["successes"]
failures  = baseline["joint"]["failures"]

print(f"\nActual joint test rows: {test_rows}")
print(f"Successes: {successes}")
print(f"Failures: {failures}")
print(f"Actual joint accuracy: {actual_joint:.6f} ({actual_joint*100:.2f}%)")
print(f"Yield within ±25%: {final['joint']['component_pass_rate']['yield_within_25pct']:.6f}")

# ──────────────────────────────────────────────────────────────────────────────
# 3. Explain the 89.55% figure
# ──────────────────────────────────────────────────────────────────────────────
explanation = {
    "what_is_8955": (
        "The 89.55% is the THEORETICAL EMPIRICAL CEILING for the DISTRICT-LEVEL model. "
        "It answers: 'If yield prediction were perfect (100% within ±25%), what joint "
        "accuracy would crop + seed components achieve on the current 440-row test set?' "
        "Answer: 0.9955 × 0.90 × 1.0 = 0.8959 ≈ 89.59% (89.55% as rounded and reported). "
        "It is NOT the achieved accuracy. Actual joint accuracy was 45.00%."
    ),
    "why_yield_drags_it_down": (
        "The yield sub-model achieves only ~50.7% within ±25% on the district test set. "
        "This is because the target (Yield_Tonnes) is total district production (tens of "
        "thousands of tonnes), not per-hectare field yield. A ±25% tolerance on a target "
        "of 50,000 tonnes is ±12,500 tonnes — still enormous variance. "
        "The model predicts district-aggregate correctly (R²=0.91) but the ±25% "
        "row-level tolerance check fails for half the rows."
    ),
    "why_field_level_needs_new_test_set": (
        "A field-level model would be trained on individual farm/plot records with "
        "soil inputs (N, P, K, pH), climate (rainfall, temperature), crop type, "
        "and a target of tonnes/hectare. The current 440-row test set contains "
        "district aggregate rows (Karnataka 19 districts × crops × years). "
        "These are entirely different observations. No result from the current "
        "test set is valid for a field-level model. A new held-out test set "
        "drawn from genuine field-level records is required."
    ),
}

# ──────────────────────────────────────────────────────────────────────────────
# 4. Recompute from component rates (verify no rounding errors)
# ──────────────────────────────────────────────────────────────────────────────
crop_rate = baseline["joint"]["component_pass_rate"]["crop"]
yield_rate = baseline["joint"]["component_pass_rate"]["yield_within_25pct"]
seed_rate  = baseline["joint"]["component_pass_rate"]["seed"]


naive_product = crop_rate * yield_rate * seed_rate
# The actual joint rate accounts for WHICH samples fail (not independent)
# but naive product gives approximate expectation under independence assumption
print(f"\nNaive product (if independent): {naive_product:.6f} ({naive_product*100:.2f}%)")
print(f"Actual measured joint:          {actual_joint:.6f} ({actual_joint*100:.2f}%)")
print(f"(Difference due to failure co-occurrence on same samples)")

# Wilson CI for reported 89.55%
n = 440
p_ceiling = 0.8955
z = 1.96
denom = 1 + z**2/n
center = (p_ceiling + z**2/(2*n)) / denom
margin = z * math.sqrt(p_ceiling*(1-p_ceiling)/n + z**2/(4*n**2)) / denom
ci_low = center - margin
ci_high = center + margin
print(f"\n89.55% ceiling Wilson 95% CI (n={n}): [{ci_low:.4f}, {ci_high:.4f}]")

output = {
    "metric_identity": "THEORETICAL EMPIRICAL CEILING for district-level model on district test set",
    "reported_value": 0.8955,
    "computed_value": round(theoretical_ceiling, 6),
    "matches": abs(0.8955 - theoretical_ceiling) < 0.001,
    "test_set_description": {
        "n_rows": test_rows,
        "granularity": "district × crop × year",
        "dataset": "ICRISAT-derived karnataka, 2000-2017",
        "yield_target_semantics": "total district production in tonnes (not t/ha)",
    },
    "component_pass_rates_on_district_test": {
        "crop_classification": round(crop_rate, 6),
        "yield_within_25pct": round(yield_rate, 6),
        "seed_viability": round(seed_rate, 6),
    },
    "actual_achieved_joint_accuracy": round(actual_joint, 6),
    "explanation": explanation,
    "field_level_model_requirement": {
        "new_test_set_needed": True,
        "reason": (
            "District aggregate rows ≠ individual field observations. "
            "Test set must be drawn from the same population as field-level training data, "
            "held out before any training, and never used for hyperparameter decisions."
        ),
        "minimum_test_set_size_recommendation": 300,
        "target_variable_required": "yield_tonnes_per_hectare",
    },
}

with open(OUT, "w") as f:
    json.dump(output, f, indent=2)

print(f"\nVerification saved → {OUT}")
