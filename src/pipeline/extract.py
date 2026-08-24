"""Structured attribute extraction with mandatory evidence quotes."""
import re

from pipeline.llm import LLMError
from pipeline.models import (
    Attribute,
    Classification,
    CleanRow,
    Evidence,
    Extraction,
    RetrievalResult,
)

SYSTEM = (
    "You are a precise industrial catalog data extractor. Attribute values "
    "come ONLY from the raw description and supplied source snippets — never "
    "invent measurements. ONE exception: the brand may be inferred from the "
    "product's model/part number using your knowledge of manufacturer coding "
    "schemes (e.g. PDSH4816AF -> Frigidaire, WDTS7024RZ -> Whirlpool, "
    "49-94-0063 -> Milwaukee); only infer when confident. Every other "
    "attribute MUST carry a short verbatim 'quote' copied exactly from the "
    "description or one of the snippets; omit facts not present. Output "
    "STRICT JSON only."
)

PROMPT_TEMPLATE = """Extract structured product data.

RAW DESCRIPTION: {desc}
MANUFACTURER: {mfr}
CLASSPATH: {classpath}

SOURCE SNIPPETS (manufacturer-owned pages):
{snippets}

You are enriching for a distributor catalog. For appliances and spec-heavy
products, mine the snippets deeply and populate these labels EXACTLY when the
source states them: Series, Model Number, Voltage Rating, Amperage Rating,
Number of Wash Cycles, Mounting Type, Size (full H x W x D string), Depth With
Door Open, Minimum Height, Maximum Height, Sound Level, Material, Color,
Capacity. Also fill features with every distinct selling-point phrase on the
page (rack systems, cycles, dispensers), certifications with every listed
approval (UL, NSF, ENERGY STAR...), and application/includes when stated.

Output STRICT JSON:
{{"classpath": "FULL-DEPTH distributor taxonomy path with >=3 levels, e.g. 'Appliances & Consumer Electronics > Kitchen Appliances > Built-In Dishwashers' for a dishwasher, 'Hardware > Power Tool Accessories > Abrasive Cut-Off Wheels' for a cut-off disc — never a 2-level shortcut",
  "unspsc": "6-digit UNSPSC code or null",
  "official_domain": "brand's official website domain like example.com, or null",
  "item_type": "short product type noun",
  "series": "series name or null",
  "brand": "brand printed on the product OR confidently inferred from the model number (e.g. '3M', 'Diablo', 'Leviton', 'Frigidaire') or null — NOT the distributor",
  "brand_inferred": true if brand came from model-number knowledge rather than text, else false,
  "manufacturer": "actual product manufacturer you are confident about, else null",
  "attributes": [{{"label": "...", "value": "...", "uom": "approved abbrev or null", "quote": "verbatim source text"}}],
  "features": ["short feature phrase", ...],
  "certifications": ["UL Listed", ...],
  "application": "or null",
  "includes": "or null",
  "warranty": "warranty statement with its verbatim quote, or null",
  "country_of_origin": "e.g. 'USA', 'Germany' — only if a source states it, else null",
  "upc": "12-digit UPC barcode ONLY if printed in a source, else null",
  "ean": "13-digit EAN barcode ONLY if printed in a source, else null",
  "gtin": "14-digit GTIN ONLY if printed in a source, else null",
  "package_quantity": "count per package as plain number (e.g. 10 for '10pc', 50 for '50 Disc/Box') with quote, or null",
  "additional": "misc specs sentence or null"}}

Pre-extracted from the description (confirm, correct, or extend — do not drop unless wrong):
{pre}"""

_DIM_RE = re.compile(r"(\d*\.?\d+(?:-\d+/\d+|/\d+)?)\"")
_VOLT_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s?V\b")
_AMP_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s?A\b")
_WATT_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s?W\b")
_GRIT_RE = re.compile(r"\bP(\d{2,4})\b")
_DISC_HINT = re.compile(r"disc|blade|wheel|cutter|saw|grinder|cut.?off")


def _strip_mpn(desc: str) -> str:
    """Remove the leading part-number token so MPNs like '37418A' or
    '49-94-0063' never masquerade as electrical specs."""
    parts = desc.split(" ", 1)
    if len(parts) == 2 and len(parts[0]) >= 4 and any(ch.isdigit() for ch in parts[0]):
        return parts[1]
    return desc


