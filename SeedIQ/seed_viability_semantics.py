"""Canonical seed-viability encoding, shared by training and serving.

The hybrid meta model consumes two seed features. Until now they were built two
different ways:

* **training** (`train_all_models.train_meta.build_triples`) used the raw
  predicted **class index** — ``float(model.predict(...)[0])``;
* **serving** (`app.py`, step C) used a **binary label test** —
  ``1.0 if seed_classical == 'Viable' else 0.0``.

With the current 2-class seed target these two encodings agree by accident
(class index 1 is the only "Viable" class), so nothing is visibly wrong today.
They stop agreeing the moment the seed model is anything other than binary: a
3-class target (for example the real 210-row UCI Seeds table) would put
``{0, 1, 2}`` into the training matrix while serving would still emit
``{0.0, 1.0}`` — a silent train/serve skew that corrupts ``prob_success`` with
no exception raised anywhere.

This module is the single source of truth for that encoding. Both sides import
from here, so the two definitions cannot drift apart again. It is the seed
counterpart of ``yield_semantics.py``.

Scope note: this module only fixes the *encoding*. It does not change the seed
dataset, the seed model, or the meta target.
"""

from __future__ import annotations

# The class index the served API treats as the positive ("Viable") outcome.
# `load_seed_frame` fits on the integer `Viable` column, whose positive value is 1.
POSITIVE_CLASS_INDEX = 1

POSITIVE_CLASS_LABEL = "Viable"
NEGATIVE_CLASS_LABEL = "Non-Viable"


def viable_label(predicted_index, positive_index: int = POSITIVE_CLASS_INDEX) -> str:
    """Map a raw predicted class index to the label the API reports.

    This is the *only* place a class index becomes a seed verdict, so any future
    change to the class layout is made once and applies to training and serving
    together.
    """
    return (POSITIVE_CLASS_LABEL if int(predicted_index) == int(positive_index)
            else NEGATIVE_CLASS_LABEL)


def viable_flag_from_index(predicted_index,
                           positive_index: int = POSITIVE_CLASS_INDEX) -> float:
    """Canonical 0.0/1.0 meta feature from a raw predicted class index (training side)."""
    return 1.0 if int(predicted_index) == int(positive_index) else 0.0


def viable_flag_from_label(label) -> float:
    """Canonical 0.0/1.0 meta feature from an already-decoded verdict (serving side).

    ``viable_flag_from_label(viable_label(i)) == viable_flag_from_index(i)`` for
    every index ``i`` — that identity is what lets the training matrix and the
    served feature vector be built by different code paths and still be equal.
    """
    return 1.0 if str(label) == POSITIVE_CLASS_LABEL else 0.0
