"""Adversarial verifier: second LLM pass attempts to refute extracted claims."""
from pipeline.llm import LLMError
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


def mark_unsupported_without_evidence(extraction: Extraction) -> Extraction:
    """Deterministic policy: with zero external sources there is nothing an
    auditor could confirm, so stake claims are marked UNSUPPORTED without
    spending an LLM call."""
    for attr in select_stakes(extraction):
        attr.verdict = "UNSUPPORTED"
        attr.review_reason = (
            attr.review_reason or "no manufacturer source available to verify"
        )
    return extraction


async def verify(llm, extraction: Extraction, retrieval: RetrievalResult | None) -> Extraction:
    stakes = select_stakes(extraction)
    if not stakes:
        return extraction
    claims = "\n".join(
        f"{i}: {a.label} = {a.value}{' ' + a.uom if a.uom else ''}"
        for i, a in enumerate(stakes)
    )
    if not retrieval or not retrieval.snippets:
        return mark_unsupported_without_evidence(extraction)
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


def _chunk(items, size):
    for i in range(0, len(items), size):
        yield i, items[i : i + size]


async def verify_many(
    llm,
    pairs: list[tuple[Extraction, RetrievalResult | None]],
    batch: int = 8,
) -> list[Extraction]:
    """Batched audit; pairs without evidence are resolved deterministically."""
    results: list[Extraction] = []
    pending: list[tuple[int, Extraction]] = []
    for i, (extraction, retrieval) in enumerate(pairs):
        if not select_stakes(extraction) or not retrieval or not retrieval.snippets:
            if select_stakes(extraction):
                mark_unsupported_without_evidence(extraction)
            results.append(extraction)
        else:
            pending.append((i, extraction))
            results.append(extraction)  # placeholder; mutated below

    for start, chunk in _chunk(pending, batch):
        blocks = []
        for offset, (_, extraction) in enumerate(chunk):
            stakes = select_stakes(extraction)
            claims = "\n".join(
                f"{offset}.{j}: {a.label} = {a.value}{' ' + a.uom if a.uom else ''}"
                for j, a in enumerate(stakes)
            )
            blocks.append(f"=== CLAIM GROUP {offset} ===\n{claims}")
        # sources from the group's retrievals (first of each pair carries its own;
        # per-group sources embedded to avoid cross-contamination)
        sections = []
        for offset, (idx, _) in enumerate(chunk):
            extraction, retrieval = pairs[idx]
            sections.append(
                f"=== SOURCE GROUP {offset} ===\n{_sources_block(retrieval)}"
            )
        prompt = (
            "Audit claim groups against their own source groups. Group k claims "
            "may only be judged using SOURCE GROUP k.\n\nCLAIMS:\n"
            + "\n\n".join(blocks)
            + "\n\nSOURCES:\n"
            + "\n\n".join(sections)
        )
        try:
            data = await llm.generate_json(prompt, SYSTEM)
        except LLMError as exc:
            if "invalid JSON" not in str(exc):
                raise
            data = []
        verdicts = data if isinstance(data, list) else (data.get("verdicts") if isinstance(data, dict) else None) or []
        by_key: dict[tuple[int, int], dict] = {}
        for v in verdicts:
            if not isinstance(v, dict) or "index" not in v:
                continue
            raw = str(v["index"])
            try:
                group_s, item_s = raw.split(".")
                by_key[(int(group_s), int(item_s))] = v
            except ValueError:
                continue
        for offset, (idx, extraction) in enumerate(chunk):
            stakes = select_stakes(extraction)
            for j, attr in enumerate(stakes):
                v = by_key.get((offset, j))
                if not v:
                    attr.verdict = "UNSUPPORTED"
                    attr.review_reason = attr.review_reason or "auditor returned no verdict"
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
    return results