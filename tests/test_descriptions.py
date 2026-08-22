import pytest

from pipeline.format.descriptions import (
    DescInput,
    build_invoice_desc,
    build_long_desc,
    build_mobile_desc,
    build_retail_desc,
    build_short_desc,
)
from pipeline.models import Attribute, Evidence


@pytest.fixture
def dishwasher() -> DescInput:
    return DescInput(
        brand_display="FRIGIDAIRE®",
        manuf_name="Rheem Manufacturing",
        mpn="PDSH4816AF",
        item_type="Dishwasher",
        series="Professional Series",
        feature="CleanBoost™",
        attributes=[
            Attribute(label="Mounting Type", value="Leg"),
            Attribute(label="Number of Wash Cycles", value="5"),
            Attribute(label="Voltage Rating", value="120", uom="V"),
            Attribute(label="Amperage Rating", value="15", uom="A"),
            Attribute(label="Material", value="Stainless Steel"),
            Attribute(label="Size", value="24 in W x 24-1/4 in D"),
            Attribute(
                label="Depth With Door Open", value="50-1/4", uom="in"
            ),
        ],
        additional="240 kW-hr Annual Energy, 1 to 12 hr Delay Start Hours",
    )


def test_invoice_desc_caps_and_limit(dishwasher):
    out = build_invoice_desc(dishwasher)
    assert len(out) <= 40
    assert out == out.upper()
    assert out.startswith("DISHWASHER")


def test_mobile_desc_matches_ground_truth_pattern(dishwasher):
    assert build_mobile_desc(dishwasher) == (
        "Rheem Manufacturing FRIGIDAIRE®, Dishwasher, Professional Series, "
        "PDSH4816AF"
    )


def test_short_desc_title_formula(dishwasher):
    out = build_short_desc(dishwasher)
    assert out.startswith(
        "FRIGIDAIRE® Professional Series PDSH4816AF Dishwasher With CleanBoost™"
    )
    assert "Leg" in out and "Stainless Steel" in out


def test_long_desc_enumerates_attributes_with_units(dishwasher):
    out = build_long_desc(dishwasher)
    assert out.startswith("FRIGIDAIRE® Dishwasher With CleanBoost™")
    assert "120 V" in out
    assert "15 A" in out
    assert "50-1/4 in Depth With Door Open" in out
    assert out.endswith("Additional Information: 240 kW-hr Annual Energy, 1 to 12 hr Delay Start Hours")


def test_retail_desc_compact(dishwasher):
    out = build_retail_desc(dishwasher)
    assert "Professional Series Dishwasher" in out


def test_builders_survive_missing_optionals():
    bare = DescInput(
        brand_display=None,
        manuf_name=None,
        mpn="X1",
        item_type="Disc",
        series=None,
        feature=None,
        attributes=[],
        additional=None,
    )
    assert "DISC" in build_invoice_desc(bare)
    assert "X1" in build_mobile_desc(bare)
    assert build_short_desc(bare).startswith("X1 Disc")
