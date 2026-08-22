"""Structured attribute extraction with mandatory evidence quotes."""
import re

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


async def extract(
    llm,
    row: CleanRow,
    classification: Classification | None,
    retrieval: RetrievalResult | None,
) -> Extraction:
    pres = pre_extract_attributes(row.part_desc)
    pre_block = "\n".join(
        f'- {a.label}: {a.value}{" " + a.uom if a.uom else ""}' for a in pres
    ) or "(none)"
    prompt = PROMPT_TEMPLATE.format(
        desc=row.part_desc,
        mfr=row.mfr_name or "unknown",
        classpath=classification.classpath if classification else "unclassified",
        snippets=_snippets_block(retrieval),
        pre=pre_block,
    )
    data = await llm.generate_json(prompt, SYSTEM)
    extraction = Extraction(
        item_type=str(data.get("item_type") or "Product"),
        series=data.get("series") or None,
        features=[str(f) for f in (data.get("features") or [])][:20],
        certifications=[str(c) for c in (data.get("certifications") or [])],
        application=data.get("application") or None,
        includes=data.get("includes") or None,
        additional=data.get("additional") or None,
    )
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
    merged = {a.label.lower(): a for a in extraction.attributes}
    for pre in pres:
        if pre.label.lower() not in merged:
            extraction.attributes.append(pre)
    return extraction
