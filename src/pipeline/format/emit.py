"""Writers for the 252-column Delivery Format plus provenance sidecar."""
import csv
import json
from pathlib import Path

import pandas as pd

from pipeline.models import RowResult

PASSTHROUGH = {
    "Mfg_Part_Num": "mfg_part_num",
    "Part_Desc": "part_desc",
    "E1_Brand": "e1_brand",
    "Unilog_Brand": "unilog_brand",
    "DIB_Brand": "dib_brand",
    "Part_Manuf": "mfr_display",
}

CORE_FIELDS = [
    "MANUFACTURER_NAME",
    "BRAND_NAME",
    "TRADE_NAME",
    "MANUFACTURER_PART_NUMBER",
    "Classpath",
    "MOBILE_DESC",
    "INVOICE_DESC",
    "SHORT_DESC",
    "LONG_DESC1",
    "RETAIL_DESC",
    "MARKETING_DESCRIPTION",
    "ITEM_FEATURES_1",
    "ITEM_FEATURES_2",
    "ITEM_FEATURES_3",
    "With",
    "Standard/Approvals",
    "Application",
    "Includes",
    "Product Name",
    "UNSPSC",
]


def load_headers(path: str | Path) -> list[str]:
    # utf-8-sig strips any BOM on read; we deliberately WRITE plain utf-8
    # below because the ground-truth Delivery Format file carries no BOM.
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return next(csv.reader(handle))


def passthrough_fields(row: RowResult) -> dict[str, str]:
    clean = row.clean
    mfr_bits = [b for b in [clean.mfr_name, f"({clean.mfr_code})" if clean.mfr_code else None] if b]
    values = {
        "mfg_part_num": clean.mfg_part_num,
        "part_desc": clean.part_desc,
        "e1_brand": clean.e1_brand or "",
        "unilog_brand": clean.unilog_brand or "",
        "dib_brand": clean.dib_brand or "",
        "mfr_display": " ".join(mfr_bits),
    }
    out = {}
    for column, key in PASSTHROUGH.items():
        value = values[key]
        if value:
            out[column] = value
    return out


def _sidecar_record(row: RowResult) -> dict:
    fields: dict[str, dict] = {}
    extraction = row.extraction
    if extraction:
        for attr in extraction.attributes:
            fields[attr.label] = {
                "value": attr.value,
                "uom": attr.uom,
                "source_url": attr.evidence.url if attr.evidence else None,
                "quote": attr.evidence.quote if attr.evidence else None,
                "tier": attr.evidence.tier if attr.evidence else None,
                "verdict": attr.verdict,
                "confidence": attr.confidence,
                "review_reason": attr.review_reason,
            }
    physics = row.physics
    return {
        "mfg_part_num": row.mfg_part_num,
        "fields": fields,
        "physics": physics.model_dump() if physics else None,
        "flags": row.flags,
        "triage_score": row.triage_score,
        "retrieval": row.retrieval.model_dump() if row.retrieval else None,
        "classification": (
            row.classification.model_dump() if row.classification else None
        ),
    }


def write_outputs(
    rows: list[RowResult], outdir: str | Path
) -> tuple[Path, Path, Path]:
    """Write result.csv, result.xlsx and sidecar.jsonl; returns their paths."""
    from pipeline.config import ROOT

    headers_path = ROOT / "input" / "Unihack_ Expected Output - Delivery Format.csv"
    headers = load_headers(headers_path)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    matrix = []
    for row in rows:
        merged = {h: "" for h in headers}
        merged.update(passthrough_fields(row))
        for key, value in row.output_row.items():
            if key in merged:
                merged[key] = value
        matrix.append(merged)

    csv_path = outdir / "result.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="raise")
        writer.writeheader()
        writer.writerows(matrix)

    frame = pd.DataFrame(matrix, columns=headers)
    xlsx_path = outdir / "result.xlsx"
    frame.to_excel(xlsx_path, index=False)

    sidecar_path = outdir / "sidecar.jsonl"
    with open(sidecar_path, "w") as handle:
        for record in (_sidecar_record(row) for row in rows):
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    return csv_path, xlsx_path, sidecar_path
