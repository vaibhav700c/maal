import csv

import pytest

from pipeline.format.emit import (
    load_headers,
    passthrough_fields,
    write_outputs,
)
from pipeline.models import Attribute, CleanRow, Extraction, RowResult


EXPECTED_CSV = "input/Unihack_ Expected Output - Delivery Format.csv"


def test_load_headers_exact_fidelity():
    headers = load_headers(EXPECTED_CSV)
    assert len(headers) == 252
    assert headers[0] == "MFR URL" and headers[-1] == "Actual Image (Yes/No)"
    with open(EXPECTED_CSV, newline="") as f:
        source = next(csv.reader(f))
    assert headers == source


def _row(mpn="PDSH4816AF", item_type="Dishwasher") -> RowResult:
    clean = CleanRow(mfg_part_num=mpn, part_desc=f"{mpn} {item_type}")
    extraction = Extraction(
        item_type=item_type,
        series=None,
        attributes=[Attribute(label="Voltage Rating", value="120", uom="V")],
    )
    return RowResult(
        mfg_part_num=mpn,
        clean=clean,
        extraction=extraction,
        output_row={
            "MANUFACTURER_PART_NUMBER": mpn,
            "SHORT_DESC": f"{item_type} {mpn}",
        },
    )


def test_passthrough_fields_mapped():
    row = _row()
    out = passthrough_fields(row)
    assert out["Mfg_Part_Num"] == "PDSH4816AF"
    assert out["Part_Desc"] == "PDSH4816AF Dishwasher"
    assert "PART_NUMBER" not in out


def test_write_outputs_roundtrip(tmp_path):
    rows = [_row("A1"), _row("B2"), _row("C3")]
    csv_path, xlsx_path, sidecar_path = write_outputs(rows, tmp_path)
    assert csv_path.read_text(encoding="utf-8-sig").splitlines()[0].startswith("MFR URL")
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        body = list(reader)
    assert len(header) == 252 and len(body) == 3
    idx = header.index("MANUFACTURER_PART_NUMBER")
    assert {r[idx] for r in body} == {"A1", "B2", "C3"}
    assert xlsx_path.exists()
    lines = sidecar_path.read_text().strip().splitlines()
    assert len(lines) == 3


def test_result_csv_header_fidelity_roundtrip(tmp_path):
    headers = load_headers(EXPECTED_CSV)
    rows = [_row(), _row(mpn="WDTS7024RZ")]
    csv_path, _, _ = write_outputs(rows, tmp_path)
    with open(csv_path, newline="") as f:
        written = next(csv.reader(f))
    assert written == headers
    assert written[0] == "MFR URL"
