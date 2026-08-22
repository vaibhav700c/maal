"""Adversarial verifier: second LLM pass attempts to refute extracted claims."""
from pipeline.models import Extraction, RetrievalResult

SYSTEM = (
    "You are an adversarial auditor. Your job is to REFUTE product claims "
    "using only the provided sources. For each claim output CONFIRMED if a "
    "source clearly supports it, REFUTED if a source contradicts it, and "
    "UNSUPPORTED if no source addresses it. Be strict; do not assume."
)

STAKE_LABELS = {
    "voltage rating", "amperage rating", "wattage", "sound level",
    "diameter", "thickness", "arbor", "length", "width", "height",
    "depth with door open", "weight", "capacity", "grit", "inner diameter",
    "outer diameter", "pressure rating", "minimum height", "maximum height",
}


def numeric_attr(attr) -> bool:
    try:
        float(attr.value.replace(",", "").rstrip("%"))
        return True
    except ValueError:
        return False


def select_stakes(extraction: Extraction):
    out = []
    for attr in extraction.attributes:
        label_low = attr.label.lower()
        if label_low in STAKE_LABELS or any(s in label_low for s in ("size", "rating")) or numeric_attr(attr):
            out.append(attr)
    return out


PROMPT_TEMPLATE = """Audit these product claims against the sources below.

CLAIMS:
{claims}

SOURCES:
{sources}

For every claim index, output STRICT JSON array:
[{{"index": 0, "verdict": "CONFIRMED|REFUTED|UNSUPPORTED", "reason": "one short sentence"}}]"""


def _sources_block(retrieval: RetrievalResult | None) -> str:
    if not retrieval or not retrieval.snippets:
        return "(no external sources; judge against internal consistency only)"
    return "\n".join(
        f"[S{i}] ({s.url or 'unknown'}) {s.quote}"
        for i, s in enumerate(retrieval.snippets[:6])
    )


async def verify(llm, extraction: Extraction, retrieval: RetrievalResult | None) -> Extraction:
    stakes = select_stakes(extraction)
    if not stakes:
        return extraction
    claims = "\n".join(
        f"{i}: {a.label} = {a.value}{' ' + a.uom if a.uom else ''}"
        for i, a in enumerate(stakes)
    )
    data = await llm.generate_json(
        PROMPT_TEMPLATE.format(claims=claims, sources=_sources_block(retrieval)),
        SYSTEM,
    )
    verdicts = data if isinstance(data, list) else data.get("verdicts", [])
    by_index: dict[int, dict] = {}
    for v in verdicts:
        if isinstance(v, dict) and "index" in v:
            try:
                by_index[int(v["index"])] = v
            except (TypeError, ValueError):
                continue
    for i, attr in enumerate(stakes):
        v = by_index.get(i)
        if not v:
            attr.verdict = "UNSUPPORTED"
            attr.review_reason = "auditor returned no verdict"
            continue
        verdict = str(v.get("verdict", "UNSUPPORTED")).upper()
        reason = str(v.get("reason", ""))
        if verdict == "CONFIRMED":
            attr.verdict = "CONFIRMED"
        elif verdict == "REFUTED":
            attr.verdict = "REFUTED"
            attr.review_reason = reason or "refuted by adversarial audit"
        else:
            attr.verdict = "UNSUPPORTED"
            attr.review_reason = reason or "no supporting source found"
    return extraction
