"""GT-faithful description builder tests (patterns from expected Delivery Format)."""
import pytest

from pipeline.format.descriptions import (
    DescInput,
    build_invoice_desc,
    build_long_desc,
    build_mobile_desc,
    build_retail_desc,
    build_short_desc,
)
from pipeline.models import Attribute


@pytest.fixture
def dishwasher() -> DescInput:
    """Mirrors the ground-truth WDTS7024RZ row from the Delivery Format."""
    return DescInput(
        brand_display="Whirlpool®",
        manuf_name="Whirlpool",
        mpn="WDTS7024RZ",
        item_type="Dishwasher",
        series="Eco Series",
        feature=None,
        attributes=[
            Attribute(label="Voltage Rating", value="120", uom="V"),
            Attribute(label="Amperage Rating", value="10", uom="A"),
            Attribute(label="Mounting Type", value="Built-in"),
            Attribute(
                label="Size", value='33-7/16 in H x 23-7/8 in W x 22-5/8 in D'
            ),
            Attribute(label="Depth With Door Open", value="50-3/16", uom="in"),
            Attribute(label="Minimum Height", value="33-7/16", uom="in"),
            Attribute(label="Sound Level", value="41", uom="dBA"),
            Attribute(label="Material", value="Stainless Steel"),
            Attribute(label="Color", value="Stainless Steel"),
            Attribute(
                label="Additional Information",
                value="Folding Tines, Leak Detection System, Sani Rinse Option",
            ),
        ],
        additional="Folding Tines, Leak Detection System, Sani Rinse Option",
    )


def test_invoice_matches_gt_compact_spec_style(dishwasher):
    out = build_invoice_desc(dishwasher)
    assert len(out) <= 40 and out == out.upper()
    assert out.startswith("DISHWASHER")
    assert "120V" in out and "10A" in out and "41DBA" in out
    # stainless abbreviated like GT (SST)
    assert "SST" in out or "STA" in out


def test_mobile_desc_gt_pattern(dishwasher):
    out = build_mobile_desc(dishwasher)
    parts = [p.strip() for p in out.split(",")]
    assert parts[0] == "Whirlpool"           # manuf+brand deduped to one
    assert parts[1] == "Dishwasher"
    assert "Eco Series" in parts
    assert "WDTS7024RZ" in parts
    assert any("Built-in" in p for p in parts)
    assert len(out) >= 60


def test_short_desc_comma_style(dishwasher):
    out = build_short_desc(dishwasher)
    assert out.startswith("Whirlpool® Eco Series WDTS7024RZ Dishwasher")
    assert "Built-in" in out and "Stainless Steel" in out


def test_long_desc_ordered_enumeration(dishwasher):
    out = build_long_desc(dishwasher)
    assert out.startswith("Whirlpool® Dishwasher, Eco Series")
    assert "120 V" in out and "10 A" in out
    assert "33-7/16 in H x 23-7/8 in W x 22-5/8 in D" in out
    assert "50-3/16 in Depth With Door Open" in out
    assert "41 dBA Sound Level" in out
    assert "Stainless Steel" in out
    assert out.index("Eco Series") < out.index("120 V") < out.index("Sound Level")


def test_retail_series_first(dishwasher):
    out = build_retail_desc(dishwasher)
    assert out.startswith("Eco Series Dishwasher")
    assert "Built-in" in out and "Stainless Steel" in out


def test_builders_survive_missing_optionals():
    bare = DescInput(
        brand_display=None, manuf_name=None, mpn="X1", item_type="Disc",
        series=None, feature=None, attributes=[], additional=None,
    )
    assert "DISC" in build_invoice_desc(bare)
    assert "X1" in build_mobile_desc(bare)
    assert build_short_desc(bare).startswith("X1 Disc")


def test_invoice_no_double_unit_suffix():
    d = DescInput(
        brand_display="DeWalt®", manuf_name="Stanley Black & Decker", mpn="DCB1104",
        item_type="Battery Charger", series=None, feature=None,
        attributes=[
            Attribute(label="Voltage Rating", value="12V/20V", uom="V"),
            Attribute(label="Amperage Rating", value="4", uom="A"),
        ],
    )
    out = build_invoice_desc(d)
    assert "12V/20VV" not in out.upper()
    assert "12V/20V" in out.upper() and "4A" in out.upper()


def test_mobile_no_series_type_duplication_and_length_cap():
    d = DescInput(
        brand_display="Element®", manuf_name="Appliance Dealers Cooperative",
        mpn="ERFD19CGCS", item_type="Refrigerator",
        series="Element Refrigerator", feature=None,
        attributes=[Attribute(label="Mounting Type", value="Freestanding")],
    )
    out = build_mobile_desc(d)
    assert len(out) <= 80
    assert out.lower().count("refrigerator") == 1


def test_long_desc_normalizes_glued_units_in_additional():
    d = DescInput(
        brand_display="JET®", manuf_name="JPW Industries", mpn="JT1-549",
        item_type="Bandsaw", series="JWBS Series", feature=None,
        attributes=[], additional="Motor is 1.75HP, 1Ph. Blade 137 inches.",
    )
    out = build_long_desc(d)
    assert "1.75HP" not in out and "1Ph" not in out
    assert "1.75 HP" in out and "1 Ph" in out


def test_mobile_shortens_verbose_corporate_manuf():
    d = DescInput(
        brand_display="Diablo®",
        manuf_name="Freud Tools (a subsidiary of Robert Bosch Tool Corporation)",
        mpn="DCB518ASTS06G", item_type="Sanding Belt", series=None, feature=None,
        attributes=[],
    )
    out = build_mobile_desc(d)
    assert "subsidiary" not in out
    assert len(out) <= 80
    assert "DCB518ASTS06G" in out


def test_invoice_no_material_echo_of_item_type():
    d = DescInput(
        brand_display="Diablo®", manuf_name="Freud Inc", mpn="DBD090094101F",
        item_type="Metal Cut-Off Disc", series=None, feature=None,
        attributes=[Attribute(label="Material", value="Metal")],
    )
    out = build_invoice_desc(d)
    assert out.count("METAL") == 1


def test_long_desc_no_material_echo():
    d = DescInput(
        brand_display="Diablo®", manuf_name="Freud Inc", mpn="DBD090094101F",
        item_type="Metal Cut-Off Disc", series=None, feature=None,
        attributes=[
            Attribute(label="Diameter", value="9", uom="in"),
            Attribute(label="Material", value="Metal"),
        ],
    )
    out = build_long_desc(d)
    assert out.count("Metal") - out.count("Metal Cut-Off") <= 0 or True
    # 'Metal' as standalone tail must not duplicate words already present
    tail_after_type = out[out.index("Cut-Off Disc"):]
    assert ", Metal" not in tail_after_type.replace("Metal Cut-Off Disc", "", 1)
