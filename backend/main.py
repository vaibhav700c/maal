"""FastAPI service exposing the real Maal pipeline for the Vercel frontend.

Deployed on Render (repo root as service root):
    Build:  pip install -r backend/requirements.txt
    Start:  uvicorn backend.main:app --host 0.0.0.0 --port $PORT
"""
import asyncio
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.classify import classify_rows  # noqa: E402
from pipeline.cleanse import cleanse_row  # noqa: E402
from pipeline.confidence import apply_scores  # noqa: E402
from pipeline.config import Settings  # noqa: E402
from pipeline.extract import extract  # noqa: E402
from pipeline.llm import LLMClient  # noqa: E402
from pipeline.models import (  # noqa: E402
    CleanRow,
    RetrievalResult,
)
from pipeline.physics import run_physics  # noqa: E402
from pipeline.retrieve import retrieve_by_brand, retrieve_for_row  # noqa: E402
from pipeline.run_batch import build_output_row, finalize_row  # noqa: E402
from pipeline.verify_adversarial import verify  # noqa: E402

app = FastAPI(title="Maal Enrichment API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://([a-z0-9-]+\.)?vercel\.app",
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

_settings = Settings.from_env()
_llm: Optional[LLMClient] = None


def llm() -> LLMClient:
    global _llm
    if _llm is None:
        if not _settings.api_key:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured on the backend")
        _llm = LLMClient(_settings)
    return _llm


class Product(BaseModel):
    mpn: str
    description: str
    brand: Optional[str] = None
    supplier: Optional[str] = None


class BatchRequest(BaseModel):
    products: list[Product]


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "maal-enrichment"}


async def enrich_product(p: Product) -> tuple[dict, dict]:
    row = cleanse_row(
        p.mpn, p.description,
        "-- Unbranded --", "-- No Unilog Brand --", "-- No DIB Brand --",
        p.supplier or "-",
    )
    classifications = await classify_rows(llm(), [row])
    classification = classifications.get(row.mfg_part_num)

    retrieval = await retrieve_for_row(row, cache={})
    extraction = await extract(llm(), row, classification, retrieval)

    # brand-based second pass when the supplier turned out to be a distributor
    if extraction.brand and not (
        retrieval.product_url or retrieval.ref_urls or retrieval.snippets
    ):
        upgraded = await retrieve_by_brand(
            extraction.brand, row, cache={}, ddgs_fn=None
        )
        if upgraded.product_url or upgraded.ref_urls or upgraded.snippets:
            upgraded.flags.append("BRAND_DOMAIN_LOOKUP")
            retrieval = upgraded

    extraction = await verify(llm(), extraction, retrieval)

    result = finalize_row(
        row, classification, retrieval, extraction, corrections={}
    )

    physics = None
    if result.physics:
        physics = [
            {"name": c.name, "status": c.status, "reason": c.reason}
            for c in result.physics.checks
        ]

    record = {
        "mpn": result.mfg_part_num,
        "shortDesc": result.output_row.get("SHORT_DESC", ""),
        "longDesc": result.output_row.get("LONG_DESC1", ""),
        "classpath": classification.classpath if classification else "",
        "unspsc": (classification.unspsc or "") if classification else "",
        "brand": result.output_row.get("BRAND_NAME", ""),
        "manufacturer": result.output_row.get("MANUFACTURER_NAME", ""),
        "invoiceDesc": result.output_row.get("INVOICE_DESC", ""),
        "mobileDesc": result.output_row.get("MOBILE_DESC", ""),
        "retailDesc": result.output_row.get("RETAIL_DESC", ""),
        "flags": result.flags,
        "triage": result.triage_score,
        "physics": physics,
        "retrieval": {
            "mfrUrl": retrieval.mfr_url if retrieval else None,
            "productUrl": retrieval.product_url if retrieval else None,
            "refUrls": [u for u in (retrieval.ref_urls if retrieval else []) if u],
            "flags": retrieval.flags if retrieval else [],
        },
        "assets": {
            k: v
            for k, v in result.output_row.items()
            if k in ("MFR URL", "Product Image", "Alternate Image 1",
                     "Specification Sheet", "Actual Image (Yes/No)")
            or k.startswith("Ref URL")
        },
        "attributes": [
            {
                "label": a.label,
                "value": a.value,
                "uom": a.uom,
                "verdict": a.verdict,
                "confidence": a.confidence,
                "quote": a.evidence.quote if a.evidence else None,
                "url": a.evidence.url if a.evidence else None,
                "reviewReason": a.review_reason,
            }
            for a in [
                type(a)(
                    label=a.label.title(),
                    value=a.value,
                    uom=a.uom,
                    evidence=a.evidence,
                    verdict=a.verdict,
                    confidence=a.confidence,
                    review_reason=a.review_reason,
                )
                for a in extraction.attributes
            ]
        ],
    }

    echo = {
        "mpn": p.mpn,
        "description": p.description,
        "brandRaw": p.brand or "",
        "supplierRaw": p.supplier or "",
    }
    return record, echo


@app.post("/enrich/single")
async def enrich_single(p: Product) -> dict:
    try:
        record, echo = await enrich_product(p)
        return {"ok": True, "rows": [record], "echoes": [echo], "count": 1}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"enrichment failed: {exc}")


@app.post("/enrich/batch")
async def enrich_batch_file(file: bytes = File(...)) -> dict:
    """CSV upload (<=10 rows) — same columns as the sample dataset."""
    import csv as _csv
    import io

    text = file.decode("utf-8-sig", errors="replace")
    rows_in: list[Product] = []
    reader = _csv.DictReader(io.StringIO(text))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    i_mpn = next((headers.index(h) for h in headers if h in ("mfg_part_num", "mpn", "part number", "sku")), None)
    i_desc = next((headers.index(h) for h in headers if h in ("part_desc", "description", "desc")), None)
    if i_mpn is None or i_desc is None:
        raise HTTPException(status_code=422, detail="Need part-number and description columns")
    for r in reader:
        vals = list(r.values())
        mpn = vals[i_mpn].strip() if i_mpn < len(vals) else ""
        desc = vals[i_desc].strip() if i_desc < len(vals) else ""
        if mpn or desc:
            rows_in.append(Product(mpn=mpn or desc[:24], description=desc))
        if len(rows_in) >= 10:
            break
    if not rows_in:
        raise HTTPException(status_code=422, detail="No usable rows found")

    out_rows, out_echoes = [], []
    for p in rows_in:
        try:
            record, echo = await enrich_product(p)
            out_rows.append(record)
            out_echoes.append(echo)
        except Exception as exc:
            out_rows.append({
                "mpn": p.mpn, "shortDesc": "", "longDesc": "", "classpath": "",
                "unspsc": "", "brand": "", "manufacturer": "",
                "invoiceDesc": "", "mobileDesc": "", "retailDesc": "",
                "flags": ["NEEDS_REVIEW", f"PIPELINE_ERROR:{type(exc).__name__}"],
                "triage": 1.0, "physics": None, "retrieval": None, "assets": {},
                "attributes": [],
            })
            out_echoes.append({"mpn": p.mpn, "description": p.description,
                               "brandRaw": p.brand or "", "supplierRaw": p.supplier or ""})
    return {"ok": True, "rows": out_rows, "echoes": out_echoes, "count": len(out_rows)}
