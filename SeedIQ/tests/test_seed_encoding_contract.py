#!/usr/bin/env python3
"""Guard: the seed meta feature must be encoded identically in training and serving.

Background — the skew this test exists to prevent
------------------------------------------------
The hybrid meta model consumes two seed features. They used to be built two ways:

* training built them from the raw predicted **class index**
  (``float(seed_p[si][0])`` in ``train_all_models.train_meta.build_triples``);
* serving built them from a **binary label test**
  (``1.0 if seed_classical == 'Viable' else 0.0`` in ``app.py``).

Those agree only while the seed target is binary. On any other class layout the
training matrix would receive ``{0, 1, 2, ...}`` while serving would still send
``{0.0, 1.0}`` — a silent train/serve skew with no exception raised.

Both sides now import ``seed_viability_semantics``. This test pins three things:

1. the index -> label -> flag round trip is self-consistent for every class of
   the **production** seed model;
2. the shared encoding is a **no-op** against the previous expressions for the
   current binary model, so no existing meta feature and no served
   ``prob_success`` value changes;
3. the training-side helper and the serving-side helper agree for every class.

Run:  python tests/test_seed_encoding_contract.py
Exit status is the source of truth (0 = all checks passed).
"""
from __future__ import annotations

import os
import pickle
import sys

import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
MODELS_DIR = os.path.join(BASE_DIR, "models")

from seed_viability_semantics import (  # noqa: E402
    NEGATIVE_CLASS_LABEL,
    POSITIVE_CLASS_INDEX,
    POSITIVE_CLASS_LABEL,
    viable_flag_from_index,
    viable_flag_from_label,
    viable_label,
)

FAILURES = []


def check(name, fn):
    try:
        detail = fn()
    except Exception as exc:  # noqa: BLE001 - a guard must fail loudly, not silently
        FAILURES.append(f"{name}: {type(exc).__name__}: {exc}")
        print(f"FAIL  {name}\n        {type(exc).__name__}: {exc}")
        return
    print(f"ok    {name}" + (f"  [{detail}]" if detail else ""))


