"""Format-compliance scoring for generated Delivery Format output."""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CSV = ROOT / "input" / "Unihack_ Expected Output - Delivery Format.csv"

INVOICE_LIMIT = 40
UOM_GLUED_RE = re.compile(r"\d[A-Za-z]{2,}")  # e.g. '120VAC' outside INVOICE_DESC
FRACTION_RE = re.compile(r"\b\d+-\d+/\d+\b|\b\d+/\d+\b")


def load_rows(path: str | Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def check_headers(headers: list[str]) -> bool:
    expected, _ = load_rows(EXPECTED_CSV)
    return headers == expected


def row_checks(row: dict) -> dict[str, str | bool]:
    """Returns per-rule pass/fail; rules evaluated only when field populated."""
    out: dict[str, str | bool] = {}
    invoice = (row.get("INVOICE_DESC") or "").strip()
    if invoice:
        out["invoice_length"] = len(invoice) <= INVOICE_LIMIT
        out["invoice_caps"] = invoice == invoice.upper()
    mobile = (row.get("MOBILE_DESC") or "").strip()
    if mobile:
        out["mobile_length"] = 40 <= len(mobile) <= 90
    long_desc = (row.get("LONG_DESC1") or "").strip()
    short_desc = (row.get("SHORT_DESC") or "").strip()
    if long_desc:
        glued = [m.group(0) for m in UOM_GLUED_RE.finditer(long_desc)]
        out["long_uom_spacing"] = not glued
    if short_desc:
        out["short_populated_with_mpn_like_token"] = bool(short_desc)
    for key, value in row.items():
        if key.startswith("ATTRIBUTE_VALUE") and value and "/" in value:
            for token in value.split():
                if re.fullmatch(r"\d+/\d+", token) and not FRACTION_RE.search(value):
                    out.setdefault("fraction_form", False)
                elif re.fullmatch(r"\d+-\d+/\d+|\d+/\d+", token):
                    out.setdefault("fraction_form", True)
    mpn = (row.get("MANUFACTURER_PART_NUMBER") or "").strip()
    if mpn and short_desc:
        out["short_contains_mpn"] = mpn.lower() in short_desc.lower()
    return {k: v for k, v in out.items() if isinstance(v, bool)}


def compliance_report(path: str | Path) -> dict:
    headers, rows = load_rows(path)
    header_ok = check_headers(headers)
    rule_counts: dict[str, int] = {}
    rule_totals: dict[str, int] = {}
    failures_by_row: dict[str, list[str]] = {}
    for row in rows:
        mpn = row.get("MANUFACTURER_PART_NUMber", row.get("MANUFACTURER_PART_NUMBER", ""))
        checks = row_checks(row)
        failed = []
        for rule, ok in checks.items():
            rule_totals[rule] = rule_totals.get(rule, 0) + 1
            if ok:
                rule_counts[rule] = rule_counts.get(rule, 0) + 1
            else:
                failed.append(rule)
        if failed:
            failures_by_row[mpn] = failed
    rates = {
        rule: round(rule_counts.get(rule, 0) / total, 4)
        for rule, total in sorted(rule_totals.items())
    }
    overall = (
        round(sum(rule_counts.values()) / max(1, sum(rule_totals.values())), 4)
        if rule_totals
        else 0.0
    )
    return {
        "file": str(path),
        "header_fidelity": header_ok,
        "rows": len(rows),
        "rule_pass_rates": rates,
        "overall_format_compliance": overall,
        "rows_failing": failures_by_row,
    }


def replay_diff(generated_path: str | Path, fields: list[str]) -> list[dict]:
    """Compare generated rows for the two labelled example MPNs vs ground truth."""
    _, truth_rows = load_rows(EXPECTED_CSV)
    by_mpn = {}
    for r in truth_rows:
        mpn = r.get("MANUFACTURER_PART_NUMBER", "")
        if mpn:
            by_mpn[mpn] = r
    _, gen_rows = load_rows(generated_path)
    diffs = []
    for gen in gen_rows:
        mpn = gen.get("MANUFACTURER_PART_NUMBER", "")
        if mpn not in by_mpn:
            continue
        for field in fields:
            want = (by_mpn[mpn].get(field) or "").strip()
            got = (gen.get(field) or "").strip()
            if want and want != got:
                diffs.append({
                    "mpn": mpn, "field": field,
                    "expected": want[:160], "generated": got[:160],
                    "match": _similarity(want, got),
                })
    return diffs


def _similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher

    return round(SequenceMatcher(None, a.lower(), b.lower()).ratio(), 3)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else ROOT / "output" / "result.csv"
    report = compliance_report(target)
    print(json.dumps(report, indent=2)[:4000])
