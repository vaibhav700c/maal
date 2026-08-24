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
    Attribute,
    CleanRow,
    RetrievalResult,
)
from pipeline.physics import run_physics  # noqa: E402
from pipeline.retrieve import retrieve_by_brand, retrieve_for_row  # noqa: E402
from pipeline.run_batch import build_output_row, finalize_row  # noqa: E402
from pipeline.verify_adversarial import verify  # noqa: E402

def _norm(s):
    return (s or "").replace("®", "").replace("™", "").strip().lower()


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

from pipeline.retrieve import load_cache as _load_retrieval_cache  # noqa: E402

RETRIEVAL_CACHE: dict = _load_retrieval_cache()


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
    e1_brand: Optional[str] = None
    unilog_brand: Optional[str] = None


_PLACEHOLDERS = {"-- unbranded --", "-- no unilog brand --", "-- no dib brand --", "-"}


def _clean_hint(value: str | None) -> Optional[str]:
    v = (value or "").strip()
    return None if not v or v.lower() in _PLACEHOLDERS else v


def parse_upload(text: str, cap: int = 3) -> list[Product]:
    """Parse an uploaded CSV/TSV into Products, keeping brand hints."""
    import csv as _csv
    import io

    reader = _csv.DictReader(io.StringIO(text))
    headers = [(h or "").strip().lower() for h in (reader.fieldnames or [])]

    def col(*names: str) -> Optional[int]:
        for n in names:
            if n in headers:
                return headers.index(n)
        return next((headers.index(h) for h in headers if any(x in h for x in names)), None)

    i_mpn = col("mfg_part_num", "mpn", "part number", "sku")
    i_desc = col("part_desc", "description", "desc")
    i_sup = col("part_manuf", "manufacturer", "supplier", "vendor")
    i_e1 = col("e1_brand")
    i_unilog = col("unilog_brand")
    i_dib = col("dib_brand")
    if i_mpn is None or i_desc is None:
        raise HTTPException(status_code=422, detail="Need part-number and description columns")

    products: list[Product] = []
    for r in reader:
        vals = list(r.values())
        def cell(idx: Optional[int]) -> str:
            return vals[idx].strip() if idx is not None and idx < len(vals) else ""
        mpn = cell(i_mpn)
        desc = cell(i_desc)
        if mpn or desc:
            products.append(Product(
                mpn=mpn or desc[:24],
                description=desc,
                supplier=_clean_hint(cell(i_sup)),
                brand=_clean_hint(cell(i_dib)),
                e1_brand=_clean_hint(cell(i_e1)),
                unilog_brand=_clean_hint(cell(i_unilog)),
            ))
        if len(products) >= cap:
            break
    return products


class BatchRequest(BaseModel):
    products: list[Product]


@app.get("/health")
async def health() -> dict:
    import os

    return {
        "status": "ok",
        "service": "maal-enrichment",
        "gemini_key_present": bool(os.environ.get("GEMINI_API_KEY")),
        "env_keys_sample": sorted(list(os.environ.keys()))[:8],
    }


