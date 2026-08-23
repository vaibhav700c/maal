"""Generate honest, offline demo artifacts for the web console.

Takes the first N rows of the sample input CSV and pushes them through the
pipeline's real *deterministic* stages only: cleanse -> a small regex-based
attribute reader (no LLM) -> physics (Z3) -> confidence scoring -> the
description templates -> emit. Classification and retrieval are never
attempted, so they are left as None rather than guessed, and every attribute
is tagged UNVERIFIED with tier-0 ("input-only") evidence quoting the exact
input substring it came from. No network or API calls are made.

Usage:
    python tools/make_demo_data.py [--limit 40] [--input PATH] [--out-dir DIR]
"""
import argparse
import csv
import itertools
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.cleanse import cleanse_row, load_abbrev  # noqa: E402
from pipeline.confidence import mark_duplicates, triage_score  # noqa: E402
from pipeline.format.emit import write_outputs  # noqa: E402
from pipeline.models import Attribute, CleanRow, Evidence, Extraction, RowResult  # noqa: E402
from pipeline.run_batch import finalize_row  # noqa: E402

DEFAULT_INPUT = ROOT / "input" / "Unihack_ Sample Dataset - Input.csv"
DEFAULT_OUT_DIR = ROOT / "output"
DEFAULT_LIMIT = 40

# --- deterministic, regex-only attribute reader -----------------------
# No LLM, no network: every value here is a literal substring of the row's
# own (cleansed) description, so it is only ever as good as what the
# distributor typed in.

NUM = r"(?:\d+-\d+/\d+|\d+/\d+|\.\d+|\d+\.\d+|\d+)"
_UNIT = r'("|mm)?'
DIM3_RE = re.compile(rf"({NUM}){_UNIT}\s*[xX]\s*({NUM}){_UNIT}\s*[xX]\s*({NUM}){_UNIT}")
DIM2_RE = re.compile(rf"({NUM}){_UNIT}\s*[xX]\s*({NUM}){_UNIT}")
DIM1_RE = re.compile(rf'({NUM})(")')
GRIT_RE = re.compile(r"\bP(\d{2,4})\b")
PACK_RE = re.compile(r"\b(\d+)\s*(?:pcs?|pieces?)\b", re.I)
BOX_RE = re.compile(r"\b(\d+)\s*Disc/Box\b", re.I)


def _uom(marker: str | None) -> str | None:
    if marker == '"':
        return "in"
    if marker == "mm":
        return "mm"
    return None


def _evidence(quote: str) -> Evidence:
    return Evidence(quote=quote.strip(), url=None, tier=0.0)  # tier 0: input-only


def _attr(label: str, value: str, uom: str | None, quote: str) -> Attribute:
    return Attribute(label=label, value=value, uom=uom, evidence=_evidence(quote))


def derive_extraction(row: CleanRow) -> Extraction:
    """Read whatever attributes are literally spelled out in the row's own
    description. Nothing here is looked up, inferred from world knowledge,
    or verified against a manufacturer source."""
    desc = row.part_desc
    lower = desc.lower()
    is_disc = "disc" in lower or "blade" in lower
    is_belt = "belt" in lower

    attrs: list[Attribute] = []
    consumed: list[tuple[int, int]] = []

    dim = DIM3_RE.search(desc)
    if dim:
        span = dim.span()
        if is_disc:
            labels = ("Diameter", "Thickness", "Arbor")
        else:
            labels = ("Dimension 1", "Dimension 2", "Dimension 3")
        for label, value, marker in zip(
            labels, (dim.group(1), dim.group(3), dim.group(5)),
            (dim.group(2), dim.group(4), dim.group(6)),
        ):
            attrs.append(_attr(label, value, _uom(marker), dim.group(0)))
        consumed.append(span)
    else:
        dim = DIM2_RE.search(desc)
        if dim:
            span = dim.span()
            if is_disc:
                labels = ("Diameter", "Arbor")
            elif is_belt:
                labels = ("Width", "Length")
            else:
                labels = ("Dimension 1", "Dimension 2")
            for label, value, marker in zip(
                labels, (dim.group(1), dim.group(3)), (dim.group(2), dim.group(4))
            ):
                attrs.append(_attr(label, value, _uom(marker), dim.group(0)))
            consumed.append(span)
        else:
            dim = DIM1_RE.search(desc)
            if dim:
                label = "Diameter" if is_disc else "Size"
                attrs.append(_attr(label, dim.group(1), "in", dim.group(0)))
                consumed.append(dim.span())

    grit = GRIT_RE.search(desc)
    if grit:
        attrs.append(_attr("Grit", grit.group(1), None, grit.group(0)))
        consumed.append(grit.span())

    pack = BOX_RE.search(desc) or PACK_RE.search(desc)
    if pack:
        attrs.append(_attr("Package Quantity", pack.group(1), "each", pack.group(0)))
        consumed.append(pack.span())

    item_type = _strip_spans(desc, row.mfg_part_num, consumed)

    return Extraction(item_type=item_type or "Product", attributes=attrs)