def pre_extract_attributes(desc: str) -> list[Attribute]:
    attrs: list[Attribute] = []
    desc = _strip_mpn(desc)

    def add(label: str, value: str, uom: str | None):
        attrs.append(
            Attribute(
                label=label,
                value=value,
                uom=uom,
                evidence=Evidence(quote=desc[:200], url=None, tier=0.0),
            )
        )

    desc = re.sub(r"(\d+(?:\.\d+)?(?:-\d+/\d+)?)\s*(?:ft|')(?=\s|$)", r"\1 ft ", desc)
    dims = _DIM_RE.findall(desc)
    if len(dims) >= 3:
        add("Diameter", dims[0], "in")
        add("Thickness", dims[1], "in")
        add("Arbor", dims[2], "in")
    elif len(dims) == 2:
        add("Diameter", dims[0], "in")
        add("Arbor", dims[1], "in")
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s+ft\b", desc):
        add("Length", m.group(1), "ft")
    # bare NxM forms without inch quotes: "DBDS14125A01F Diablo 14x1 - Wheel"
    if not dims and _DISC_HINT.search(desc.lower()):
        pair = re.findall(
            r"(\d+(?:\.\d+)?(?:-\d+/\d+)?)\s?[xX]\s?(\d+(?:\.\d+)?(?:-\d+/\d+)?)",
            desc,
        )
        if pair:
            add("Diameter", pair[0][0], "in")
            add("Arbor", pair[0][1], "in")
    if m := _VOLT_RE.search(desc):
        add("Voltage Rating", m.group(1), "V")
    if m := _AMP_RE.search(desc):
        add("Amperage Rating", m.group(1), "A")
    if m := _WATT_RE.search(desc):
        add("Wattage", m.group(1), "W")
    if m := _GRIT_RE.search(desc):
        add("Grit", m.group(1), None)
    return attrs


def _snippets_block(retrieval: RetrievalResult | None) -> str:
    if not retrieval or not retrieval.snippets:
        return "(none retrieved)"
    lines = []
    for i, snip in enumerate(retrieval.snippets[:4]):  # spec pages need room
        url = snip.url or "unknown"
        lines.append(f"[S{i}] {url}\n{snip.quote}")
    return "\n\n".join(lines)


def _match_evidence(quote: str | None, retrieval: RetrievalResult | None) -> Evidence | None:
    if not quote:
        return None
    q = quote.strip().lower()
    if retrieval:
        for snip in retrieval.snippets:
            window = snip.quote.lower()
            probe = q[:120]
            if probe and (probe in window or window[:120] in q or probe in window[: len(probe) + 50]):
                return snip.model_copy()
    return None


def _pre_block(desc: str) -> str:
    pres = pre_extract_attributes(desc)
    return (
        "\n".join(
            f'- {a.label}: {a.value}{" " + a.uom if a.uom else ""}' for a in pres
        )
        or "(none)"
    )


def _row_section(index: int, row: CleanRow, classification, retrieval) -> str:
    return (
        f"=== ROW {index} ===\n"
        f"RAW DESCRIPTION: {row.part_desc}\n"
        f"MANUFACTURER: {row.mfr_name or 'unknown'}\n"
        f"CLASSPATH: {classification.classpath if classification else 'unclassified'}\n"
        f"SOURCE SNIPPETS:\n{_snippets_block(retrieval)}\n"
        f"PRE-EXTRACTED (confirm, correct, or extend):\n{_pre_block(row.part_desc)}"
    )


MULTI_PROMPT_HEADER = """Extract structured product data for EACH numbered row INDEPENDENTLY. Do not mix facts between rows. Every attribute MUST carry a verbatim 'quote' from that row's description or its own snippets; omit facts not present. Every output object MUST set "index" to the ROW number exactly as shown (0-based).

""" + PROMPT_TEMPLATE.split("Extract structured product data.\n", 1)[1]


async def infer_brand(llm, row: CleanRow, extraction: Extraction) -> None:
    """Focused retry: flash-tier models intermittently skip brand inference."""
    if extraction.brand:
        return
    try:
        ans = await llm.generate(
            f"Which retail brand makes the product with model number "
            f"{row.mfg_part_num} and description '{row.part_desc[:120]}'? "
            f"Reply with ONLY the brand name (e.g. DeWalt, Diablo, Milwaukee), "
            f"or NONE if genuinely unknown."
        )
        candidate = ans.strip().strip('"').split("\n")[0]
        if candidate and candidate.upper() != "NONE" and 1 < len(candidate) < 30:
            extraction.brand = candidate
            extraction.manufacturer = extraction.manufacturer or (
                row.mfr_name or None
            )
    except Exception:  # noqa: BLE001 - opportunistic
        pass


