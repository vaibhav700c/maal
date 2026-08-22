"""Deterministic description builders — no LLM generation, templates only."""
from dataclasses import dataclass

from pipeline.models import Attribute

INVOICE_LIMIT = 40
MOBILE_MIN = 60
MOBILE_MAX = 80


@dataclass
class DescInput:
    brand_display: str | None
    manuf_name: str | None
    mpn: str
    item_type: str
    series: str | None
    feature: str | None
    attributes: list[Attribute]
    additional: str | None = None


def _attr_text(attr: Attribute) -> str:
    if attr.uom and attr.value and attr.value[-1].isdigit():
        return f"{attr.value} {attr.uom}"
    if attr.uom:
        return f"{attr.value} {attr.uom}"
    return attr.value


def _join(parts: list[str | None]) -> str:
    return ", ".join(p for p in parts if p)


def _truncate_words(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,")


def build_invoice_desc(d: DescInput) -> str:
    """Compact CAPS till-receipt description, ≤40 chars (ground-truth style)."""
    parts = [d.item_type.upper()]
    for attr in d.attributes[:6]:
        compact = _attr_text(attr).replace(" ", "")
        parts.append(compact.upper())
    return _truncate_words(" ".join(parts), INVOICE_LIMIT)


def _brand(d: DescInput) -> str | None:
    brand = d.brand_display or d.manuf_name
    return brand or None


def build_mobile_desc(d: DescInput) -> str:
    """'{Manuf} {Brand}, {Type}, {Series}, {MPN}' per ground truth."""
    head = " ".join(p for p in [d.manuf_name, _brand(d)] if p)
    return _join([head, d.item_type, d.series, d.mpn])


def build_short_desc(d: DescInput) -> str:
    """Search title: Brand Series MPN Type With Feature, key attributes."""
    lead = " ".join(
        p for p in [_brand(d), d.series, d.mpn, d.item_type] if p
    )
    with_feature = f"{lead} With {d.feature}" if d.feature else lead
    tail = [
        _attr_text(a)
        for a in d.attributes
        if a.label in {"Mounting Type", "Material", "Color", "Size"}
    ][:3]
    out = _join([with_feature] + tail)
    if len(out) > MOBILE_MAX + 40:
        out = _truncate_words(out, MOBILE_MAX + 40)
    return out


def build_long_desc(d: DescInput) -> str:
    """Full attribute enumeration ending with Additional Information."""
    lead = " ".join(p for p in [_brand(d), d.item_type] if p)
    with_feature = f"{lead} With {d.feature}," if d.feature else f"{lead},"
    body_parts = [p for p in [d.series] if p]
    for attr in d.attributes:
        text = _attr_text(attr)
        body_parts.append(f"{text} {attr.label}" if attr.uom else text)
    out = f"{with_feature} " + ", ".join(body_parts)
    if d.additional:
        out += f", Additional Information: {d.additional}"
    return out


def build_retail_desc(d: DescInput) -> str:
    """Short shopper-facing line: Series Type, top attributes."""
    parts = [" ".join(p for p in [d.series, d.item_type] if p)]
    for attr in d.attributes[:3]:
        if attr.label not in {"Voltage Rating", "Amperage Rating"}:
            parts.append(_attr_text(attr))
    return _join(parts)[:160]
