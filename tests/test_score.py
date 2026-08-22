import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.score import check_headers, compliance_report, replay_diff, row_checks  # noqa: E402


def _write(path, rows):
    headers_path = Path(__file__).resolve().parents[1] / "input" / "Unihack_ Expected Output - Delivery Format.csv"
    with open(headers_path, newline="") as f:
        header = next(csv.reader(f))
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({h: r.get(h, "") for h in header})


def test_row_checks_catch_violations():
    bad = {"INVOICE_DESC": "D" * 50, "MOBILE_DESC": "too short",
           "LONG_DESC1": "operates at 120VAC and 15AMP"}
    checks = row_checks(bad)
    assert checks["invoice_length"] is False
    assert checks["mobile_length"] is False
    assert checks["long_uom_spacing"] is False

    good = {"INVOICE_DESC": "DISHWASHER LEG 5 SST 120V 15A", "MOBILE_DESC": "x" * 70,
            "LONG_DESC1": "120 V, 15 A, 24 in W", "MANUFACTURER_PART_NUMBER": "PD1",
            "SHORT_DESC": "PD1 Dishwasher"}
    checks = row_checks(good)
    assert all(checks[r] for r in ("invoice_length", "invoice_caps", "mobile_length",
                                   "long_uom_spacing", "short_contains_mpn"))


def test_compliance_report_and_header_fidelity(tmp_path):
    out = tmp_path / "gen.csv"
    _write(out, [
        {"INVOICE_DESC": "OK DISC 5IN", "MANUFACTURER_PART_NUMBER": "G1",
         "MOBILE_DESC": "m" * 65, "LONG_DESC1": "runs 120 V"},
        {"INVOICE_DESC": "x" * 45, "MANUFACTURER_PART_NUMBER": "B1",
         "MOBILE_DESC": "short", "SHORT_DESC": ""},
    ])
    report = compliance_report(out)
    assert report["header_fidelity"] is True
    assert report["rows"] == 2
    assert report["rule_pass_rates"]["invoice_length"] == 0.5
    assert set(report["rows_failing"]) >= {"B1"}


def test_replay_diff_detects_seeded_error(tmp_path):
    out = tmp_path / "gen.csv"
    _write(out, [{
        "MANUFACTURER_PART_NUMBER": "PDSH4816AF",
        "Classpath": "Wrong>Taxonomy>Here",
        "BRAND_NAME": "FRIGIDAIRE®",
    }])
    diffs = replay_diff(
        out,
        fields=["Classpath", "BRAND_NAME"],
    )
    classpath = next(d for d in diffs if d["field"] == "Classpath")
    assert classpath["expected"].startswith("Appliances & Consumer Electronics")
    assert classpath["match"] < 0.3
