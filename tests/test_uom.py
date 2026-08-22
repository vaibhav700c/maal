import pytest

from pipeline.format.uom import (
    APPROVED_UOM,
    decimal_to_fraction,
    format_measure,
    normalize_measurement_text,
    normalize_uom,
)


def test_approved_forms_map_to_inch():
    for form in ("inches", "IN.", "inch", '"', "in"):
        assert normalize_uom(form) == "in"


def test_common_units():
    assert normalize_uom("volts") == "V"
    assert normalize_uom("amps") == "A"
    assert normalize_uom("watts") == "W"
    assert normalize_uom("dba") == "dBA"
    assert normalize_uom("feet") == "ft"
    assert normalize_uom("psi") == "psi"
    assert normalize_uom("kwhr") == "kW-hr"
    with pytest.raises(ValueError):
        normalize_uom("furlongs")


def test_decimal_to_fraction_exact():
    assert decimal_to_fraction(0.5) == "1/2"
    assert decimal_to_fraction(0.25) == "1/4"
    assert decimal_to_fraction(0.984375) == "63/64"
    assert decimal_to_fraction(0.75) == "3/4"


def test_decimal_to_fraction_nearest_64th():
    assert decimal_to_fraction(0.505) == "1/2"
    assert decimal_to_fraction(0.333) == "21/64"


def test_format_measure_mixed_number():
    assert format_measure(50.25) == "50-1/4"
    assert format_measure(24) == "24"
    assert format_measure(7 / 64) == "7/64"
    assert format_measure(23 + 7 / 8) == "23-7/8"


def test_normalize_measurement_text_quote_dimensions():
    assert (
        normalize_measurement_text('14"x7/64"x1"')
        == "14 in x 7/64 in x 1 in"
    )


def test_normalize_measurement_text_missing_space():
    assert normalize_measurement_text("24in wide") == "24 in wide"
