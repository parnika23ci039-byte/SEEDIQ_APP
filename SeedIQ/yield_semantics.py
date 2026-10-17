"""Yield unit and area semantics for SeedIQ.

The two quantities the app can talk about are NOT interchangeable:

* **yield per hectare** — the only quantity the trained model is evaluated on
  (the +/-25% tolerance is defined on it) and the only figure the API reports;
* **total tonnes** — arithmetic ``per_hectare x area``. It is a product, not a
  model output, and it is only meaningful when the per-hectare figure and the
  area describe the SAME piece of land.

The training table is ICRISAT **district-level annual statistics**: one row is
a whole district's planted area and production for one crop in one year. So:
``Area_Hectares`` in training is a *district* area (10 ha to 612,300 ha in the
Karnataka table), not a farm's field. Multiplying a district average by a
farmer's 2 ha field is an *extrapolation*, and this module labels it as one
instead of letting a product look like a measurement.

Nothing here invents a numeric cutoff for "field scale": the recorded district
areas overlap field scale, so a threshold would be fiction. What is enforced is
that the *kind* of area and the *basis* of the estimate agree, and that every
derived total carries its basis and caveats.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------- #
# Units
# --------------------------------------------------------------------------- #
UNIT_YIELD_PER_HECTARE = "tonnes per hectare"
UNIT_TOTAL = "tonnes"

YIELD_UNITS = {
    "yield_per_hectare": UNIT_YIELD_PER_HECTARE,
    "total": UNIT_TOTAL,
}

# --------------------------------------------------------------------------- #
# Estimate basis — what the per-hectare number is derived from
# --------------------------------------------------------------------------- #
BASIS_DISTRICT_AGGREGATE = "district_aggregate_annual_statistics"
BASIS_FIELD_MEASUREMENT = "field_level_measurement"

BASIS_DESCRIPTIONS = {
    BASIS_DISTRICT_AGGREGATE: (
        "Derived from real district-level annual crop statistics (ICRISAT, "
        "Karnataka 2000-2017). It is a district average, NOT a measurement of "
        "any individual field."
    ),
    BASIS_FIELD_MEASUREMENT: (
        "Derived from measurements of individual fields/plots."
    ),
}

# --------------------------------------------------------------------------- #
# Area kind — what the area being multiplied actually is
# --------------------------------------------------------------------------- #
AREA_KIND_FIELD = "individual_field"
AREA_KIND_DISTRICT = "district_aggregate"

AREA_KIND_DESCRIPTIONS = {
    AREA_KIND_FIELD: "The area of one farmer's field/plot.",
    AREA_KIND_DISTRICT: (
        "The total planted area of a whole district for one crop and year, as "
        "recorded in the ICRISAT aggregate statistics."
    ),
}

EXTRAPOLATION_CAVEAT = (
    "Total tonnes is arithmetic (predicted tonnes/hectare x the given area). "
    "The per-hectare figure is a district-level average, so applying it to an "
    "individual field is an extrapolation with no accuracy guarantee at field "
    "level."
)


class AreaSemanticsError(ValueError):
    """Raised when a yield quantity would be reported with the wrong semantics."""


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate_area(area: Any, field_name: str = "area_hectares") -> float:
    """Return ``area`` as a finite, strictly positive float.

    Rejects ``None``, non-numeric, NaN/inf and non-positive values with a
    message naming the offending field, so a caller can surface a 400 instead
    of letting ``float()`` raise or a NaN propagate into a prediction.
    """
    if area is None:
        raise AreaSemanticsError(f"{field_name} is required (received null).")
    if isinstance(area, bool):
        raise AreaSemanticsError(f"{field_name} must be a number, received a boolean.")
    try:
        value = float(area)
    except (TypeError, ValueError):
        raise AreaSemanticsError(
            f"{field_name} must be a number, received {type(area).__name__}."
        ) from None
    if math.isnan(value) or math.isinf(value):
        raise AreaSemanticsError(f"{field_name} must be finite, received {value!r}.")
    if value <= 0:
        raise AreaSemanticsError(f"{field_name} must be greater than 0, received {value!r}.")
    return value


def validate_basis(basis: str) -> str:
    """Reject an unknown estimate basis rather than describing it loosely."""
    if basis not in BASIS_DESCRIPTIONS:
        raise AreaSemanticsError(
            f"Unknown estimate basis {basis!r}; expected one of {sorted(BASIS_DESCRIPTIONS)}."
        )
    return basis


def validate_area_kind(area_kind: str) -> str:
    if area_kind not in AREA_KIND_DESCRIPTIONS:
        raise AreaSemanticsError(
            f"Unknown area kind {area_kind!r}; expected one of {sorted(AREA_KIND_DESCRIPTIONS)}."
        )
    return area_kind


# --------------------------------------------------------------------------- #
# Conversions
# --------------------------------------------------------------------------- #
def per_hectare_from_total(total_tonnes: float, area_hectares: float) -> float:
    """Total tonnes -> tonnes per hectare. The area must be the SAME land."""
    area = validate_area(area_hectares)
    try:
        total = float(total_tonnes)
    except (TypeError, ValueError):
        raise AreaSemanticsError(
            f"total_tonnes must be a number, received {type(total_tonnes).__name__}."
        ) from None
    if math.isnan(total) or math.isinf(total):
        raise AreaSemanticsError(f"total_tonnes must be finite, received {total!r}.")
    if total < 0:
        raise AreaSemanticsError(f"total_tonnes must not be negative, received {total!r}.")
    return total / area


def scale_per_hectare_to_total(
    per_hectare: float,
    area_hectares: float,
    *,
    area_kind: str = AREA_KIND_FIELD,
    estimate_basis: str = BASIS_DISTRICT_AGGREGATE,
) -> Dict[str, Any]:
    """Multiply a per-hectare estimate by the area it is applied to.

    Returns a block that states the units, the basis and (when the basis is a
    district average applied to an individual field) the extrapolation flag and
    caveat. Raises :class:`AreaSemanticsError` when the area kind and the
    estimate basis describe different pieces of land in a way that is not an
    honest extrapolation — e.g. a whole-district aggregate area multiplied by a
    single-field estimate, presented as that field's production.
    """
    area = validate_area(area_hectares)
    validate_area_kind(area_kind)
    validate_basis(estimate_basis)

    try:
        value = float(per_hectare)
    except (TypeError, ValueError):
        raise AreaSemanticsError(
            f"per_hectare must be a number, received {type(per_hectare).__name__}."
        ) from None
    if math.isnan(value) or math.isinf(value):
        raise AreaSemanticsError(f"per_hectare must be finite, received {value!r}.")
    if value < 0:
        raise AreaSemanticsError(f"per_hectare must not be negative, received {value!r}.")

    if area_kind == AREA_KIND_DISTRICT and estimate_basis != BASIS_DISTRICT_AGGREGATE:
        raise AreaSemanticsError(
            f"A {area_kind!r} area cannot be combined with a "
            f"{estimate_basis!r} estimate: a district's total planted area is not "
            f"an individual field, so the product is not that field's production."
        )

    extrapolation = (area_kind == AREA_KIND_FIELD
                     and estimate_basis == BASIS_DISTRICT_AGGREGATE)
    caveats: List[str] = []
    if extrapolation:
        caveats.append(EXTRAPOLATION_CAVEAT)

    total = value * area
    return {
        "yield_per_hectare": round(value, 6),
        "area_hectares": round(area, 6),
        "total_tonnes": round(total, 6),
        "units": {"yield_per_hectare": UNIT_YIELD_PER_HECTARE, "total": UNIT_TOTAL},
        "estimate_basis": estimate_basis,
        "area_kind": area_kind,
        "is_extrapolation": extrapolation,
        "caveats": caveats,
    }


def describe_basis(estimate_basis: str, area_kind: Optional[str] = None) -> Dict[str, str]:
    """Human-readable semantics for a basis (and optionally an area kind)."""
    validate_basis(estimate_basis)
    out = {"estimate_basis": estimate_basis, "basis_description": BASIS_DESCRIPTIONS[estimate_basis]}
    if area_kind is not None:
        validate_area_kind(area_kind)
        out["area_kind"] = area_kind
        out["area_kind_description"] = AREA_KIND_DESCRIPTIONS[area_kind]
    return out