def _parse_extraction(
    data: dict,
    row: CleanRow,
    retrieval: RetrievalResult | None,
) -> Extraction:
    extraction = Extraction(
        item_type=str(data.get("item_type") or "Product"),
        series=data.get("series") or None,
        classpath=data.get("classpath") or None,
        unspsc=data.get("unspsc") or None,
        official_domain=data.get("official_domain") or None,
        brand=(str(data["brand"]).strip() if data.get("brand") else None),
        manufacturer=(str(data["manufacturer"]).strip() if data.get("manufacturer") else None),
        brand_inferred=bool(data.get("brand_inferred")),
        features=[str(f) for f in (data.get("features") or [])][:20],
        certifications=[str(c) for c in (data.get("certifications") or [])],
        application=data.get("application") or None,
        includes=data.get("includes") or None,
        additional=data.get("additional") or None,
    )
    _fill_attributes(extraction, data, row, retrieval)
    # scalar fields become first-class attributes so provenance flows through
    for json_key, label in (
        ("warranty", "Warranty"),
        ("country_of_origin", "Country of Origin"),
        ("upc", "UPC"),
        ("ean", "EAN"),
        ("gtin", "GTIN"),
    ):
        value = data.get(json_key)
        if value and str(value).strip() and str(value).lower() != "null":
            extraction.attributes.append(Attribute(
                label=label,
                value=str(value).strip(),
                evidence=Evidence(
                    quote=row.part_desc[:200],
                    url=None,
                    tier=0.0,
                ),
                verdict="UNVERIFIED",
            ))
    pq = data.get("package_quantity")
    if isinstance(pq, dict) and str(pq.get("value", "")).strip().isdigit():
        extraction.attributes.append(Attribute(
            label="Package Quantity",
            value=str(pq["value"]).strip(),
            evidence=Evidence(quote=str(pq.get("quote") or row.part_desc[:200]), url=None, tier=0.0),
            verdict="UNVERIFIED",
        ))
    elif isinstance(pq, (int, float)) or (isinstance(pq, str) and pq.strip().isdigit()):
        extraction.attributes.append(Attribute(
            label="Package Quantity",
            value=str(pq).strip(),
            evidence=Evidence(quote=row.part_desc[:200], url=None, tier=0.0),
            verdict="UNVERIFIED",
        ))
    merged = {a.label.lower(): a for a in extraction.attributes}
    for pre in pre_extract_attributes(row.part_desc):
        if pre.label.lower() not in merged:
            extraction.attributes.append(pre)

    if extraction.brand and "brand" not in merged and "brand name" not in merged:
        inferred = bool(getattr(extraction, "brand_inferred", False))
        extraction.attributes.insert(0, Attribute(
            label="Brand Name",
            value=extraction.brand,
            evidence=Evidence(
                quote=(
                    f"inferred from model number {row.mfg_part_num}"
                    if inferred
                    else row.part_desc[:200]
                ),
                url=None,
                tier=0.5 if inferred else 0.0,
            ),
            verdict="UNVERIFIED" if inferred else "UNVERIFIED",
            review_reason=None if not inferred else "brand inferred from manufacturer model-code knowledge",
        ))
    return extraction


async def infer_brand(llm, row: CleanRow, extraction: Extraction) -> None:
    """Focused retry: flash-tier models intermittently skip brand inference."""
    if extraction.brand:
        return
    gen = getattr(llm, "generate", None)
    if gen is None:
        return
    try:
        ans = await gen(
            f"Which retail brand makes the product with model number "
            f"{row.mfg_part_num} and description '{row.part_desc[:120]}'? "
            f"Reply with ONLY the brand name (e.g. DeWalt, Diablo, Milwaukee), "
            f"or NONE if genuinely unknown."
        )
        candidate = ans.strip().strip('"').split("\n")[0]
        if candidate and candidate.upper() != "NONE" and 1 < len(candidate) < 30:
            extraction.brand = candidate
            extraction.manufacturer = extraction.manufacturer or (
                row.mfr_name or None
            )
    except Exception:  # noqa: BLE001 - opportunistic
        pass