async def enrich_product(p: Product) -> tuple[dict, dict]:
    row = cleanse_row(
        p.mpn, p.description,
        p.e1_brand or "-- Unbranded --",
        p.unilog_brand or "-- No Unilog Brand --",
        p.brand or "-- No DIB Brand --",
        p.supplier or "-",
    )
    # ── Gemini-first: knowledge enrichment BEFORE retrieval ──
    classification = None

    try:
        knowledge_data = await _knowledge_enrich(llm(), p.mpn, row)
    except Exception:
        knowledge_data = None

    if knowledge_data and isinstance(knowledge_data, dict):
        _merge_knowledge(extraction := type("E", (), {"attributes": [], "features": [], "certifications": [], "item_type": "", "series": None, "brand": None, "manufacturer": None, "classpath": None, "unspsc": None, "official_domain": None, "application": None, "includes": None, "additional": None})(), knowledge_data)

        from pipeline.models import Classification
        cp = knowledge_data.get("classpath")
        if cp and isinstance(cp, str):
            parts = [p.strip() for p in cp.split(">")]
            classification = Classification(
                dept=parts[0] if parts else "",
                klass=parts[1] if len(parts) > 1 else "",
                fine=parts[-1] if parts else "",
                classpath=cp.replace(" > ", ">"),
                unspsc=str(knowledge_data["unspsc"]) if knowledge_data.get("unspsc") else None,
            )
        corp = knowledge_data.get("manufacturer_corporate")
        if corp:
            extraction.manufacturer = corp

    retrieval = await retrieve_for_row(row, cache=RETRIEVAL_CACHE)
    extraction = await extract(llm(), row, None, retrieval)

    # brand-based second pass when the supplier turned out to be a distributor
    domain_hint = getattr(extraction, "official_domain", None)
    if (extraction.brand or domain_hint) and not (
        retrieval.product_url or retrieval.ref_urls or retrieval.snippets
    ):
        upgraded = await retrieve_by_brand(
            domain_hint or extraction.brand, row, cache=RETRIEVAL_CACHE, ddgs_fn=None
        )
        if upgraded.product_url or upgraded.ref_urls or upgraded.snippets:
            upgraded.flags.append("BRAND_DOMAIN_LOOKUP")
            retrieval = upgraded
    try:
        from pipeline.retrieve import save_cache
        save_cache(RETRIEVAL_CACHE)
    except Exception:
        pass

    # knowledge-tier enrichment merged from the SAME Gemini-first pass —
    # a second grounded call here doubled latency for zero new information
    knowledge_urls: list[str] = []
    if knowledge_data:
        _merge_knowledge(extraction, knowledge_data)
        knowledge_urls = [u for u in (knowledge_data.get("source_urls") or []) if u]
        corp = knowledge_data.get("manufacturer_corporate")
        if corp and extraction.manufacturer in (None, "", row.mfr_name):
            extraction.manufacturer = corp

    # deep document mining: product page + PDF manuals -> spec attributes
    from backend.deep_mine import mine_documents

    try:
        mined_attrs, mined_features, mined_certs = await mine_documents(
            llm(),
            p.mpn,
            retrieval.ref_urls if retrieval else [],
            retrieval.product_url if retrieval else None,
        )
        existing = {a.label.lower() for a in extraction.attributes}
        for attr in mined_attrs:
            if attr.label.lower() not in existing:
                extraction.attributes.append(attr)
                existing.add(attr.label.lower())
        for f in mined_features:
            if f not in extraction.features:
                extraction.features.append(f)
        for c in mined_certs:
            if c not in extraction.certifications:
                extraction.certifications.append(c)
    except Exception:
        pass  # mining is opportunistic; never fails the request

    extraction = await verify(llm(), extraction, retrieval)

    # canonical manufacturer resolution (same as batch pipeline)
    try:
        from pipeline.run_batch import resolve_manufacturers

        mfr_map = await resolve_manufacturers(
            llm(),
            [{
                "mpn": p.mpn,
                "brand": extraction.brand if extraction else p.brand,
                "supplier": row.mfr_name,
                "desc": row.part_desc,
            }],
        )
        canon = mfr_map.get(p.mpn)
        if canon and extraction:
            current = extraction.manufacturer or ""
            from pipeline.run_batch import _norm_key
            echoes = bool(current) and _norm_key(current) in _norm_key(row.mfr_name or "")
            if not current or echoes:
                extraction.manufacturer = canon
    except Exception:
        pass  # resolution is opportunistic

    result = finalize_row(
        row, classification, retrieval, extraction, corrections={}
    )

    # knowledge-tier source URLs (collected pre-finalize; `result` exists now)
    if knowledge_urls:
        for i, u in enumerate(knowledge_urls[:5], 1):
            result.output_row.setdefault(f"Ref URL {i}", u)
        if len(result.output_row.get("MFR URL", "")) < 12:
            result.output_row["MFR URL"] = knowledge_urls[0]

    physics = None
    if result.physics:
        physics = [
            {"name": c.name, "status": c.status, "reason": c.reason}
            for c in result.physics.checks
        ]

    # Inject LLM-knowledge URLs when retrieval didn't find them
    if extraction and getattr(extraction, "official_domain", None):
        existing_mfr = result.output_row.get("MFR URL", "")
        if not existing_mfr or existing_mfr.rstrip("/") in ("https:/", "https://"):
            domain = extraction.official_domain
            if domain.startswith("http"):
                result.output_row["MFR URL"] = domain
            elif "." in domain:
                result.output_row["MFR URL"] = f"https://{domain}"

    if extraction and getattr(extraction, "knowledge_ref_urls", None):
        for i, u in enumerate(extraction.knowledge_ref_urls[:5], 1):
            key = f"Ref URL {i}"
            if not result.output_row.get(key):
                result.output_row[key] = u

    # Unilog internal Dept/Class/Fine taxonomy + corporate parent resolution
    from pipeline.taxonomy import apply_unilog_taxonomy, corporate_parent, order_attributes

    taxo = apply_unilog_taxonomy(
        classification.classpath if classification else None,
        extraction.item_type if extraction else None,
    )
    if taxo["dept"]:
        result.output_row["Dept"] = taxo["dept"]
        result.output_row["Class"] = taxo["klass"]
        result.output_row["Fine"] = taxo["fine"]

    # resolve corporate manufacturer from brand lookup table
    brand_name = result.output_row.get("BRAND_NAME", "")
    brand_norm = _norm(brand_name)
    corp = corporate_parent(brand_name.replace("®", "").replace("™", "").strip())
    if corp:
        result.output_row["MANUFACTURER_NAME"] = corp
        if brand_norm == _norm(corp):
            result.output_row["TRADE_NAME"] = ""
        else:
            result.output_row["TRADE_NAME"] = brand_name

    # order attributes to match GT sequence for this product family
    extraction.attributes = order_attributes(
        extraction.attributes, extraction.item_type if extraction else ""
    )

    features_list = extraction.features[:15] if extraction else []
    certs_str = "|".join(extraction.certifications) if extraction else ""

    record = {
        "mpn": result.mfg_part_num,
        "shortDesc": result.output_row.get("SHORT_DESC", ""),
        "longDesc": result.output_row.get("LONG_DESC1", ""),
        "classpath": classification.classpath if classification else "",
        "unspsc": (classification.unspsc or "") if classification else "",
        "brand": result.output_row.get("BRAND_NAME", ""),
        "manufacturer": result.output_row.get("MANUFACTURER_NAME", ""),
        "tradeName": result.output_row.get("TRADE_NAME", ""),
        "invoiceDesc": result.output_row.get("INVOICE_DESC", ""),
        "mobileDesc": result.output_row.get("MOBILE_DESC", ""),
        "retailDesc": result.output_row.get("RETAIL_DESC", ""),
        "marketingDesc": result.output_row.get("MARKETING_DESCRIPTION", ""),
        "featuresList": features_list,
        "certificationsStr": certs_str,
        "application": (extraction.application or "") if extraction else "",
        "includes": (extraction.includes or "") if extraction else "",
        "dept": taxo["dept"],
        "class": taxo["klass"],
        "fine": taxo["fine"],
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
            k: v for k, v in result.output_row.items()
            if k in ("MFR URL", "Product Image", "Alternate Image 1",
                     "Alternate Image 2", "Alternate Image 3",
                     "Alternate Image 4", "Specification Sheet",
                     "Actual Image (Yes/No)")
            or k.startswith("Ref URL")
        },
        "outputRow": {k: v for k, v in result.output_row.items() if v},
        "attributes": [
            {
                "label": a.label.title(),
                "value": a.value,
                "uom": a.uom,
                "verdict": a.verdict,
                "confidence": a.confidence,
                "quote": a.evidence.quote if a.evidence else None,
                "url": a.evidence.url if a.evidence else None,
                "reviewReason": a.review_reason,
            }
            for a in extraction.attributes
        ] if extraction else [],
    }

    echo = {
        "mpn": p.mpn,
        "description": p.description,
        "brandRaw": p.brand or "",
        "supplierRaw": p.supplier or "",
    }
    return record, echo


