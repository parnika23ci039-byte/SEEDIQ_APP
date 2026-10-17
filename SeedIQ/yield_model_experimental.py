"""The experimental district-level yield estimator: ``Crop + District -> t/ha``.

Kept in its own importable module (not in the training script) so the artifact
can be unpickled by the API: a class defined in ``__main__`` pickle-loads only
when the loading process happens to define the same name in ``__main__``, which
made the first artifact unloadable outside its own training run.

Contract
--------
``fit`` takes tonnes per hectare and fits ``log(t/ha)``; ``predict`` returns
tonnes per hectare directly. There is **no area term anywhere** — no area input,
no area multiplication — so the reported figure cannot drift with whatever area
a client sends. Converting to a field's total tonnes is a separate, explicit
step (``yield_semantics.scale_per_hectare_to_total``).

Compare ``yield_model.LogPerHaRegressor`` (the served production wrapper): that
one takes ``Area_Hectares`` as a feature and returns a district *total*, which
is why the served per-hectare figure moves with the requested area.
"""

from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.ensemble import HistGradientBoostingRegressor

MIN_PER_HA = 1e-9

APPROVED_HYPERPARAMS = {"max_iter": 400, "learning_rate": 0.08}


class PerHectareRegressor(RegressorMixin, BaseEstimator):
    """Fit ``log(yield per hectare)`` and predict tonnes per hectare."""

    def __init__(self, regressor=None, min_target=MIN_PER_HA):
        self.regressor = regressor
        self.min_target = min_target

    @staticmethod
    def _n_features(X):
        return int(X.shape[1]) if hasattr(X, "shape") else int(np.asarray(X).shape[1])

    def fit(self, X, y_per_ha):
        y = np.asarray(y_per_ha, dtype=float)
        if (y < 0).any():
            raise ValueError("Per-hectare yield must not be negative.")
        target = np.log(np.maximum(y, self.min_target))
        base = self.regressor
        if base is None:
            base = HistGradientBoostingRegressor(random_state=42, **APPROVED_HYPERPARAMS)
        self.regressor_ = clone(base) if hasattr(base, "get_params") else base
        self.regressor_.fit(X, target)
        self.n_features_in_ = self._n_features(X)
        return self

    def predict(self, X):
        if not hasattr(self, "regressor_"):
            raise RuntimeError(
                "This PerHectareRegressor instance is not fitted yet; call 'fit' first."
            )
        return np.exp(np.asarray(self.regressor_.predict(X), dtype=float))


def make_per_hectare_model(random_state=42):
    return PerHectareRegressor(
        regressor=HistGradientBoostingRegressor(random_state=random_state,
                                                **APPROVED_HYPERPARAMS))