def _fill_attributes(extraction, data, row, retrieval):
    seen_labels = set()
    for item in data.get("attributes") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        if not label or not value:
            continue
        key = label.lower()
        if key in seen_labels:
            continue
        seen_labels.add(key)
        quote = item.get("quote")
        evidence = _match_evidence(str(quote) if quote else None, retrieval)
        if evidence is None and quote and str(quote).strip() and str(quote).strip().lower() != row.part_desc.lower():
            # model claims a snippet quote we cannot find -> keep but mark unverified
            attr_evidence = Evidence(quote=str(quote)[:300], url=None, tier=0.0)
            extraction.attributes.append(
                Attribute(
                    label=label,
                    value=value,
                    uom=(str(item["uom"]) if item.get("uom") else None),
                    evidence=attr_evidence,
                    verdict="UNSUPPORTED",
                )
            )
            continue
        if evidence is None:
            # input-description-derived
            attr_evidence = Evidence(quote=row.part_desc[:200], url=None, tier=0.0)
        else:
            attr_evidence = evidence
        extraction.attributes.append(
            Attribute(
                label=label,
                value=value,
                uom=(str(item["uom"]) if item.get("uom") else None),
                evidence=attr_evidence,
            )
        )


async def extract(
    llm,
    row: CleanRow,
    classification: Classification | None,
    retrieval: RetrievalResult | None,
) -> Extraction:
    """Single-row convenience wrapper (one LLM call)."""
    prompt = (
        "Extract structured product data.\n"
        + PROMPT_TEMPLATE.format(
            desc=row.part_desc,
            mfr=row.mfr_name or "unknown",
            classpath=classification.classpath if classification else "unclassified",
            snippets=_snippets_block(retrieval),
            pre=_pre_block(row.part_desc),
        ).split("\n", 1)[1]
    )
    data = await llm.generate_json(prompt, SYSTEM)
    extraction = _parse_extraction(data, row, retrieval)
    await infer_brand(llm, row, extraction)
    return extraction


def _chunk(items, size):
    for i in range(0, len(items), size):
        yield i, items[i : i + size]


async def extract_many(
    llm,
    items: list[tuple[CleanRow, Classification | None, RetrievalResult | None]],
    batch: int = 8,
) -> list[Extraction]:
    """Batched extraction: ~batch rows share one LLM call."""
    results: list[Extraction | None] = [None] * len(items)
    for start, chunk in _chunk(items, batch):
        sections = "\n\n".join(
            _row_section(i, row, cls, ret)
            for i, (row, cls, ret) in enumerate(chunk)
        )
        prompt = MULTI_PROMPT_HEADER + "\nROWS:\n\n" + sections
        attempts = 0
        while True:
            try:
                data = await llm.generate_json(prompt, SYSTEM)
            except LLMError as exc:
                if "invalid JSON" not in str(exc):
                    raise  # quota/network must surface, not degrade quality
                data = []
            usable = bool(data) and (
                isinstance(data, list)
                or isinstance(data, dict)
                and bool(data.get("rows") or data.get("item_type"))
            )
            if usable or attempts >= 1:
                break
            attempts += 1  # one clean retry on an unusable single-shot response
        arr = data if isinstance(data, list) else (data.get("rows") if isinstance(data, dict) else None) or []
        if (
            not arr
            and isinstance(data, dict)
            and data.get("item_type")
            and len(chunk) == 1
        ):
            # single-row batches often come back as one bare object
            arr = [dict(data, index=0)]
        by_index: dict[int, dict] = {}
        for position, entry in enumerate(arr):
            if not isinstance(entry, dict):
                continue
            idx_value = entry.get("index", entry.get("row", position))
            try:
                by_index[int(idx_value)] = entry
            except (TypeError, ValueError):
                continue
        for local_i, (row, _cls, ret) in enumerate(chunk):
            parsed = by_index.get(local_i)
            if parsed and isinstance(parsed, dict) and parsed.get("item_type"):
                candidate = _parse_extraction(parsed, row, ret)
                await infer_brand(llm, row, candidate)
                results[start + local_i] = candidate
            else:
                # model skipped the row -> deterministic input-only fallback
                fallback = Extraction(item_type="Product")
                _fill_attributes(fallback, {"attributes": []}, row, ret)
                for pre in pre_extract_attributes(row.part_desc):
                    fallback.attributes.append(pre)
                await infer_brand(llm, row, fallback)
                results[start + local_i] = fallback
    return [r for r in results if r is not None]