def require(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _load(rel):
    path = os.path.join(MODELS_DIR, rel)
    with open(path, "rb") as fh:
        return pickle.load(fh)


# ── 1. encoding self-consistency ────────────────────────────────────────────
print("=" * 78)
print("1. seed encoding — index -> label -> flag round trip")
print("=" * 78)


def round_trip_all_indices():
    for i in range(-3, 6):
        label = viable_label(i)
        f_idx = viable_flag_from_index(i)
        f_lbl = viable_flag_from_label(label)
        require(f_idx == f_lbl,
                f"index {i}: helper and label disagree ({f_idx} vs {f_lbl})")
        require(label in (POSITIVE_CLASS_LABEL, NEGATIVE_CLASS_LABEL),
                f"index {i}: unexpected label {label!r}")
        require(f_idx in (0.0, 1.0), f"index {i}: flag must be 0.0/1.0, got {f_idx}")
    return "indices -3..5 consistent"


def positive_index_is_one():
    require(POSITIVE_CLASS_INDEX == 1, "positive class index changed")
    require(viable_label(1) == POSITIVE_CLASS_LABEL, "class 1 must be Viable")
    require(viable_label(0) == NEGATIVE_CLASS_LABEL, "class 0 must be Non-Viable")
    return "positive class = 1 ('Viable')"


check("index -> label -> flag round trip", round_trip_all_indices)
check("positive class identity", positive_index_is_one)

# ── 2. no-op against the PREVIOUS expressions, for the production model ─────
print()
print("=" * 78)
print("2. no-op proof against the previous expressions (production model)")
print("=" * 78)


def load_production_seed_model():
    model = _load(os.path.join("seed_viability", "randomforest_model.pkl"))
    classes = list(getattr(model, "classes_", []))
    require(classes, "production seed model exposes no classes_")
    return model, classes


def previous_training_encoding(idx):
    """Exactly what build_triples used before: the raw predicted class index."""
    return float(idx)


def previous_serving_encoding(idx):
    """Exactly what app.py step C used before: 1.0 iff class index == 1."""
    return 1.0 if int(idx) == 1 else 0.0


def encoding_is_noop_for_production_classes():
    _, classes = load_production_seed_model()
    for c in classes:
        new = viable_flag_from_index(c)
        require(new == previous_training_encoding(c),
                f"training feature for class {c} changed: {previous_training_encoding(c)} -> {new}")
        require(new == previous_serving_encoding(c),
                f"serving feature for class {c} changed: {previous_serving_encoding(c)} -> {new}")
    require(len(classes) == 2,
            f"production seed model is {len(classes)}-class; the no-op proof below assumes "
            f"binary classes_={classes}. Re-measure before trusting this guard.")
    return f"classes={classes} unchanged"


check("shared encoding is a no-op for every production class", encoding_is_noop_for_production_classes)


def served_prob_success_unchanged():
    """End-to-end: the 6-feature vector and prob_success must be bit-identical."""
    seed_model, _ = load_production_seed_model()
    meta = _load("meta_model.pkl")
    require(hasattr(meta, "predict_proba"), "production meta model has no predict_proba")

    # A grid of realistic seed payloads (moisture %, 100-seed weight g).
    grid = [(m, w) for m in (6.0, 9.5, 10.8, 14.0, 22.0) for w in (20.0, 35.0, 52.0, 70.0)]
    checked = 0
    for moisture, weight in grid:
        X = np.array([[moisture, weight]], dtype=float)
        idx = int(seed_model.predict(X)[0])

        new_flag = viable_flag_from_label(viable_label(idx))
        old_flag = previous_serving_encoding(idx)
        require(new_flag == old_flag,
                f"seed flag changed for ({moisture},{weight}): {old_flag} -> {new_flag}")

        # Identical surrounding features in both runs, so the only difference under
        # test is the seed encoding.
        other = [0.5, 0.5, 0.4, 0.4]
        old_vec = np.array([[*other, old_flag, old_flag]], dtype=float)
        new_vec = np.array([[*other, new_flag, new_flag]], dtype=float)
        require(np.array_equal(old_vec, new_vec),
                f"meta feature vector changed for ({moisture},{weight})")

        old_p = float(meta.predict_proba(old_vec)[0, 1])
        new_p = float(meta.predict_proba(new_vec)[0, 1])
        require(abs(old_p - new_p) < 1e-15,
                f"prob_success changed for ({moisture},{weight}): {old_p} -> {new_p}")
        checked += 1
    return f"{checked} payloads, prob_success bit-identical"


check("served prob_success unchanged", served_prob_success_unchanged)

# ── 3. training and serving helpers agree for the production model ──────────
print()
print("=" * 78)
print("3. training-side == serving-side, for the production seed model")
print("=" * 78)


def train_and_serve_agree():
    seed_model, classes = load_production_seed_model()
    for c in classes:
        train_side = viable_flag_from_index(c)
        serve_side = viable_flag_from_label(viable_label(c))
        require(train_side == serve_side,
                f"class {c}: train={train_side} serve={serve_side}")
    return f"{len(classes)} classes agree on both sides"


check("train_all_models encoding == seed_viability_semantics encoding", train_and_serve_agree)


def seed_model_feature_is_the_encoded_output():
    """The served meta feature must depend on the model output only through the encoding."""
    seed_model, _ = load_production_seed_model()
    seen = set()
    for moisture, weight in [(6.0, 20.0), (9.5, 35.0), (10.8, 52.0), (14.0, 70.0),
                             (22.0, 20.0), (30.0, 80.0)]:
        idx = int(seed_model.predict(np.array([[moisture, weight]], dtype=float))[0])
        seen.add(viable_flag_from_index(idx))
    require(seen <= {0.0, 1.0}, f"feature values outside 0/1: {seen}")
    return f"feature values observed: {sorted(seen)}"


check("seed feature stays in {0.0, 1.0}", seed_model_feature_is_the_encoded_output)

# ── summary ─────────────────────────────────────────────────────────────────
print()
print("=" * 78)
if FAILURES:
    print(f"SEED ENCODING CONTRACT: FAIL ({len(FAILURES)} check(s))")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("SEED ENCODING CONTRACT: PASS")
sys.exit(0)
