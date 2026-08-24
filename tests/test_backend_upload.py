"""Upload parsing must carry brand hints, not drop them."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backend.main import parse_upload as _parse_upload

CSV = (
    "Mfg_Part_Num,Part_Desc,E1_Brand,Unilog_Brand,DIB_Brand,Part_Manuf\n"
    '1700-1PK-BB40,"3/4x60"" Vinyl Elect Tape",-- Unbranded --,-- No Unilog Brand --,3M,3 M Co (5293)\n'
    "9A-570-320,Abranet 2.75x30,-- Unbranded --,-- No Unilog Brand --,-- No DIB Brand --,Mirka Abrasives Inc (MIRUS)\n"
)


def test_parse_upload_carries_brand_columns():
    products = _parse_upload(CSV)
    assert len(products) == 2
    tape = products[0]
    assert tape.mpn == "1700-1PK-BB40"
    assert tape.brand == "3M"
    assert tape.supplier == "3 M Co (5293)"


def test_parse_upload_placeholders_become_none():
    products = _parse_upload(CSV)
    mirka = products[1]
    assert mirka.brand is None
    assert mirka.e1_brand is None
    assert mirka.supplier == "Mirka Abrasives Inc (MIRUS)"
