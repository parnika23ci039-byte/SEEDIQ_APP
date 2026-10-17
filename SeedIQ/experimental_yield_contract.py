"""Experimental prediction contract: Crop + District -> district-level tonnes/hectare.

Why this contract exists
------------------------
The served yield endpoint accepts ``Crop + Area_Hectares``, where the area is a
**model feature** taken from ICRISAT *district-level annual statistics*. Two
honest limits follow:

1. ``Crop + Area`` cannot separate district-year outcomes. The one extra input
   the source table genuinely contains is ``District``.
2. The area is a district aggregate. Feeding a farmer's 2 ha field into it makes
   the reported tonnes/hectare move with that field size (measured up to a 62%
   relative spread at fixed crop), so the number is not a function of the crop
   and place alone.

This experimental contract fixes both: the estimate is
``f(Crop, District) -> tonnes per hectare`` with **no area term**, and the total
for a field is the explicit arithmetic product ``t/ha x field area`` produced by
``yield_semantics.scale_per_hectare_to_total``, labelled as the extrapolation it
is.

Honesty rules enforced here
---------------------------
* Crop and District must come from the trained vocabulary. There is **no**
  silent fallback: an unseen crop or district is rejected. (Measured: the
  district model does not beat a crop-median baseline on districts held out
  entirely, so pretending to serve one would overstate accuracy.)
* ``season`` is **rejected**, not ignored: the training table is annual district
  statistics with no season dimension, so no season-resolved prediction exists.
* Weather, soil, nutrient and irrigation inputs are **rejected**: no verified
  per-district, per-crop, per-year values aligned to the training rows are
  available at inference time, and inventing defaults is not allowed.
* ``area_hectares`` is required (no default) and is used only for the arithmetic
  conversion to total tonnes, never as a model feature.
* The result is always labelled district-level; it is never presented as a
  field-level measurement.

The contract is strictly experimental: it loads its own artifact from
``models/experimental/`` and never touches the production model, manifest or
registry.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

# Registered for unpickling: the experimental artifact is a
# yield_model_experimental.PerHectareRegressor, and pickle resolves the class by
# module name at load time.
from yield_model_experimental import PerHectareRegressor  # noqa: F401
from yield_semantics import (
    AREA_KIND_FIELD,
    BASIS_DESCRIPTIONS,
    BASIS_DISTRICT_AGGREGATE,
    UNIT_TOTAL,
    UNIT_YIELD_PER_HECTARE,
    AreaSemanticsError,
    describe_basis,
    scale_per_hectare_to_total,
    validate_area,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXPERIMENTAL_MODEL_DIR = os.path.join(SCRIPT_DIR, "models", "experimental")
DISTRICT_MODEL_FILE = os.path.join(EXPERIMENTAL_MODEL_DIR, "district_yield_model.pkl")
DISTRICT_MANIFEST_FILE = os.path.join(EXPERIMENTAL_MODEL_DIR, "district_yield_manifest.json")

CONTRACT_NAME = "experimental-district-yield-v1"
LEVEL_DISTRICT = "district"
IS_FIELD_LEVEL = False

#: Inputs the caller may supply.
SUPPORTED_INPUTS: Tuple[str, ...] = ("crop", "district", "area_hectares")

#: Inputs that are deliberately NOT accepted, with the reason a caller sees.
UNSUPPORTED_INPUTS: Dict[str, str] = {
    "season": (
        "the yield training table is real ICRISAT annual district statistics with no "
        "season dimension, so no season-resolved model exists"
    ),
    "year": (
        "the model is fitted across 2000-2017 annual statistics and has no time dimension; "
        "a year-specific estimate would need a different model"
    ),
    "rainfall": "no verified per-district, per-year rainfall value is aligned to the training rows",
    "temperature": "no verified per-district, per-year temperature value is aligned to the training rows",
    "humidity": "no verified per-district, per-year humidity value is aligned to the training rows",
    "soil_type": "no verified per-district soil series aligned to the training rows",
    "soil_ph": "no verified per-district soil pH aligned to the training rows",
    "nitrogen": "the yield training rows carry no nutrient measurements",
    "phosphorus": "the yield training rows carry no nutrient measurements",
    "potassium": "the yield training rows carry no nutrient measurements",
    "fertilizer": "the yield training rows carry no fertilizer measurements",
    "irrigation": "the yield training rows carry no irrigation measurements",
    "area": (
        "the legacy `area` alias is not part of this contract; send `area_hectares` "
        "so the unit is never ambiguous"
    ),
}


class UnsupportedInputError(ValueError):
    """A caller supplied an input this contract does not support (-> HTTP 400)."""


class ExperimentalModelUnavailable(RuntimeError):
    """The experimental artifact is missing or unreadable (-> HTTP 503)."""


def _nearest(candidate: str, vocabulary: List[str]) -> List[str]:
    """A few close vocabulary entries, for an actionable error message."""
    text = str(candidate or "").strip().lower()
    scored = sorted(vocabulary, key=lambda v: (v.lower() not in text, len(v)))
    return scored[:8]


class DistrictYieldContract:
    """Loads the experimental artifact and serves validated district-level estimates."""

    def __init__(self, model_path: str = DISTRICT_MODEL_FILE,
                 manifest_path: str = DISTRICT_MANIFEST_FILE):
        self.model_path = model_path
        self.manifest_path = manifest_path
        self._lock = threading.Lock()
        self._model: Any = None
        self._manifest: Optional[Dict[str, Any]] = None
        self._load_error: Optional[str] = None

    # ------------------------------------------------------------------ load
    def _load(self) -> None:
        if self._model is not None or self._load_error is not None:
            return
        try:
            import joblib
            with open(self.manifest_path, "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
            model = joblib.load(self.model_path)
            for field in ("feature_columns", "crop_options", "district_options"):
                if not manifest.get(field):
                    raise ValueError(f"manifest is missing {field!r}")
            width = getattr(model, "n_features_in_", None)
            if width is not None and int(width) != len(manifest["feature_columns"]):
                raise ValueError(
                    f"artifact expects {width} features but the manifest declares "
                    f"{len(manifest['feature_columns'])}"
                )
            self._manifest = manifest
            self._model = model
        except Exception as exc:  # noqa: BLE001 - reported as 503 by the caller
            self._load_error = f"{type(exc).__name__}: {exc}"

    @property
    def available(self) -> bool:
        with self._lock:
            self._load()
            return self._model is not None

    @property
    def load_error(self) -> Optional[str]:
        with self._lock:
            self._load()
            return self._load_error

    @property
    def manifest(self) -> Dict[str, Any]:
        with self._lock:
            self._load()
            return dict(self._manifest or {})

    def crop_options(self) -> List[str]:
        return list(self.manifest.get("crop_options") or [])

    def district_options(self) -> List[str]:
        return list(self.manifest.get("district_options") or [])

    # -------------------------------------------------------------- contract
    def contract_info(self) -> Dict[str, Any]:
        manifest = self.manifest
        return {
            "name": CONTRACT_NAME,
            "status": "experimental",
            "inputs": list(SUPPORTED_INPUTS),
            "required_inputs": ["crop", "district", "area_hectares"],
            "unsupported_inputs": dict(UNSUPPORTED_INPUTS),
            "output_units": UNIT_YIELD_PER_HECTARE,
            "level": LEVEL_DISTRICT,
            "is_field_level_prediction": IS_FIELD_LEVEL,
            "area_is_a_model_feature": False,
            "season_supported": False,
            "dataset": manifest.get("dataset"),
            "dataset_provenance": manifest.get("dataset_provenance"),
            "dataset_synthetic": manifest.get("dataset_synthetic"),
            "semantics": manifest.get("semantics"),
            "validation": manifest.get("validation"),
            "model_artifact": os.path.relpath(self.model_path, SCRIPT_DIR),
        }

    # ------------------------------------------------------------ validation
    @staticmethod
    def _reject_unsupported(payload: Dict[str, Any]) -> None:
        supplied = [key for key, value in payload.items()
                    if key in UNSUPPORTED_INPUTS and value not in (None, "", [])]
        if not supplied:
            return
        details = "; ".join(f"{key}: {UNSUPPORTED_INPUTS[key]}" for key in sorted(supplied))
        raise UnsupportedInputError(
            f"Unsupported input(s) for the {CONTRACT_NAME} contract — {details}. "
            f"Supported inputs are {list(SUPPORTED_INPUTS)}."
        )

    def _validate_choice(self, value: Any, vocabulary: List[str], field: str) -> str:
        if value is None or str(value).strip() == "":
            raise UnsupportedInputError(
                f"{field} is required for the {CONTRACT_NAME} contract; it is what makes "
                f"the estimate district-level. Supported values: {len(vocabulary)} "
                f"{field}s, e.g. {vocabulary[:4]}."
            )
        text = str(value).strip()
        for option in vocabulary:
            if option.lower() == text.lower():
                return option
        raise UnsupportedInputError(
            f"{field} {text!r} is not in the trained vocabulary of {len(vocabulary)} "
            f"{field}s. The model has no verified estimate for it and no default is "
            f"invented. Example supported values: {_nearest(text, vocabulary)}."
        )

    # ------------------------------------------------------------- inference
    def predict(self, crop: Any, district: Any, area_hectares: Any,
                **extra: Any) -> Dict[str, Any]:
        """Return a labelled district-level estimate, or raise a typed error.

        Raises
        ------
        UnsupportedInputError
            Missing/unseen crop or district, a required area, or any input the
            contract does not support (including ``season`` and the legacy
            ``area`` alias).
        ExperimentalModelUnavailable
            The experimental artifact or manifest cannot be loaded.
        AreaSemanticsError
            The area is not a finite positive number.
        """
        with self._lock:
            self._load()
            if self._model is None:
                raise ExperimentalModelUnavailable(
                    f"experimental district model unavailable ({self._load_error})"
                )
            manifest = dict(self._manifest or {})
            model = self._model

        self._reject_unsupported(extra)
        crops = list(manifest.get("crop_options") or [])
        districts = list(manifest.get("district_options") or [])
        canonical_crop = self._validate_choice(crop, crops, "crop")
        canonical_district = self._validate_choice(district, districts, "district")

        if area_hectares is None:
            raise UnsupportedInputError(
                "area_hectares is required: it is needed to convert the predicted "
                "tonnes/hectare into total tonnes. It is not a model input and no "
                "default area is assumed."
            )
        area = validate_area(area_hectares)

        columns = list(manifest["feature_columns"])
        crop_prefix = manifest.get("crop_feature_prefix", "Crop")
        district_prefix = manifest.get("district_feature_prefix", "District")
        row = {column: 0.0 for column in columns}
        crop_column, district_column = f"{crop_prefix}_{canonical_crop}", f"{district_prefix}_{canonical_district}"
        if crop_column not in row:
            raise UnsupportedInputError(f"model has no feature column {crop_column!r}")
        if district_column not in row:
            raise UnsupportedInputError(f"model has no feature column {district_column!r}")
        row[crop_column] = 1.0
        row[district_column] = 1.0

        import numpy as np
        matrix = np.asarray([[row[column] for column in columns]], dtype=float)
        per_hectare = float(np.asarray(model.predict(matrix), dtype=float)[0])
        if not (per_hectare == per_hectare) or per_hectare <= 0:
            raise ExperimentalModelUnavailable(
                f"artifact produced an unusable estimate ({per_hectare!r})"
            )

        scaled = scale_per_hectare_to_total(
            per_hectare, area,
            area_kind=AREA_KIND_FIELD,
            estimate_basis=BASIS_DISTRICT_AGGREGATE,
        )
        basis = describe_basis(BASIS_DISTRICT_AGGREGATE, AREA_KIND_FIELD)
        return {
            "status": "ok",
            "contract": CONTRACT_NAME,
            "crop": canonical_crop,
            "district": canonical_district,
            "level": LEVEL_DISTRICT,
            "is_field_level_prediction": IS_FIELD_LEVEL,
            "yield_per_hectare": round(scaled["yield_per_hectare"], 4),
            "total_tonnes": round(scaled["total_tonnes"], 4),
            "area_hectares": round(area, 4),
            "units": UNIT_YIELD_PER_HECTARE,
            "total_units": UNIT_TOTAL,
            "estimate_basis": BASIS_DISTRICT_AGGREGATE,
            "basis_description": BASIS_DESCRIPTIONS[BASIS_DISTRICT_AGGREGATE],
            "is_extrapolation": scaled["is_extrapolation"],
            "caveats": list(scaled["caveats"]),
            "inputs_used": ["crop", "district"],
            "inputs_ignored": [],
            "area_used_only_for": "multiplying the per-hectare estimate by the given area",
            "area_kind": AREA_KIND_FIELD,
            "area_kind_description": basis.get("area_kind_description"),
            "model": {
                "artifact": os.path.relpath(self.model_path, SCRIPT_DIR),
                "feature_count": manifest.get("feature_count"),
                "target": manifest.get("target"),
                "crops": len(crops),
                "districts": len(districts),
            },
            "validation": manifest.get("validation"),
            "semantics": manifest.get("semantics"),
        }


#: Process-wide instance (the Flask route reuses it).
contract = DistrictYieldContract()
