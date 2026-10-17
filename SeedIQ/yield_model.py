"""Served classical yield regressor for the ``Crop + Area_Hectares`` contract.

Model M (read-only experiment, approved for production)
========================================================
    HistGradientBoostingRegressor(max_iter=400, learning_rate=0.08)
    fitted on      log(Yield_Tonnes / Area_Hectares)
    returning      exp(prediction) * Area_Hectares   -> total Yield_Tonnes

WHY THIS TARGET
---------------
The yield model is judged by a ±25% RELATIVE tolerance on yield, and the app
displays the prediction divided by area (t/ha). Squared error on district
totals is dominated by the largest districts, so low-yield rows — the majority
of the table, under 1 t/ha — are allowed to drift outside the tolerance.
Fitting the log of yield-per-hectare makes squared error approximate *relative*
error, which is exactly what the ±25% threshold measures.

Relative error is algebraically identical judged on the total or on the
per-hectare figure (the area cancels), so this changes the loss geometry, not
the quantity being predicted.

CONTRACT UNCHANGED
------------------
Inputs are still the same 23 columns (``Area_Hectares`` + one dummy per crop)
and the output is still the district's total ``Yield_Tonnes`` in tonnes, so
``app.py`` can keep dividing by area, the feature manifest is untouched and the
API/Android payloads do not change. No Season, Year or District is involved.

The area is read from the ``Area_Hectares`` column of the feature frame, which
is column 0 of the published manifest order — never from a separate argument —
so ``fit(X, y)`` / ``predict(X)`` keep the standard scikit-learn signature that
``cross_val_score``, ``cross_val_predict`` and ``app.py`` rely on.
"""

from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.exceptions import NotFittedError

# Column holding the area in the published 23-feature contract
# (``models/yield_feature_manifest.json`` -> feature_columns[0]).
AREA_COLUMN = "Area_Hectares"

# Approved hyper-parameters for the served classical yield model. Kept here so
# training and any re-derivation share a single definition.
APPROVED_HYPERPARAMS = {"max_iter": 400, "learning_rate": 0.08}


class LogPerHaRegressor(RegressorMixin, BaseEstimator):
    """Predict log(yield per hectare), return total ``Yield_Tonnes``.

    Parameters
    ----------
    regressor : sklearn regressor, optional
        Fit on ``log(Yield_Tonnes / Area_Hectares)``. Defaults to
        ``HistGradientBoostingRegressor(**APPROVED_HYPERPARAMS)``.
    min_target : float
        Floor on per-hectare yield inside the log, guarding the 0-division.
    min_area : float
        Floor applied to area when converting between total and per-hectare.
    """

    def __init__(self, regressor=None, min_target=1e-12, min_area=1e-9):
        self.regressor = regressor
        self.min_target = min_target
        self.min_area = min_area

    # -- area is part of the features, not an extra argument --------------
    def _area(self, X):
        if hasattr(X, "columns"):
            if AREA_COLUMN not in X.columns:
                raise ValueError(
                    f"Yield feature frame is missing the {AREA_COLUMN!r} column "
                    f"(found {list(X.columns)}). The served yield contract is "
                    f"{AREA_COLUMN} + crop dummies -> Yield_Tonnes."
                )
            return np.asarray(X[AREA_COLUMN], dtype=float)
        arr = np.asarray(X)
        if arr.ndim != 2 or arr.shape[1] == 0:
            raise ValueError(f"Expected a 2-D feature matrix, got shape {arr.shape}.")
        # Manifest order puts Area_Hectares first.
        return np.asarray(arr[:, 0], dtype=float)

    @staticmethod
    def _n_features(X):
        if hasattr(X, "shape"):
            return int(X.shape[1])
        return int(np.asarray(X).shape[1])

    def fit(self, X, y):
        area = np.maximum(self._area(X), self.min_area)
        y = np.asarray(y, dtype=float)
        target = np.log(np.maximum(y / area, self.min_target))

        base = self.regressor
        if base is None:
            base = HistGradientBoostingRegressor(
                random_state=42, **APPROVED_HYPERPARAMS)
        # Clone so the constructor parameter is never mutated in place and the
        # wrapper stays clone-able for cross_val_score / cross_val_predict.
        self.regressor_ = clone(base) if hasattr(base, "get_params") else base
        self.regressor_.fit(X, target)
        self.n_features_in_ = self._n_features(X)
        return self

    def predict(self, X):
        if not hasattr(self, "regressor_"):
            raise NotFittedError(
                f"This {type(self).__name__} instance is not fitted yet; "
                "call 'fit' before using this estimator."
            )
        area = np.maximum(self._area(X), self.min_area)
        return np.exp(np.asarray(self.regressor_.predict(X), dtype=float)) * area


def make_yield_model(random_state=42):
    """The approved served classical yield model (Model M)."""
    return LogPerHaRegressor(
        regressor=HistGradientBoostingRegressor(
            random_state=random_state, **APPROVED_HYPERPARAMS))