def _strip_spans(desc: str, mpn: str, spans: list[tuple[int, int]]) -> str:
    text = desc
    if text.startswith(mpn):
        spans = spans + [(0, len(mpn))]
    for start, end in sorted(spans, key=lambda s: -s[0]):
        text = text[:start] + " " + text[end:]
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"^[\s,\-]+|[\s,\-]+$", "", text)
    return text.strip()


# --- row pipeline (real deterministic stages, no network/LLM) ---------


def build_demo_rows(input_csv: Path, limit: int) -> list[RowResult]:
    abbrev = load_abbrev()
    results: list[RowResult] = []
    with open(input_csv, newline="", encoding="utf-8") as handle:
        for raw in itertools.islice(csv.DictReader(handle), limit):
            clean = cleanse_row(
                raw["Mfg_Part_Num"], raw["Part_Desc"], raw["E1_Brand"],
                raw["Unilog_Brand"], raw["DIB_Brand"], raw["Part_Manuf"],
                abbrev_table=abbrev,
            )
            extraction = derive_extraction(clean)
            result = finalize_row(clean, None, None, extraction, {})
            result.flags.append("DEMO_INPUT_ONLY")
            result.flags = list(dict.fromkeys(result.flags))
            results.append(result)
    mark_duplicates(results)
    for r in results:
        r.triage_score = triage_score(r)
    results.sort(key=lambda r: -r.triage_score)
    return results


def write_demo_artifacts(input_csv: Path, out_dir: Path, limit: int = DEFAULT_LIMIT) -> list[RowResult]:
    rows = build_demo_rows(input_csv, limit)
    write_outputs(rows, out_dir)
    out_dir = Path(out_dir)
    state_path = out_dir / "state.jsonl"
    with open(state_path, "w", encoding="utf-8") as handle:
        for r in rows:
            handle.write(
                json.dumps({"mfg_part_num": r.mfg_part_num, "row_result": r.model_dump()},
                           ensure_ascii=False) + "\n"
            )
    return rows


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args(argv)

    rows = write_demo_artifacts(Path(args.input), Path(args.out_dir), args.limit)
    print(f"wrote {len(rows)} demo rows to {args.out_dir}", file=sys.stderr)


def copy_reference_files(out_dir: Path) -> None:
    """Ship the Delivery Format + sample input next to the artifacts so the
    hosted /compare view works from the snapshot alone."""
    import shutil

    refs = {
        ROOT / "input" / "Unihack_ Expected Output - Delivery Format.csv": "expected-delivery-format.csv",
        ROOT / "input" / "Unihack_ Sample Dataset - Input.csv": "sample-input.csv",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    for src_file, name in refs.items():
        if src_file.exists():
            shutil.copyfile(src_file, out_dir / name)


if __name__ == "__main__":
    main()  # parses argv internally
    out_dir = Path(__file__).resolve().parents[1] / "output"
    if "--out-dir" in sys.argv:
        out_dir = Path(sys.argv[sys.argv.index("--out-dir") + 1])
    copy_reference_files(out_dir)
    print(f"reference files copied to {out_dir}")
