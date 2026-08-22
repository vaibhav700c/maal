from difflib import SequenceMatcher

from pipeline.models import RowResult

TIER_BASE = {0.0: 0.35, 0.8: 0.7, 0.9: 0.75, 1.0: 1.0}
VERDICT_MULT = {"CONFIRMED": 1.0, "UNVERIFIED": 0.6, "UNSUPPORTED": 0.45, "REFUTED": 0.0}

FLAG_WEIGHTS = {
    "NEEDS_REVIEW": 0.3,
    "NO_MFR_DOMAIN": 0.2,
    "NO_RETRIEVED_EVIDENCE": 0.15,
    "MARKETPLACE_HIT_EXCLUDED": 0.05,
    "DUPLICATE_SUSPECT": 0.2,
    "PHYSICS_VIOLATION": 0.4,
}


def tier_base(tier: float | None) -> float:
    if tier is None:
        return TIER_BASE[0.0]
    return TIER_BASE.get(round(tier, 2), min(1.0, max(0.35, tier)))


def score_attribute(attr) -> float:
    base = tier_base(attr.evidence.tier if attr.evidence else None)
    mult = VERDICT_MULT.get(attr.verdict, VERDICT_MULT["UNVERIFIED"])
    score = base * mult
    if attr.review_reason:
        score -= 0.1
    return round(max(0.0, min(1.0, score)), 3)


def apply_scores(extraction) -> None:
    if not extraction:
        return
    for attr in extraction.attributes:
        attr.confidence = score_attribute(attr)


def missing_core_fraction(row: RowResult) -> float:
    from pipeline.format.emit import CORE_FIELDS

    present = {k for k, v in row.output_row.items() if v}
    missing = sum(1 for f in CORE_FIELDS if f not in present)
    return missing / len(CORE_FIELDS)


def triage_score(row: RowResult) -> float:
    """Higher = more urgent human review."""
    flags_weight = sum(FLAG_WEIGHTS.get(f, 0.1) for f in row.flags)
    confidences = [a.confidence for a in row.extraction.attributes] if row.extraction else []
    mean_conf = sum(confidences) / len(confidences) if confidences else 0.5
    return round(
        min(1.0, 0.4 * missing_core_fraction(row) + 0.3 * min(flags_weight, 1.0) + 0.3 * (1 - mean_conf)),
        3,
    )


def _normalize(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def dedup_flags(rows: list[RowResult], threshold: float = 0.92) -> set[str]:
    """Returns set of mfg_part_nums that look like near-duplicates of another
    row with the same manufacturer code."""
    flagged: set[str] = set()
    by_code: dict[str, list[RowResult]] = {}
    for row in rows:
        key = row.clean.mfr_code or row.clean.mfr_name or "?"
        by_code.setdefault(key, []).append(row)
    for group in by_code.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a = _normalize(group[i].clean.part_desc)
                b = _normalize(group[j].clean.part_desc)
                if not a or not b:
                    continue
                ratio = SequenceMatcher(None, a, b).ratio()
                if ratio >= threshold and abs(len(a) - len(b)) <= max(len(a), len(b)) * 0.15:
                    flagged.add(group[i].mfg_part_num)
                    flagged.add(group[j].mfg_part_num)
    return flagged


def mark_duplicates(rows: list[RowResult]) -> None:
    for mpn in dedup_flags(rows):
        row = next(r for r in rows if r.mfg_part_num == mpn)
        if "DUPLICATE_SUSPECT" not in row.flags:
            row.flags.append("DUPLICATE_SUSPECT")
