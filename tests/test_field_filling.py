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
