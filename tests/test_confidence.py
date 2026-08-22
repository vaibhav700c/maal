from pipeline.confidence import (
    apply_scores,
    mark_duplicates,
    score_attribute,
    triage_score,
)
from pipeline.models import (
    Attribute,
    CleanRow,
    Evidence,
    Extraction,
    RowResult,
)


def test_score_matrix_boundaries():
    confirmed_mfr = Attribute(
        label="X", value="1",
        evidence=Evidence(quote="q", url="https://freud.com", tier=1.0),
        verdict="CONFIRMED",
    )
    assert score_attribute(confirmed_mfr) == 1.0

    input_only = Attribute(label="Y", value="2", verdict="UNVERIFIED")
    assert score_attribute(input_only) == round(0.35 * 0.6, 3)

    refuted = Attribute(
        label="Z", value="3",
        evidence=Evidence(quote="q", url=None, tier=0.0),
        verdict="REFUTED",
    )
    assert score_attribute(refuted) == 0.0


def test_apply_scores_sets_confidence():
    extraction = Extraction(
        item_type="Disc",
        attributes=[
            Attribute(
                label="Diameter",
                value="14",
                uom="in",
                evidence=Evidence(quote="q", url="https://freud.com/x.pdf", tier=0.9),
                verdict="CONFIRMED",
            ),
            Attribute(label="Grit", value="80"),
        ],
    )
    apply_scores(extraction)
    assert extraction.attributes[0].confidence == 0.75
    assert extraction.attributes[1].confidence == round(0.35 * 0.6, 3)


def _row(mpn: str, desc: str, output_row=None, flags=None) -> RowResult:
    clean = CleanRow(mfg_part_num=mpn, part_desc=desc, mfr_name="Freud Inc", mfr_code="2435")
    return RowResult(
        mfg_part_num=mpn,
        clean=clean,
        output_row=output_row or {},
        flags=list(flags or []),
    )


def test_triage_orders_problem_rows_first():
    healthy = _row("H1", "good disc", output_row={f: "v" for f in [
        "MANUFACTURER_NAME", "BRAND_NAME", "MANUFACTURER_PART_NUMBER", "Classpath",
        "MOBILE_DESC", "INVOICE_DESC", "SHORT_DESC", "LONG_DESC1"]})
    healthy.extraction = Extraction(item_type="d", attributes=[
        Attribute(label="A", value="1", evidence=Evidence(quote="q", url="u", tier=1.0), verdict="CONFIRMED")])
    broken = _row("B1", "bad disc", flags=["PHYSICS_VIOLATION"])
    assert triage_score(broken) > triage_score(healthy)


def test_dedup_groups_similar_same_manufacturer():
    rows = [
        _row("M1", '49-94-0063 Milw 6"x.045"x7/8" Metal Cut Off Disc'),
        _row("M2", '49-94-0023 Milw 6"x.045"x7/8" Metal Cut Off Disc'),
        _row("M3", "2535-20 Milw 3in Orbit Sander M12"),
    ]
    mark_duplicates(rows)
    flagged = {r.mfg_part_num for r in rows if "DUPLICATE_SUSPECT" in r.flags}
    assert flagged == {"M1", "M2"}
