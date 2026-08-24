"""Delivery Format columns must be filled whenever the data exists."""
from pipeline.models import Attribute, CleanRow, Extraction
from pipeline.run_batch import build_output_row, parse_qty_for_volume


def _ext(attrs):
    return Extraction(item_type="Dishwasher", brand="Whirlpool", attributes=attrs)


def _clean():
    return CleanRow(
        mfg_part_num="WDT750SAKZ", part_desc="Dishwasher",
        e1_brand="-- Unbranded --", unilog_brand="-- No Unilog Brand --",
        dib_brand="-- No DIB Brand --", mfr_name="Whirlpool",
    )


def test_warranty_and_origin_fill_columns():
    row = build_output_row(_clean(), None, None, _ext([
        Attribute(label="Warranty", value="1 Year Limited"),
        Attribute(label="Country of Origin", value="USA"),
    ]))
    assert row["Warranty"] == "1 Year Limited"
    assert row["Warranty Information"] == "1 Year Limited"
    assert row["Country Of Origin"] == "USA"


def test_barcode_routing_by_standard():
    row = build_output_row(_clean(), None, None, _ext([
        Attribute(label="UPC", value="883049498227"),
        Attribute(label="EAN", value="4012556261348"),
        Attribute(label="GTIN", value="00088304949822"),
    ]))
    assert row["UPC"] == "883049498227"
    assert row["EAN"] == "4012556261348"
    assert row["GTIN"] == "00088304949822"


def test_barcode_label_routes_by_length():
    row = build_output_row(_clean(), None, None, _ext([
        Attribute(label="Barcode", value="4012556261348"),  # 13 -> EAN
    ]))
    assert row.get("EAN") == "4012556261348"
    assert "UPC" not in row


def test_volume_from_capacity():
    row = build_output_row(_clean(), None, None, _ext([
        Attribute(label="Capacity", value="24.8", uom="cu ft"),
    ]))
    assert row["VOLUME"] == "24.8"
    assert row["VOLUME_UOM"] == "cu ft"


def test_volume_requires_unit():
    assert parse_qty_for_volume("24.8") is None
    assert parse_qty_for_volume("24.8", "cu ft") == (24.8, "cu ft")
    assert parse_qty_for_volume("3.5 gal") == (3.5, "gal")


def test_packaging_and_list_price_fill():
    row = build_output_row(_clean(), None, None, _ext([
        Attribute(label="Package Quantity", value="50"),
        Attribute(label="List Price", value="$1,299.00"),
    ]))
    assert row["Selling Qty"] == "50"
    assert row["Selling UOM"] == "each"
    assert row["Standard Packaging Information"] == "50 each"
    assert row["List Price"] == "1299"


def test_combined_size_splits_into_dimension_columns():
    from pipeline.run_batch import parse_size_dimensions
    row = build_output_row(_clean(), None, None, _ext([
        Attribute(label="Size", value="69-7/8 in H x 32-3/4 in W x 36-1/4 in D"),
    ]))
    assert row["HEIGHT"] == "69.875" and row["HEIGHT_UOM"] == "in"
    assert row["WIDTH"] == "32.75"
    assert row["LENGTH"] == "36.25"  # depth maps to LENGTH


def test_size_needs_two_dims_minimum():
    from pipeline.run_batch import parse_size_dimensions
    assert parse_size_dimensions("36 in D") == {}
    dims = parse_size_dimensions("24 in W x 24-1/4 in D")
    assert dims["WIDTH"] == (24.0, "in") and dims["LENGTH"] == (24.25, "in")


def test_prop65_column_from_attribute():
    row = build_output_row(_clean(), None, None, _ext([
        Attribute(label="Prop 65", value="WARNING: Cancer and Reproductive Harm - www.P65Warnings.ca.gov"),
    ]))
    assert "P65Warnings.ca.gov" in row["Prop 65"]


def test_cert_derived_rohs_and_energy_star():
    clean = _clean()
    ext = _ext([]) if False else Extraction(
        item_type="Charger", brand="DeWalt",
        attributes=[],
        certifications=["RoHS Compliant", "ENERGY STAR Certified"],
    )
    row = build_output_row(clean, None, None, ext)
    assert row["RoHS"] == "RoHS Compliant"
    assert row["Energy Star Guide"] == "DEWALT_WDT750SAKZ_Energy_Star_Guide.pdf"


def test_manuals_follow_asset_pattern_only_when_confirmed():
    from pipeline.models import RetrievalResult
    clean = _clean()
    ext = _ext([])
    ret = RetrievalResult(product_url="https://www.whirlpool.com/p/WDT750SAKZ")
    row = build_output_row(clean, None, ret, ext)
    assert row["Instruction/Installation Manual"] == "WHIRLPOOL_WDT750SAKZ_Installation_Manual.pdf"
    assert row["Owners/User Manual"] == "WHIRLPOOL_WDT750SAKZ_Owners_Manual.pdf"
    # no evidence -> no speculative assets
    row2 = build_output_row(clean, None, None, ext)
    assert "Instruction/Installation Manual" not in row2


def test_with_and_approvals_stay_blank_without_data():
    row = build_output_row(_clean(), None, None, _ext([]))
    assert "With" not in row
    assert "Standard/Approvals" not in row
