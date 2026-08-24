"""Deep document mining: product page + PDF manuals -> spec attributes.

Uses PyMuPDF (fitz) as primary PDF extractor with pypdf fallback.
Fetches every discovered document, splits text into chunks, and runs
focused LLM extraction per chunk. Merged into the existing attribute
ledger with dedupe by normalized label.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from pipeline.models import Attribute, Evidence  # noqa: E402

MAX_DOCS = 4
MAX_CHUNKS_PER_DOC = 5
CHUNK_CHARS = 5000
CHUNK_OVERLAP = 300


def extract_pdf_text(url: str, timeout: int = 30) -> Optional[str]:
    """Download a PDF and extract text. PyMuPDF primary, pypdf fallback.
    Streams with a hard size cap - unbounded resp.content has OOM-killed
    the 512MB free instance when manufacturers serve huge spec sheets."""
    max_bytes = 15 * 1024 * 1024
    pdf_bytes = b""
    try:
        with httpx.Client(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    return None
                for chunk in resp.iter_bytes(64 * 1024):
                    pdf_bytes += chunk
                    if len(pdf_bytes) > max_bytes:
                        break  # truncate oversize PDFs instead of dying
        if len(pdf_bytes) < 1000:
            return None
    except Exception:
        return None

    # Primary: PyMuPDF (fastest, best text quality)
    try:
        import pymupdf

        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page in doc.pages(0, min(doc.page_count, 40)):
            pages.append(page.get_text("text") or "")
        doc.close()
        result = "\n".join(pages).strip()
        if len(result) > 300:
            return result[:400_000]  # cap extracted text for the LLM stage
    except Exception:
        pass

    # Fallback: pypdf
    try:
        from pypdf import PdfReader
        import io as _io

        reader = PdfReader(_io.BytesIO(pdf_bytes))
        pages = []
        for page in reader.pages[:40]:
            pages.append(page.extract_text() or "")
        result = "\n".join(pages).strip()
        return result if len(result) > 300 else None
    except Exception:
        return None


def chunk_text(text: str) -> list[str]:
    if len(text) <= CHUNK_CHARS:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_CHARS
        # snap to word boundary
        if end < len(text):
            space = text.rfind(" ", end - 200, end)
            if space > start:
                end = space
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP
    return chunks


MINE_SYSTEM = (
    "You are mining an appliance/product specification document for catalog "
    "attributes. Extract ONLY facts literally present in the text. For each "
    "attribute include a short verbatim quote from THIS chunk proving it. "
    "Use these exact labels when present: Model Number, Series, Voltage "
    "Rating, Amperage Rating, Number of Wash Cycles, Mounting Type, Size, "
    "Depth With Door Open, Minimum Height, Maximum Height, Sound Level, "
    "Material, Color, Capacity, Width, Height, Depth, Weight, Wattage, "
    "Finish, Handle Type, Rack Type, Filter Type, Control Type. Also list "
    "features (distinct selling points like '3rd rack', 'Sani Rinse', "
    "'Leak Detection System') and certifications (UL Listed, ENERGY STAR, "
    "NSF Certified, cUL Listed)."
)

MINE_PROMPT = """Document chunk for model {mpn}:

---
{chunk}
---

Output STRICT JSON:
{{"attributes": [{{"label":"...","value":"...","uom":"... or null","quote":"verbatim text from this chunk"}}],
 "features": ["selling point phrase", ...],
 "certifications": ["UL Listed", ...]}}"""


async def mine_documents(
    llm,
    mpn: str,
    doc_urls: list[str],
    product_url: str | None,
    http: Optional[httpx.AsyncClient] = None,
) -> tuple[list[Attribute], list[str], list[str]]:
    """Returns (new_attributes, features, certifications) mined from docs."""
    import json as _json

    attrs_out: dict[str, Attribute] = {}
    features: list[str] = []
    certs: list[str] = []

    targets: list[tuple[str, bool]] = []  # (url, is_pdf)

    # product page first (HTML — fetch via Jina Reader)
    if product_url and not product_url.lower().endswith(".pdf"):
        targets.append((product_url, False))

    # then PDFs / manuals
    for u in doc_urls[:MAX_DOCS]:
        is_pdf = u.lower().split("?")[0].endswith(".pdf")
        targets.append((u, is_pdf))

    own_client = http is None
    client = http or httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0"}, timeout=25
    )

    texts: list[tuple[str, str]] = []  # (text, source_url)

    async def fetch_html(url: str) -> Optional[str]:
        """Fetch HTML via Jina Reader (handles bot-blocks), fallback direct."""
        try:
            resp = await client.get(f"https://r.jina.ai/{url}")
            if resp.status_code == 200 and len(resp.text) > 200:
                body = resp.text
                # strip markdown link syntax but keep content readable
                import re as _re
                body = _re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", body)
                return body if len(body) > 200 else None
        except httpx.HTTPError:
            pass
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                import re as _re
                html = resp.text
                html = _re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html, flags=_re.I)
                html = _re.sub(r"<[^>]+>", " ", html)
                return _re.sub(r"\s+", " ", html) if len(html) > 300 else None
        except httpx.HTTPError:
            pass
        return None

    try:
        for url, is_pdf in targets[: MAX_DOCS + 1]:
            if is_pdf:
                # PDF extraction runs in a thread to not block the event loop
                text = await asyncio.to_thread(extract_pdf_text, url)
                source_tag = f"{url} (PDF manual)"
            else:
                text = await fetch_html(url)
                source_tag = url
            if text and len(text) > 300:
                texts.append((text, source_tag))

        merged = "\n\n---PAGE BREAK---\n\n".join(t for t, _ in texts)
        chunks = chunk_text(merged)[:MAX_CHUNKS_PER_DOC]

        for ci, chunk in enumerate(chunks):
            prompt = MINE_PROMPT.replace("{mpn}", mpn).replace("{chunk}", chunk)
            try:
                data = await llm.generate_json(prompt, MINE_SYSTEM)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue

            for item in data.get("attributes") or []:
                label = str(item.get("label") or "").strip()
                value = str(item.get("value") or "").strip()
                if not label or not value:
                    continue
                key = label.lower()
                if key in attrs_out:
                    # prefer longer values
                    if len(value) > len(attrs_out[key].value):
                        attrs_out[key] = Attribute(
                            label=label.title(),
                            value=value,
                            uom=str(item["uom"]).strip() if item.get("uom") else None,
                            evidence=None,
                            verdict="CONFIRMED",
                            confidence=0.75,
                        )
                else:
                    src_url = targets[min(ci, len(targets)-1)][0] if ci < len(targets) else None
                    attrs_out[key] = Attribute(
                        label=label.title(),
                        value=value,
                        uom=str(item["uom"]).strip() if item.get("uom") else None,
                        evidence=type("E", (), {"quote": "", "url": src_url, "tier": 0.9})(),
                        verdict="CONFIRMED",
                        confidence=0.75,
                    )

            for f in data.get("features") or []:
                fs = str(f).strip()
                if fs and fs.lower() not in {x.lower() for x in features} and len(features) < 15:
                    features.append(fs)

            for cert in data.get("certifications") or []:
                cs = str(cert).strip()
                if cs and cs.lower() not in {x.lower() for x in certs} and len(certs) < 10:
                    certs.append(cs)

    finally:
        if own_client:
            await client.aclose()

    return list(attrs_out.values()), features, certs
