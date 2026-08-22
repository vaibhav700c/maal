"""Physics-aware validation of extracted values using the Z3 solver."""
import re

from pipeline.models import Extraction, PhysicsCheck, PhysicsReport
from pipeline.format.uom import decimal_to_fraction
from z3 import And, Bool, Implies, Not, Real, RealVal, Solver, unsat

# Unit-range sanity: label -> (uom, min, max)
RANGE_RULES = {
    ("Sound Level", "dBA"): (30.0, 80.0),
    ("Voltage Rating", "V"): (0.5, 1000.0),
    ("Amperage Rating", "A"): (0.05, 400.0),
    ("Wattage", "W"): (0.1, 20000.0),
    ("Pressure Rating", "psi"): (0.0, 10000.0),
}

_FRACTION_TOKEN = re.compile(r"(\d+)-(\d+)/(\d+)|(\d+)/(\d+)")


def _fraction_value(text: str) -> float | None:
    match = _FRACTION_TOKEN.fullmatch(text.strip())
    if not match:
        return None
    if match.group(1):
        return int(match.group(1)) + int(match.group(2)) / int(match.group(3))
    return int(match.group(4)) / int(match.group(5))


def parse_qty(text: str) -> tuple[float, str | None] | None:
    """Parse '120 V' / '50-1/4 in' / '15' -> (value, uom)."""
    if not text:
        return None
    tokens = text.strip().split()
    number = tokens[0]
    fraction = _fraction_value(number)
    value = fraction if fraction is not None else _try_float(number)
    if value is None:
        return None
    uom = tokens[1] if len(tokens) > 1 else None
    return (value, uom)


