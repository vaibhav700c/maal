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
    "You are a precise industrial catalog data extractor. Extract facts ONLY "
    "from the raw description and the supplied source snippets. NEVER invent "
    "values. Every attribute you output MUST carry a short verbatim 'quote' "
    "copied exactly from the description or one of the snippets. If a fact is "
    "not present, omit it. Output STRICT JSON only."
)

PROMPT_TEMPLATE = """Extract structured product data.

RAW DESCRIPTION: {desc}
MANUFACTURER: {mfr}
CLASSPATH: {classpath}

SOURCE SNIPPETS (manufacturer-owned pages):
{snippets}

Output STRICT JSON:
{{"item_type": "short product type noun",
  "series": "series name or null",
  "brand": "brand printed on the product (e.g. '3M', 'Diablo', 'Leviton') or null — NOT the distributor",
  "manufacturer": "actual product manufacturer you are confident about, else null",
  "attributes": [{{"label": "...", "value": "...", "uom": "approved abbrev or null", "quote": "verbatim source text"}}],
  "features": ["short feature phrase", ...],
  "certifications": ["UL Listed", ...],
  "application": "or null",
  "includes": "or null",
  "additional": "misc specs sentence or null"}}

Pre-extracted from the description (confirm, correct, or extend — do not drop unless wrong):
{pre}"""

_DIM_RE = re.compile(r"(\d*\.?\d+(?:-\d+/\d+|/\d+)?)\"")
_VOLT_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s?V\b")
_AMP_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s?A\b")
_WATT_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s?W\b")
_GRIT_RE = re.compile(r"\bP(\d{2,4})\b")


def pre_extract_attributes(desc: str) -> list[Attribute]:
    attrs: list[Attribute] = []

    def add(label: str, value: str, uom: str | None):
        attrs.append(
            Attribute(
                label=label,
                value=value,
                uom=uom,
                evidence=Evidence(quote=desc[:200], url=None, tier=0.0),
            )
        )

    dims = _DIM_RE.findall(desc)
    if len(dims) >= 3:
        add("Diameter", dims[0], "in")
        add("Thickness", dims[1], "in")
        add("Arbor", dims[2], "in")
    elif len(dims) == 2:
        add("Diameter", dims[0], "in")
        add("Arbor", dims[1], "in")
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
    for i, snip in enumerate(retrieval.snippets[:5]):
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


def _parse_extraction(
    data: dict,
    row: CleanRow,
    retrieval: RetrievalResult | None,
) -> Extraction:
    extraction = Extraction(
        item_type=str(data.get("item_type") or "Product"),
        series=data.get("series") or None,
        brand=(str(data["brand"]).strip() if data.get("brand") else None),
        manufacturer=(str(data["manufacturer"]).strip() if data.get("manufacturer") else None),
        features=[str(f) for f in (data.get("features") or [])][:20],
        certifications=[str(c) for c in (data.get("certifications") or [])],
        application=data.get("application") or None,
        includes=data.get("includes") or None,
        additional=data.get("additional") or None,
    )
    _fill_attributes(extraction, data, row, retrieval)
    merged = {a.label.lower(): a for a in extraction.attributes}
    for pre in pre_extract_attributes(row.part_desc):
        if pre.label.lower() not in merged:
            extraction.attributes.append(pre)
    return extraction


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
    return _parse_extraction(data, row, retrieval)


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
        try:
            data = await llm.generate_json(prompt, SYSTEM)
        except LLMError as exc:
            if "invalid JSON" not in str(exc):
                raise  # quota/network problems must surface, not degrade quality
            data = []  # malformed model output -> deterministic fallbacks
        arr = data if isinstance(data, list) else (data.get("rows") if isinstance(data, dict) else None) or []
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
                results[start + local_i] = _parse_extraction(parsed, row, ret)
            else:
                # model skipped the row -> deterministic input-only fallback
                fallback = Extraction(item_type="Product")
                _fill_attributes(fallback, {"attributes": []}, row, ret)
                for pre in pre_extract_attributes(row.part_desc):
                    fallback.attributes.append(pre)
                results[start + local_i] = fallback
    return [r for r in results if r is not None]
