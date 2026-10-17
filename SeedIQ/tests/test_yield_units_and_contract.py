#!/usr/bin/env python3
"""Tests for yield units/area semantics and the experimental district contract.

Covers the failure modes the audit found: per-hectare vs total-tonnes confusion,
district aggregate area treated as a field, unsupported inputs silently ignored,
missing ground truth, and unseen crops/districts.

Run:
    cd SeedIQ && ../.freebuff/venv/bin/python -m pytest tests/test_yield_units_and_contract.py -q
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from experimental_yield_contract import (  # noqa: E402
    CONTRACT_NAME,
    DISTRICT_MANIFEST_FILE,
    DISTRICT_MODEL_FILE,
    SUPPORTED_INPUTS,
    UNSUPPORTED_INPUTS,
    UnsupportedInputError,
    DistrictYieldContract,
)
from yield_semantics import (  # noqa: E402
    AREA_KIND_DISTRICT,
    AREA_KIND_FIELD,
    BASIS_DISTRICT_AGGREGATE,
    BASIS_FIELD_MEASUREMENT,
    UNIT_TOTAL,
    UNIT_YIELD_PER_HECTARE,
    AreaSemanticsError,
    per_hectare_from_total,
    scale_per_hectare_to_total,
    validate_area,
    validate_basis,
)

ARTIFACT_AVAILABLE = os.path.exists(DISTRICT_MODEL_FILE) and os.path.exists(DISTRICT_MANIFEST_FILE)
needs_artifact = pytest.mark.skipif(
    not ARTIFACT_AVAILABLE,
    reason="experimental district artifact not built (run train_district_yield_model.py)")


# --------------------------------------------------------------------------- #
# Units and area validation
# --------------------------------------------------------------------------- #
def test_per_hectare_is_total_divided_by_area():
    assert per_hectare_from_total(20.0, 10.0) == pytest.approx(2.0)


def test_units_are_distinct_and_labelled():
    assert UNIT_YIELD_PER_HECTARE == "tonnes per hectare"
    assert UNIT_TOTAL == "tonnes"
    assert UNIT_YIELD_PER_HECTARE != UNIT_TOTAL


@pytest.mark.parametrize("bad", [None, "abc", float("nan"), float("inf"), 0, -1, True])
def test_invalid_areas_are_rejected(bad):
    with pytest.raises(AreaSemanticsError):
        validate_area(bad)


def test_valid_area_is_returned_as_float():
    assert validate_area("2.5") == pytest.approx(2.5)
    assert isinstance(validate_area(3), float)


# --------------------------------------------------------------------------- #
# Scaling: per-hectare -> total tonnes
# --------------------------------------------------------------------------- #
def test_total_tonnes_is_per_hectare_times_area():
    block = scale_per_hectare_to_total(2.0, 5.0,
                                       area_kind=AREA_KIND_FIELD,
                                       estimate_basis=BASIS_DISTRICT_AGGREGATE)
    assert block["total_tonnes"] == pytest.approx(10.0)
    assert block["units"]["yield_per_hectare"] == UNIT_YIELD_PER_HECTARE
    assert block["units"]["total"] == UNIT_TOTAL


def test_district_estimate_on_a_field_is_flagged_as_extrapolation():
    block = scale_per_hectare_to_total(2.0, 5.0,
                                       area_kind=AREA_KIND_FIELD,
                                       estimate_basis=BASIS_DISTRICT_AGGREGATE)
    assert block["is_extrapolation"] is True
    assert block["caveats"], "an extrapolated total must carry a caveat"


def test_field_measurement_on_a_field_is_not_an_extrapolation():
    block = scale_per_hectare_to_total(2.0, 5.0,
                                       area_kind=AREA_KIND_FIELD,
                                       estimate_basis=BASIS_FIELD_MEASUREMENT)
    assert block["is_extrapolation"] is False
    assert block["caveats"] == []


def test_district_area_with_a_field_estimate_is_refused():
    """A district's planted area is not an individual field."""
    with pytest.raises(AreaSemanticsError) as excinfo:
        scale_per_hectare_to_total(2.0, 500_000.0,
                                   area_kind=AREA_KIND_DISTRICT,
                                   estimate_basis=BASIS_FIELD_MEASUREMENT)
    assert "not an individual field" in str(excinfo.value)


def test_scaling_is_rejected_for_unknown_basis_or_kind():
    with pytest.raises(AreaSemanticsError):
        scale_per_hectare_to_total(2.0, 5.0, estimate_basis="vibes")
    with pytest.raises(AreaSemanticsError):
        scale_per_hectare_to_total(2.0, 5.0, area_kind="back_of_envelope")


def test_negative_per_hectare_is_rejected():
    with pytest.raises(AreaSemanticsError):
        scale_per_hectare_to_total(-1.0, 5.0)


def test_validate_basis_rejects_unknown_values():
    assert validate_basis(BASIS_DISTRICT_AGGREGATE) == BASIS_DISTRICT_AGGREGATE
    with pytest.raises(AreaSemanticsError):
        validate_basis("district-ish")