def _try_float(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _attr_map(extraction: Extraction) -> dict[str, tuple[float, str | None]]:
    out = {}
    for attr in extraction.attributes:
        parsed = parse_qty(attr.value)
        if parsed is not None:
            out[attr.label] = parsed
    return out


def _check(name: str, status: str, fields=None, reason=None) -> PhysicsCheck:
    return PhysicsCheck(
        name=name,
        status=status,
        fields=fields or [],
        reason=reason,
    )


def check_power_balance(attrs: dict[str, tuple[float, str | None]]) -> PhysicsCheck:
    needed = {"Voltage Rating", "Amperage Rating", "Wattage"}
    if not needed <= attrs.keys():
        return _check("power_balance", "SKIPPED")
    volts = attrs["Voltage Rating"][0]
    amps = attrs["Amperage Rating"][0]
    watts = attrs["Wattage"][0]
    from z3 import Or

    v, a, w = Real("v"), Real("a"), Real("w")
    solver = Solver()
    solver.add(v == RealVal(volts), a == RealVal(amps), w == RealVal(watts))
    tolerance = RealVal("1/10")  # ±10%
    too_low = w < (RealVal(1) - tolerance) * (v * a)
    too_high = w > (RealVal(1) + tolerance) * (v * a)
    solver.assert_and_track(Or(too_low, too_high), "power_balance")
    if solver.check() == unsat:
        # violation formula unsatisfiable -> stated values obey P = V x I
        return _check("power_balance", "SAT", sorted(needed))
    return _check(
        "power_balance",
        "UNSAT",
        sorted(needed),
        f"watts {watts:g} does not equal volts {volts:g} x amps {amps:g} "
        "(within 10%); one of these values is wrong",
    )


def check_diameter_gt_arbor(attrs: dict[str, tuple[float, str | None]]) -> PhysicsCheck:
    pairs = [
        (("Diameter", "Disc Diameter"), ("Arbor", "Arbor Size", "Bore")),
        (("Blade Diameter",), ("Arbor", "Arbor Size", "Bore")),
    ]
    for dia_names, bore_names in pairs:
        dia = next((attrs[n][0] for n in dia_names if n in attrs), None)
        bore = next((attrs[n][0] for n in bore_names if n in attrs), None)
        if dia is None or bore is None or dia == bore:
            continue
        if dia <= bore:
            return _check(
                "diameter_gt_arbor",
                "UNSAT",
                [n for n in list(dia_names) + list(bore_names) if n in attrs],
                f"disc/blade diameter {dia:g} must be larger than the arbor/bore {bore:g}",
            )
        return _check(
            "diameter_gt_arbor", "SAT", [n for n in list(dia_names) + list(bore_names) if n in attrs]
        )
    return _check("diameter_gt_arbor", "SKIPPED")


def check_id_lt_od(attrs: dict[str, tuple[float, str | None]]) -> PhysicsCheck:
    inner = next((attrs[n][0] for n in ("Inner Diameter", "ID", "Bore Diameter") if n in attrs), None)
    outer = next((attrs[n][0] for n in ("Outer Diameter", "OD") if n in attrs), None)
    if inner is None or outer is None:
        return _check("id_lt_od", "SKIPPED")
    fields = ["Inner Diameter", "Outer Diameter"]
    if inner >= outer:
        return _check(
            "id_lt_od",
            "UNSAT",
            fields,
            f"inner diameter {inner:g} cannot be greater than or equal to outer diameter {outer:g}",
        )
    return _check("id_lt_od", "SAT", fields)


def check_unit_ranges(extraction: Extraction) -> PhysicsCheck:
    violations: list[tuple[str, str]] = []
    for attr in extraction.attributes:
        rule_key = next(
            (k for k in RANGE_RULES if k[0].lower() == attr.label.lower()), None
        )
        if rule_key is None:
            continue
        parsed = parse_qty(attr.value)
        if parsed is None:
            continue
        value, uom = parsed
        uom = uom or attr.uom
        expected_uom = rule_key[1]
        low, high = RANGE_RULES[rule_key]
        if uom and uom != expected_uom:
            violations.append(
                (
                    attr.label,
                    f"{attr.label} given in {uom} but requires {expected_uom} "
                    f"in range {low:g}-{high:g}",
                )
            )
        elif not (low <= value <= high):
            violations.append(
                (attr.label, f"{attr.label} value {value:g}{expected_uom} outside plausible range")
            )
    if violations:
        return _check(
            "unit_range_sanity",
            "UNSAT",
            [label for label, _ in violations],
            "; ".join(reason for _, reason in violations),
        )
    checked = any(k[0] in {a.label for a in extraction.attributes} for k in RANGE_RULES)
    return _check("unit_range_sanity", "SAT" if checked else "SKIPPED")


def check_fraction_consistency(extraction: Extraction) -> PhysicsCheck:
    """Within one attribute value, a written fraction and decimal describing the
    same measurement must agree."""
    problems: list[str] = []
    labels: list[str] = []
    for attr in extraction.attributes:
        numbers = re.findall(r"\d+(?:-\d+/\d+)?(?:\.\d+)?(?:/\d+)?", attr.value)
        fractions = [_fraction_value(n) for n in numbers if "/" in n]
        decimals = [float(n) for n in numbers if "/" not in n]
        if not fractions or not decimals:
            continue
        frac_set = {round(f, 6) for f in fractions}
        for dec in decimals:
            snapped = decimal_to_fraction(dec)
            if snapped is None:
                continue
            snap_val = _fraction_value(snapped)
            if snap_val is not None and round(snap_val, 6) not in frac_set and dec != int(dec):
                # decimal present whose exact fractional twin is absent while an
                # unrelated fraction exists — only flag when magnitudes are close
                if any(abs(f - dec) < 12 for f in fractions):
                    problems.append(
                        f"{dec:g} should be written {snapped} to match the fraction form"
                    )
                    labels.append(attr.label)
    if problems:
        return _check(
            "fraction_decimal_consistency",
            "UNSAT",
            labels or ["Size"],
            "; ".join(problems),
        )
    relevant = any("/" in a.value for a in extraction.attributes)
    return _check(
        "fraction_decimal_consistency", "SAT" if relevant else "SKIPPED"
    )


FAMILIES = {
    "Dishwasher": ["electrical"],
    "Heater": ["electrical"],
    "Cut Off Disc": ["mechanical_disc"],
    "Saw Blade": ["mechanical_disc"],
    "Bearing": ["bearing"],
}


def run_physics(extraction: Extraction, family_hint: str | None = None) -> PhysicsReport:
    attrs = _attr_map(extraction)
    checks = [
        check_power_balance(attrs),
        check_diameter_gt_arbor(attrs),
        check_id_lt_od(attrs),
        check_unit_ranges(extraction),
        check_fraction_consistency(extraction),
    ]
    family = family_hint or extraction.item_type
    return PhysicsReport(family=family, checks=checks)