async def _knowledge_enrich(llm, mpn: str, clean) -> dict | None:
    """Ask the LLM for known specs about this specific model."""
    import re as _re

    brand = ""
    desc_words = clean.part_desc.split()
    # try to find a brand token in the description
    for w in desc_words[:6]:
        if len(w) >= 3 and not any(c.isdigit() for c in w):
            brand_candidate = w.strip(",.-")
            if brand_candidate.lower() not in ("dishwasher", "display", "only", "the"):
                brand = brand_candidate
                break

    # Detect product category for targeted prompting
    desc_low = clean.part_desc.lower()
    category_hints = []
    if any(w in desc_low for w in ("dishwasher",)):
        category_hints.append("Dishwasher")
    if any(w in desc_low for w in ("refrigerator", "fridge")):
        category_hints.append("Refrigerator")
    if any(w in desc_low for w in ("washer",)) and "dish" not in desc_low:
        category_hints.append("Clothes Washer")
    if any(w in desc_low for w in ("dryer",)):
        category_hints.append("Clothes Dryer")
    if any(w in desc_low for w in ("cut off", "cut-off", "grinding")):
        category_hints.append("Abrasive Cut-Off Wheel")

    cat_context = f" This appears to be a {' / '.join(category_hints)}." if category_hints else ""

    prompt = f"""You know industrial and consumer product catalogs. For the product:
Model: {mpn}
Description: {clean.part_desc}
Supplier (may be a distributor, not the maker): {clean.mfr_name or 'unknown'}
Brand hint: {brand}
Category: {cat_context}

From your training data, provide the published specifications for this product.
For appliances, include: Series name, Voltage Rating, Amperage Rating,
Number of Wash Cycles (if applicable), Mounting Type, Size dimensions,
Sound Level, Material, Color, Capacity.
For tools and accessories, include: Diameter, Thickness, Arbor size, Material, Max RPM, Application.

Output STRICT JSON with these EXACT attribute labels when applicable:
{{"brand": "brand name",
 "manufacturer_corporate": "corporate parent (e.g. 'Whirlpool Corporation', 'Rheem Manufacturing') or null",
 "series": "product series/line name",
 "classpath": "full-depth distributor taxonomy path (>= 3 levels)",
 "unspsc": "6-digit UNSPSC code",
  "official_domain": "brand's official website domain",
  "product_url": "exact URL on the manufacturer's site for this specific product, or null",
  "reference_urls": ["URL to owners manual or spec PDF on manufacturer site", ...] or null,
  "item_type": "short product type noun",
 "attributes": [
   {{"label": "Series", "value": "...", "uom": null}},
   {{"label": "Voltage Rating", "value": "120", "uom": "V"}},
   {{"label": "Amperage Rating", "value": "10", "uom": "A"}},
   {{"label": "Number of Wash Cycles", "value": "5", "uom": null}},
   {{"label": "Mounting Type", "value": "Built-in", "uom": null}},
   {{"label": "Size", "value": "33-7/16 in H x 23-7/8 in W x 22-5/8 in D", "uom": null}},
   {{"label": "Depth With Door Open", "value": "50-3/16", "uom": "in"}},
   {{"label": "Sound Level", "value": "47", "uom": "dBA"}},
   {{"label": "Material", "value": "Stainless Steel", "uom": null}},
   {{"label": "Color", "value": "Stainless Steel", "uom": null}}
 ],
 "features": ["3rd rack with extra wash action", "Adjustable 2nd Rack", ...],
 "certifications": ["ENERGY STAR Certified", "cUL Listed"],
 "warranty": "1 Year Manufacturer, 1 Year Labor and Parts" or null,
 "additional_information": "Folding Tines, Leak Detection System..." or null,
 "marketing_description": "one-sentence marketing blurb" or null
}}

ONLY include facts you genuinely know. Omit attributes you're unsure about."""

    system = (
        "You are a product catalog specialist with deep knowledge of appliance, "
        "tool, and building product specifications. Provide detailed, accurate "
        "specifications using your training data. Always use the exact label "
        "names shown in the schema. Include ALL attributes you can, even "
        "estimates based on similar models from the same brand and series."
    )

    # Use Google Search grounding for real URLs and verified data
    source_urls: list[str] = []
    backend_obj = getattr(llm, "backend", None)
    if backend_obj and hasattr(backend_obj, "complete_grounded"):
        try:
            text, source_urls = await backend_obj.complete_grounded(prompt, system)
        except Exception:
            text = await llm.generate(prompt, system)
    else:
        text = await llm.generate(prompt, system)

    import json as _json

    fence = _re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    raw = fence.group(1) if fence else text
    try:
        result = _json.loads(raw)
    except _json.JSONDecodeError:
        cleaned = _re.sub(r",\s*([}\]])", r"\1", raw)
        try:
            result = _json.loads(cleaned)
        except _json.JSONDecodeError:
            return None

    result["source_urls"] = source_urls[:10]
    return result


