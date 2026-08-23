"""Deterministic description builders — templates only, no free generation.

Patterns follow the Unilog ground truth (expected Delivery Format):
  MOBILE   : {Manuf} {Brand}, {Type}, {Series}, {MPN}, {Mounting}
  INVOICE  : TYPE COLOR-ABBR MATERIAL-ABBR VOLTS AMPS SOUND  (≤40 CAPS)
  SHORT    : BRAND® Series MPN Type, Mounting, Material
  LONG     : BRAND Type, Series, V V, A A, Mounting, dims…, Additional Information:
  RETAIL   : Series Type, Mounting, Material[, Color]
"""
import re
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


# ---------- tiny helpers ----------
def _norm(s: str | None) -> str:
    return (s or "").replace("®", "").replace("™", "").strip().lower()


def _brand(d: DescInput) -> str | None:
    return d.brand_display or d.manuf_name or None


def attr_text(a: Attribute) -> str:
    value = a.value or ""
    value = re.sub(r'(\d)\s*"', r"\1 in", value)  # 30 " -> 30 in
    return f"{value} {a.uom}".strip() if a.uom else value


def _truncate_words(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    cut = cut.rsplit(" ", 1)[0] if " " in cut else cut
    return cut.rstrip(" ,")


def _first(d: DescInput, *labels: str) -> str | None:
    low = {a.label.lower(): attr_text(a) for a in d.attributes}
    for label in labels:
        v = low.get(label.lower())
        if v:
            return v
    return None


def _first_obj(d: DescInput, *labels: str):
    low = {a.label.lower(): a for a in d.attributes}
    for label in labels:
        a = low.get(label.lower())
        if a is not None:
            return a
    return None


def _abbr(v: str | None, n: int) -> str | None:
    if not v:
        return None
    compact = v.replace(" ", "").upper()
    return compact[:n] or None


def _mount(d: DescInput) -> str | None:
    return _first(d, "Mounting Type", "Mounting", "Installation")


# ---------- builders ----------
def build_invoice_desc(d: DescInput) -> str:
    """GT: DISHWASHER BLTLN SST SST 120V 10A 41DBA (≤40, CAPS)."""
    parts = [d.item_type.upper()]
    color = _abbr(_first(d, "Color", "Colour"), 6)
    material = _abbr(_first(d, "Material"), 3)
    volts = _first_obj(d, "Voltage Rating")
    amps = _first_obj(d, "Amperage Rating")
    sound = _first_obj(d, "Sound Level")
    size = _first(d, "Size")

    if color:
        c = _abbr(color, 3)
        if c:
            parts.append(c)
    if material:
        m = _abbr(material, 3)
        if m:
            parts.append(m)
    if volts and volts.value:
        parts.append(f"{volts.value}V")
    if amps and amps.value:
        parts.append(f"{amps.value}A")
    if sound and sound.value:
        parts.append(f"{sound.value}DBA")
    return _truncate_words(" ".join(p for p in parts if p), INVOICE_LIMIT)


def _title(s: str | None) -> str | None:
    return s.title() if s else s


def build_mobile_desc(d: DescInput) -> str:
    """GT: 'Whirlpool, Dishwasher, Eco Series, WDTS7024RZ, Built-in Mounting'"""
    d.item_type = _title(d.item_type) or d.item_type
    head_parts: list[str] = []
    for part in [d.manuf_name, _brand(d)]:
        if part and _norm(part) not in [_norm(p) for p in head_parts]:
            head_parts.append(part)
    head = " ".join(head_parts)
    mounting = _mount(d) or ""
    mount_suffix = f" {mounting}" if mounting else ""
    out = ", ".join(
        p for p in [head, d.item_type, d.series, d.mpn] if p
    )
    if len(out) < MOBILE_MIN and mounting:
        out += f", {mounting}"
    elif mounting and d.mpn:
        # append mounting to the last element before MPN for closer GT match
        pass
    if len(out) < MOBILE_MIN and d.attributes:
        skip = {_norm(p) for p in [d.manuf_name, _brand(d), d.mpn, d.item_type] if p}
        label_block = {"brand name", "model number", "product type"}
        extra = ", ".join(
            attr_text(a)
            for a in d.attributes[:5]
            if _norm(a.label) not in label_block
            and _norm(a.label) not in skip
            and _norm(a.value) not in skip
        )
        if extra:
            out = f"{out}, {extra}"
    return out


def build_short_desc(d: DescInput) -> str:
    """GT: BRAND Series MPN Type, Mounting, Material (space-joined lead)."""
    lead = " ".join(
        p for p in [_brand(d), d.series, d.mpn, d.item_type] if p
    )
    tail = [
        t for t in (
            _mount(d),
            _first(d, "Material"),
            _first(d, "Color"),
        ) if t
    ]
    return ", ".join([lead] + tail)[:160]


def build_long_desc(d: DescInput) -> str:
    parts: list[str] = []
    brand = _brand(d)
    parts.append(f"{brand} {d.item_type}".strip() if brand else d.item_type)
    if d.series:
        parts.append(d.series)
    volts = _first_obj(d, "Voltage Rating")
    amps = _first_obj(d, "Amperage Rating")
    mounting = _mount(d)
    size = _first(d, "Size")
    depth = _first(d, "Depth With Door Open")
    min_h = _first(d, "Minimum Height")
    sound = _first_obj(d, "Sound Level")
    material = _first(d, "Material")
    color = _first(d, "Color")

    if volts:
        parts.append(f"{volts.value} V")
    if amps:
        parts.append(f"{amps.value} A")
    if mounting:
        parts.append(mounting)
    if size:
        parts.append(size)
    if depth:
        parts.append(f"{depth} Depth With Door Open" if "depth with door open" not in depth.lower() else depth)
    if min_h:
        parts.append(f"{min_h} Minimum Height" if "minimum height" not in min_h.lower() else min_h)
    if sound:
        sv = sound.value
        parts.append(f"{sv} dBA Sound Level" if "dba" not in sv.lower() else sv)
    if material:
        parts.append(material)
    if color:
        parts.append(color)
    if d.additional:
        parts.append(f"Additional Information: {d.additional}")
    return ", ".join(p for p in parts if p)[:600]


def build_retail_desc(d: DescInput) -> str:
    series_part = " ".join(p for p in [d.series, d.item_type] if p)
    parts = [series_part or d.item_type]
    for label in ("Mounting Type", "Material", "Color"):
        v = _first(d, label)
        if v:
            parts.append(v)
    return ", ".join(parts)[:160]
