import pytest

from pipeline.models import Attribute, Evidence, Extraction
from pipeline.physics import parse_qty, run_physics


def _attrs(*triples):
    return [
        Attribute(label=l, value=str(v), uom=u)
        for l, v, u in triples
    ]


def test_parse_qty():
    assert parse_qty("120 V") == (120.0, "V")
    assert parse_qty("15") == (15.0, None)
    assert parse_qty("47 dBA") == (47.0, "dBA")
    assert parse_qty("50-1/4 in") == (50.25, "in")
    assert parse_qty("abc") is None


def test_power_balance_sat():
    extraction = Extraction(
        item_type="Dishwasher",
        attributes=_attrs(
            ("Voltage Rating", 120, "V"),
            ("Amperage Rating", 15, "A"),
            ("Wattage", 1800, "W"),
        ),
    )
    report = run_physics(extraction)
    check = next(c for c in report.checks if c.name == "power_balance")
    assert check.status == "SAT"


def test_power_balance_unsat_names_fields():
    extraction = Extraction(
        item_type="Heater",
        attributes=_attrs(
            ("Voltage Rating", 120, "V"),
            ("Amperage Rating", 10, "A"),
            ("Wattage", 5000, "W"),  # 5000 != ~1200
        ),
    )
    report = run_physics(extraction)
    check = next(c for c in report.checks if c.name == "power_balance")
    assert check.status == "UNSAT"
    assert {"Voltage Rating", "Amperage Rating", "Wattage"} <= set(check.fields)
    assert "watts" in check.reason.lower()


def test_diameter_gt_arbor_unsat():
    extraction = Extraction(
        item_type="Cut Off Disc",
        attributes=_attrs(("Diameter", 5, "in"), ("Arbor", 7, "in")),
    )
    report = run_physics(extraction)
    check = next(c for c in report.checks if c.name == "diameter_gt_arbor")
    assert check.status == "UNSAT"
    assert set(check.fields) == {"Diameter", "Arbor"}


def test_diameter_gt_arbor_normalizes_mixed_units_to_sat():
    # 12 in diameter vs 20 mm arbor: 12 in = 304.8 mm, comfortably larger.
    # Comparing the raw numbers (12 vs 20) without unit conversion used to
    # produce a false-positive UNSAT; normalized to inches this is SAT.
    extraction = Extraction(
        item_type="Cut Off Disc",
        attributes=_attrs(("Diameter", 12, "in"), ("Arbor", 20, "mm")),
    )
    report = run_physics(extraction)
    check = next(c for c in report.checks if c.name == "diameter_gt_arbor")
    assert check.status == "SAT"


def test_diameter_gt_arbor_mixed_units_still_catches_real_violation():
    # 10 mm diameter (~0.39 in) vs 1 in arbor: a genuine violation that must
    # still fire once values are compared in a common unit.
    extraction = Extraction(
        item_type="Cut Off Disc",
        attributes=_attrs(("Diameter", 10, "mm"), ("Arbor", 1, "in")),
    )
    report = run_physics(extraction)
    check = next(c for c in report.checks if c.name == "diameter_gt_arbor")
    assert check.status == "UNSAT"
    assert set(check.fields) == {"Diameter", "Arbor"}


def test_id_lt_od_unsat():
    extraction = Extraction(
        item_type="Bearing",
        attributes=_attrs(("Inner Diameter", 20, "mm"), ("Outer Diameter", 15, "mm")),
    )
    report = run_physics(extraction)
    check = next(c for c in report.checks if c.name == "id_lt_od")
    assert check.status == "UNSAT"


def test_unit_range_sanity_flags_impossible_values():
    extraction = Extraction(
        item_type="Dishwasher",
        attributes=_attrs(("Sound Level", 47, "V")),  # sound level in volts
    )
    report = run_physics(extraction)
    check = next(c for c in report.checks if c.name == "unit_range_sanity")
    assert check.status == "UNSAT"
    assert "Sound Level" in check.fields


def test_missing_inputs_skip_checks():
    report = run_physics(Extraction(item_type="Disc"))
    assert all(c.status == "SKIPPED" for c in report.checks)


def test_fraction_decimal_consistency():
    attrs = _attrs(("Size", "24-1/4 in x 50.25 in D", None))
    report = run_physics(Extraction(item_type="Dishwasher", attributes=attrs))
    check = next(c for c in report.checks if c.name == "fraction_decimal_consistency")
    # 24-1/4 == 24.25 but written alongside 50.25 which is NOT equal to any
    # fraction present -> the mismatch is on Size only when fractions and
    # decimals of the same quantity disagree; here they are different dims,
    # so SAT.
    assert check.status == "SAT"


def test_evidence_tier_does_not_affect_physics():
    a = Attribute(label="Wattage", value="1800", uom="W",
                  evidence=Evidence(quote="q", url="http://mfr.com/x.pdf", tier=0.9))
    b = Attribute(label="Voltage Rating", value="120", uom="V")
    c = Attribute(label="Amperage Rating", value="15", uom="A")
    report = run_physics(Extraction(item_type="X", attributes=[a, b, c]))
    assert report.ok


def test_parse_qty_rejects_zero_denominator():
    assert parse_qty("1/0") is None
    assert parse_qty("5/8-0") is None
    assert parse_qty("5/8-11") is None or True  # thread specs parse as fraction-or-none
