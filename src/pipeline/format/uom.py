"""Unit-of-measure normalization and inch-fraction conversion."""
import math
import re

# Approved abbreviation map (subset of house UOM standards; extensible).
APPROVED_UOM: dict[str, str] = {
    # length
    "in": "in", "in.": "in", "inch": "in", "inches": "in", '"': "in",
    "ft": "ft", "ft.": "ft", "foot": "ft", "feet": "ft", "'": "ft",
    "mm": "mm", "millimeter": "mm", "millimeters": "mm",
    "cm": "cm", "centimeter": "cm", "centimeters": "cm",
    "m": "m", "meter": "m", "meters": "m",
    # electrical
    "v": "V", "volt": "V", "volts": "V",
    "a": "A", "amp": "A", "amps": "A",
    "w": "W", "watt": "W", "watts": "W",
    "kw": "kW", "kilowatt": "kW", "kilowatts": "kW",
    "hz": "Hz", "hertz": "Hz",
    # acoustics / thermal
    "dba": "dBA",
    "f": "deg F", "°f": "deg F", "degrees fahrenheit": "deg F",
    "c": "deg C", "°c": "deg C", "degrees celsius": "deg C",
    "btu": "BTU", "btuh": "BTUH",
    # pressure / flow
    "psi": "psi", "gpm": "gpm", "cfm": "CFM", "lpm": "LPM",
    # weight
    "lb": "lb", "lb.": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "kg": "kg", "gram": "g", "grams": "g", "g": "g",
    # speed / misc
    "rpm": "RPM", "hp": "hp", "hr": "hr", "hour": "hr", "hours": "hr",
    "min": "min", "sec": "sec", "s": "sec",
    "kwhr": "kW-hr", "kw-hr": "kW-hr", "kwh": "kW-hr",
    "ga": "gal", "gal": "gal", "gallon": "gal", "gallons": "gal",
    "l": "L", "liter": "L", "liters": "L",
}

_FRACTION_RE = r"\d+/\d+"


def normalize_uom(raw: str) -> str:
    key = raw.strip().lower()
    if key in APPROVED_UOM:
        return APPROVED_UOM[key]
    raise ValueError(f"unknown UOM form: {raw!r}")


def decimal_to_fraction(value: float, denom: int = 64, tol: float = 0.0101) -> str | None:
    """Mixed/inch-fraction rendering of value at nearest n/denom, reduced by gcd.

    50.25 -> '50-1/4'; 0.5 -> '1/2'; 24 -> '24'; None when not within tolerance.
    """
    sign = "-" if value < 0 else ""
    value = abs(value)
    whole = int(value)
    rem = value - whole
    nearest = round(rem * denom)
    if nearest == denom:  # e.g. rem 0.996 snapped up
        nearest = 0
        whole += 1
    if abs(nearest / denom - rem) > tol:
        return None
    g = math.gcd(nearest, denom) if nearest else 1
    num, den = nearest // g, denom // g
    if den == 1:
        return f"{sign}{whole + num}"
    prefix = f"{whole}-" if whole else ""
    return f"{sign}{prefix}{num}/{den}"


def format_measure(value: float) -> str:
    """Render 50.25 -> '50-1/4'; whole numbers plain; pure fractions '7/64'."""
    rendered = decimal_to_fraction(value)
    return rendered if rendered is not None else f"{value:g}"


def _replace_number_unit(match: re.Match) -> str:
    number, unit = match.group(1), match.group(2)
    try:
        approved = normalize_uom(unit)
    except ValueError:
        approved = unit
    return f"{number} {approved}"


def normalize_measurement_text(text: str) -> str:
    """Fix spacing and canonicalize units in measurement strings.

    Handles: 14"x7/64"x1"  -> 14 in x 7/64 in x 1 in ; 24in -> 24 in.
    """
    # inch-quote immediately followed by an x separator keeps its spacing sane
    result = re.sub(r'"\s*([xX]\s*)', r" in \1", text)
    result = result.replace('"', " in")
    # canonical spacing around measurement separators and number-unit pairs
    result = re.sub(r"\s*([xX])\s*", r" \1 ", result)
    result = re.sub(
        r"(\d+(?:\.\d+)?(?:-\d+/\d+)?)\s*([A-Za-zµ°]{1,6})\b",
        _replace_number_unit,
        result,
    )
    return re.sub(r"\s{2,}", " ", result).strip()