def _merge_knowledge(extraction, data: dict) -> None:
    """Merge knowledge-inferred attributes into the extraction ledger.
    All values marked tier=0.5 (knowledge-inferred) so provenance is clear."""
    existing_labels = {a.label.lower() for a in extraction.attributes}

    for item in data.get("attributes") or []:
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        if not label or not value or label.lower() in existing_labels:
            continue
        confident = bool(item.get("confident", False))
        extraction.attributes.append(
            Attribute(
                label=label.title(),
                value=value,
                uom=item.get("uom"),
                evidence=None,
                verdict="UNVERIFIED",
                confidence=0.55 if confident else 0.40,
                review_reason="knowledge-inferred from model-code analysis"
                if not confident
                else "known specification for this product family",
            )
        )
        existing_labels.add(label.lower())

    # series
    series = data.get("series")
    if series and not extraction.series:
        extraction.series = str(series)

    # features merge
    for f in data.get("features") or []:
        fs = str(f).strip()
        if fs and fs.lower() not in {x.lower() for x in extraction.features}:
            extraction.features.append(fs)

    # certifications merge
    for cert in data.get("certifications") or []:
        cs = str(cert).strip()
        if cs and cs.lower() not in {x.lower() for x in extraction.certifications}:
            extraction.certifications.append(cs)

    # product URL and reference docs from LLM knowledge
    product_url = data.get("product_url")
    if product_url and str(product_url).startswith("http"):
        extraction.official_domain = str(product_url)
    ref_urls = data.get("reference_urls")
    if ref_urls and isinstance(ref_urls, list):
        extraction.knowledge_ref_urls = [str(u) for u in ref_urls if str(u).startswith("http")]

    # additional info
    additional = data.get("additional_information")
    if additional and not extraction.additional:
        extraction.additional = str(additional)

    # marketing description
    marketing = data.get("marketing_description")
    if marketing:
        extraction.features.append(str(marketing))


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
    text = file.decode("utf-8-sig", errors="replace")
    rows_in = parse_upload(text, cap=3)
    if not rows_in:
        raise HTTPException(status_code=422, detail="No usable rows found")

    async def _safe_enrich(p: Product):
        try:
            return await enrich_product(p)
        except Exception as exc:
            record = {
                "mpn": p.mpn, "shortDesc": "", "longDesc": "", "classpath": "",
                "unspsc": "", "brand": "", "manufacturer": "",
                "invoiceDesc": "", "mobileDesc": "", "retailDesc": "",
                "flags": ["NEEDS_REVIEW", f"PIPELINE_ERROR:{type(exc).__name__}"],
                "triage": 1.0, "physics": None, "retrieval": None, "assets": {},
                "attributes": [],
            }
            echo = {"mpn": p.mpn, "description": p.description,
                    "brandRaw": p.brand or "", "supplierRaw": p.supplier or ""}
            return record, echo

    # concurrent — sequential loops blow past caller timeouts (Vercel 60s cap)
    out_rows, out_echoes = [], []
    for record, echo in await asyncio.gather(*(_safe_enrich(p) for p in rows_in)):
        out_rows.append(record)
        out_echoes.append(echo)
    return {"ok": True, "rows": out_rows, "echoes": out_echoes, "count": len(out_rows)}
