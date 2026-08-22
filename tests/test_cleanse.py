from pipeline.cleanse import (
    clean_brand,
    cleanse_row,
    expand_abbrev,
    parse_manuf,
)


def test_clean_brand_filters_placeholders():
    assert clean_brand("-- Unbranded --") is None
    assert clean_brand("-- No Unilog Brand --") is None
    assert clean_brand("-- No DIB Brand --") is None
    assert clean_brand("") is None
    assert clean_brand("  FRIGIDAIRE® ") == "FRIGIDAIRE®"


def test_parse_manuf_with_code():
    info = parse_manuf("Freud Inc (2435)")
    assert info.name == "Freud Inc"
    assert info.code == "2435"


def test_parse_manuf_without_code():
    info = parse_manuf("Mirka Abrasives Inc")
    assert info.name == "Mirka Abrasives Inc"
    assert info.code is None


def test_parse_manuf_dash_is_empty():
    assert parse_manuf("-").name == ""
    assert parse_manuf(None).name == ""


def test_expand_abbrev_word_boundaries():
    table = {"milw": "Milwaukee", "sst": "Stainless Steel"}
    assert expand_abbrev("Milw 14in Metal Disc SST", table) == (
        "Milwaukee 14in Metal Disc Stainless Steel"
    )


def test_expand_abbrev_does_not_touch_inside_words():
    table = {"milw": "Milwaukee"}
    assert expand_abbrev("MILWAUKEE milwaukeeX milw", table) == (
        "MILWAUKEE milwaukeeX Milwaukee"
    )


def test_cleanse_row_end_to_end():
    row = cleanse_row(
        "49-94-0063",
        '49-94-0063 Milw 14"x7/64"x1" Metal Cut Off Disc',
        "-- Unbranded --",
        "-- No Unilog Brand --",
        "-- No DIB Brand --",
        "Milwaukee Accessory (4031)",
    )
    assert row.mfg_part_num == "49-94-0063"
    assert row.e1_brand is None and row.unilog_brand is None and row.dib_brand is None
    assert row.mfr_name == "Milwaukee Accessory"
    assert row.mfr_code == "4031"
    assert "Milwaukee" in row.part_desc