# --------------------------------------------------------------------------- #
# Experimental contract (artifact-dependent)
# --------------------------------------------------------------------------- #
@needs_artifact
def test_contract_loads_and_declares_its_limits():
    contract = DistrictYieldContract()
    assert contract.available, contract.load_error
    info = contract.contract_info()
    assert info["name"] == CONTRACT_NAME
    assert info["inputs"] == list(SUPPORTED_INPUTS)
    assert info["level"] == "district"
    assert info["is_field_level_prediction"] is False
    assert info["area_is_a_model_feature"] is False
    assert info["season_supported"] is False
    assert info["dataset_synthetic"] is False
    assert "season" in info["unsupported_inputs"]
    assert info["validation"]["unseen_district_years"]["test_within_25pct"] > 0.5


@needs_artifact
def test_prediction_returns_labelled_per_hectare_and_total():
    contract = DistrictYieldContract()
    result = contract.predict("Rice", "Bangalore", 4.0)
    assert result["units"] == UNIT_YIELD_PER_HECTARE
    assert result["total_units"] == UNIT_TOTAL
    assert result["yield_per_hectare"] > 0
    assert result["total_tonnes"] == pytest.approx(result["yield_per_hectare"] * 4.0, rel=1e-3)
    assert result["is_field_level_prediction"] is False
    assert result["level"] == "district"
    assert result["is_extrapolation"] is True
    assert result["inputs_used"] == ["crop", "district"]
    assert result["inputs_ignored"] == []


@needs_artifact
def test_per_hectare_estimate_does_not_depend_on_the_field_area():
    """The audit's Bug 2: the reported t/ha must not move with the area sent."""
    contract = DistrictYieldContract()
    small = contract.predict("Rice", "Bangalore", 0.5)["yield_per_hectare"]
    large = contract.predict("Rice", "Bangalore", 5000.0)["yield_per_hectare"]
    assert small == pytest.approx(large, rel=1e-9)


@needs_artifact
def test_total_tonnes_scales_linearly_with_area():
    contract = DistrictYieldContract()
    one = contract.predict("Rice", "Bangalore", 1.0)["total_tonnes"]
    ten = contract.predict("Rice", "Bangalore", 10.0)["total_tonnes"]
    assert ten == pytest.approx(one * 10.0, rel=1e-3)


@needs_artifact
def test_crop_and_district_are_case_insensitive_but_normalised():
    contract = DistrictYieldContract()
    result = contract.predict("  rIcE ", "bangalore", 2.0)
    assert result["crop"] == "Rice"
    assert result["district"] == "Bangalore"


@needs_artifact
@pytest.mark.parametrize("payload,expected", [
    ({"crop": "quinoa", "district": "Bangalore", "area_hectares": 2.0}, "crop"),
    ({"crop": "Rice", "district": "Atlantis", "area_hectares": 2.0}, "district"),
    ({"crop": "Rice", "district": "Bangalore", "area_hectares": 2.0, "season": "Rabi"}, "season"),
    ({"crop": "Rice", "district": "Bangalore", "area_hectares": 2.0, "rainfall": 100}, "rainfall"),
    ({"crop": "Rice", "district": "Bangalore", "area_hectares": 2.0, "area": 2.0}, "area"),
    ({"crop": "Rice", "district": "Bangalore", "area_hectares": 2.0}, "area_hectares is required"),
])
def test_unsupported_or_missing_inputs_are_refused(payload, expected):
    contract = DistrictYieldContract()
    with pytest.raises(UnsupportedInputError) as excinfo:
        if expected == "area_hectares is required":
            contract.predict(payload["crop"], payload["district"], None)
        else:
            area = payload.pop("area_hectares")
            contract.predict(payload.pop("crop"), payload.pop("district"), area, **payload)
    assert expected in str(excinfo.value)


@needs_artifact
def test_no_silent_default_is_used_for_a_missing_area():
    contract = DistrictYieldContract()
    with pytest.raises(UnsupportedInputError):
        contract.predict("Rice", "Bangalore", None)
    # and a missing crop/district is not defaulted either
    with pytest.raises(UnsupportedInputError):
        contract.predict(None, "Bangalore", 2.0)
    with pytest.raises(UnsupportedInputError):
        contract.predict("Rice", "", 2.0)


@needs_artifact
def test_every_declared_unsupported_input_actually_raises():
    contract = DistrictYieldContract()
    for key in UNSUPPORTED_INPUTS:
        with pytest.raises(UnsupportedInputError):
            contract.predict("Rice", "Bangalore", 2.0, **{key: "x"})


@needs_artifact
def test_invalid_area_is_rejected_by_the_contract():
    contract = DistrictYieldContract()
    with pytest.raises(AreaSemanticsError):
        contract.predict("Rice", "Bangalore", -3)
    with pytest.raises(AreaSemanticsError):
        contract.predict("Rice", "Bangalore", float("nan"))


@needs_artifact
def test_unavailable_artifact_is_reported_not_guessed(tmp_path):
    contract = DistrictYieldContract(model_path=str(tmp_path / "missing.pkl"),
                                     manifest_path=str(tmp_path / "missing.json"))
    assert contract.available is False
    assert contract.load_error
    with pytest.raises(Exception):
        contract.predict("Rice", "Bangalore", 2.0)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
