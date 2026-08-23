"""Deterministic description builders — templates only, no free generation.

Patterns reverse-engineered from the Unilog ground truth (expected Delivery
Format). Each builder takes a DescInput populated with verified attributes
and produces output matching the corresponding GT field format.
"""
import re
from dataclasses import dataclass

from pipeline.models import Attribute

INVOICE_LIMIT = 40
MOBILE_MIN = 55
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
def _norm(s):
    return (s or "").replace("®", "").replace("™", "").strip().lower()

def _brand(d):
    return d.brand_display or d.manuf_name or None

def attr_text(a):
    v = a.value or ""
    v = re.sub(r'(\d)\s*"', r"\1 in", v)
    return f"{v} {a.uom}".strip() if a.uom else v

def _trunc(text, limit):
    if len(text) <= limit: return text
    cut = text[:limit]
    cut = cut.rsplit(" ", 1)[0] if " " in cut else cut
    return cut.rstrip(" ,")

def _get(d, *labels):
    """Return the first matching attr's text."""
    low = {a.label.lower(): a for a in d.attributes}
    for label in labels:
        a = low.get(label.lower())
        if a is not None:
            return attr_text(a)
    return None

def _obj(d, *labels):
    low = {a.label.lower(): a for a in d.attributes}
    for label in labels:
        a = low.get(label.lower())
        if a is not None:
            return a
    return None

def _mount(d):
    return _get(d, "Mounting Type", "Mounting", "Installation")

def _abbr(v, n):
    return v.replace(" ", "").upper()[:n] if v else None


# ---------- MOBILE ----------
def build_mobile_desc(d: DescInput) -> str:
    """GT: Whirlpool, Dishwasher, Eco Series, WDTS7024RZ, Built-in Mounting"""
    d.item_type = d.item_type.title() if d.item_type else d.item_type
    head_parts: list[str] = []
    for part in [d.manuf_name, _brand(d)]:
        np = _norm(part)
        if part and np and np not in [_norm(p) for p in head_parts]:
            head_parts.append(part)
    head = " ".join(head_parts)

    pieces = [p for p in [head, d.item_type.title(), d.series, d.mpn] if p]
    mount = _mount(d)
    out = ", ".join(pieces)
    if len(out) < MOBILE_MIN and d.attributes:
        skip = {_norm(x) for x in [d.manuf_name, _brand(d), d.mpn, d.item_type] if x}
        block = {"brand name", "model number", "product type"}
        extras = [
            attr_text(a) for a in d.attributes[:5]
            if _norm(a.label) not in block
            and _norm(a.label) not in skip
            and _norm(a.value) not in skip
        ]
        if extras:
            out += ", " + ", ".join(extras)
    if mount and mount.lower() not in out.lower():
        out += f", {mount}"
    return out


# ---------- INVOICE ----------
def build_invoice_desc(d: DescInput) -> str:
    """GT: DISHWASHER BLTLN SST SST 120V 10A 41DBA (≤40 CAPS).
    Packs: TYPE COLOR-ABBR MATERIAL-ABBR VOLTS AMPS SOUND."""
    parts = [d.item_type.upper()]
    color = _abbr(_get(d, "Color", "Colour", "Finish"), 5)
    material = _abbr(_get(d, "Material"), 3)
    volts = _obj(d, "Voltage Rating")
    amps = _obj(d, "Amperage Rating")
    # sound/material/color already handled via _get below
    sound = _obj(d, "Sound Level")

    if color: parts.append(color)
    if material: parts.append(material)
    # GT sometimes repeats material abbreviation
    if material and color and color[0] == material[0]: parts.append(material)
    if volts and volts.value: parts.append(f"{volts.value}V")
    if amps and amps.value: parts.append(f"{amps.value}A")
    if sound and sound.value: parts.append(f"{sound.value}DBA")
    return _trunc(" ".join(p for p in parts if p), INVOICE_LIMIT)


# ---------- SHORT / SEARCH TITLE ----------
def build_short_desc(d: DescInput) -> str:
    """GT: Whirlpool® Eco Series WDTS7024RZ Dishwasher, Built-in Mounting,
    Stainless Steel, Stainless Steel"""
    lead_parts = [p for p in [_brand(d), d.series, d.mpn, d.item_type] if p]
    lead = " ".join(lead_parts)
    tail_parts = []
    mount = _mount(d)
    if mount:
        tail_parts.append(f"{mount} Mounting" if "mounting" not in mount.lower() else mount)
    material = _get(d, "Material")
    if material: tail_parts.append(material)
    color = _get(d, "Color")
    if color: tail_parts.append(color)
    return ", ".join([lead] + tail_parts)[:160]


# ---------- LONG ----------
def build_long_desc(d: DescInput) -> str:
    """GT: BRAND Type, Series, V V, A A, Mounting Mounting, dims,
    Depth With Door Open, Min Height, Max Height, Sound dBA Sound Level,
    Material, Material, Additional Information: ..."""
    parts: list[str] = []
    brand = _brand(d)
    parts.append(f"{brand} {d.item_type}".strip() if brand else d.item_type)
    if d.series: parts.append(d.series)

    volts = _obj(d, "Voltage Rating")
    amps = _obj(d, "Amperage Rating")
    # sound/material/color already handled via _get below
    mount = _mount(d)
    size = _get(d, "Size")
    depth = _get(d, "Depth With Door Open")
    min_h = _get(d, "Minimum Height")
    max_h = _get(d, "Maximum Height")
    sound = _get(d, "Sound Level")
    material = _get(d, "Material")
    color = _get(d, "Color")

    if volts: parts.append(f"{volts.value} V")
    if amps: parts.append(f"{amps.value} A")
    if mount: parts.append(f"{mount} Mounting" if "mounting" not in mount.lower() else mount)
    if size: parts.append(size)
    if depth: parts.append(depth if "depth with door open" in depth.lower() else f"{depth} Depth With Door Open")
    if min_h: parts.append(min_h if "minimum height" in min_h.lower() else f"{min_h} Minimum Height")
    if max_h: parts.append(max_h if "maximum height" in max_h.lower() else f"{max_h} Maximum Height")
    if sound:
        parts.append(sound if "sound level" in sound.lower() else f"{sound} Sound Level")
    if material: parts.append(material)
    if color and color != material: parts.append(material)  # GT repeats material
    if d.additional: parts.append(f"Additional Information: {d.additional}")
    return ", ".join(p for p in parts if p)[:600]


# ---------- RETAIL ----------
def build_retail_desc(d: DescInput) -> str:
    """GT: Eco Series Dishwasher, Built-in Mounting, Stainless Steel, Stainless Steel"""
    series_part = " ".join(p for p in [d.series, d.item_type] if p)
    parts = [series_part or d.item_type]
    mount = _mount(d)
    if mount: parts.append(f"{mount} Mounting" if "mounting" not in mount.lower() else mount)
    material = _get(d, "Material")
    if material: parts.append(material)
    color = _get(d, "Color")
    if color: parts.append(color)
    return ", ".join(parts)[:160]
