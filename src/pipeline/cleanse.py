"""Input cleansing: placeholders, manufacturer parsing, abbreviation expansion."""
import json
import re
from pathlib import Path

from pipeline.models import CleanRow, MfrInfo

PLACEHOLDERS = {
    "-- Unbranded --",
    "-- No Unilog Brand --",
    "-- No DIB Brand --",
}

ABBREV_PATH = Path(__file__).resolve().parents[2] / "data" / "abbreviations.json"

SEED_ABBREVIATIONS = {
    "milw": "Milwaukee",
    "sst": "Stainless Steel",
    "wh": "Water Heater",
    "blk": "Black",
    "brs": "Brass",
    "wht": "White",
    "bk": "Black",
    "led": "LED",
}


def load_abbrev(path: Path = ABBREV_PATH) -> dict[str, str]:
    if path.exists():
        return json.loads(path.read_text())
    return dict(SEED_ABBREVIATIONS)


def save_abbrev(table: dict[str, str], path: Path = ABBREV_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(table, indent=2, sort_keys=True))


def clean_brand(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    stripped = value.strip()
    if stripped in PLACEHOLDERS:
        return None
    return stripped


def parse_manuf(value: str | None) -> MfrInfo:
    if not value or not value.strip() or value.strip() == "-":
        return MfrInfo(name="")
    text = value.strip()
    match = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", text)
    if match:
        name = match.group(1).strip()
        code = match.group(2).strip()
        if name:
            return MfrInfo(name=name, code=code or None)
        return MfrInfo(name=code)
    return MfrInfo(name=text)


def expand_abbrev(text: str, table: dict[str, str]) -> str:
    result = text
    for short, full in table.items():
        result = re.sub(
            rf"\b{re.escape(short)}\b",
            full,
            result,
            flags=re.IGNORECASE,
        )
    return result


def cleanse_row(
    mfg_part_num: str,
    part_desc: str,
    e1_brand: str,
    unilog_brand: str,
    dib_brand: str,
    part_manuf: str,
    abbrev_table: dict[str, str] | None = None,
) -> CleanRow:
    table = abbrev_table if abbrev_table is not None else load_abbrev()
    manuf = parse_manuf(part_manuf)
    desc = part_desc.replace('""', '"')
    return CleanRow(
        mfg_part_num=mfg_part_num.strip(),
        part_desc=expand_abbrev(desc, table),
        e1_brand=clean_brand(e1_brand),
        unilog_brand=clean_brand(unilog_brand),
        dib_brand=clean_brand(dib_brand),
        mfr_name=manuf.name or None,
        mfr_code=manuf.code,
    )
