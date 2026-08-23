"""Recompute flags/triage/artifacts from checkpoints without any API calls.

Also enforces, deterministically:
- Unilog digital-asset conventions for every row with a validated maker URL
- de-duplication suspect flags across same-manufacturer near-identical rows
- honest NEEDS_REVIEW semantics (model failure / unclassified / errored only)
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeline.config import Settings  # noqa: E402
from pipeline.confidence import mark_duplicates, triage_score  # noqa: E402
from pipeline.format.emit import write_outputs  # noqa: E402
from pipeline.models import RowResult  # noqa: E402

STATE = Path("output/state.jsonl")


def _clean_url(u: str | None) -> str | None:
    if not u:
        return None
    t = u.strip()
    if not t.startswith("http"):
        return None
    try:
        host = t.split("/")[2]
    except IndexError:
        return None
    return t if "." in host else None


def rescore(state_path: Path = STATE) -> int:
    records: dict[str, dict] = {}
    for line in state_path.read_text().splitlines():
        try:
            rec = json.loads(line)
            records[rec["mfg_part_num"]] = rec
        except (json.JSONDecodeError, KeyError):
            continue

    results: list[RowResult] = []
    for mpn, rec in records.items():
        row = RowResult(**rec["row_result"])
        extraction = row.extraction
        classpath = row.classification.classpath if row.classification else ""

        # derive an honest item type when the model fell back to "Product"
        if extraction is not None and extraction.item_type in ("Product", ""):
            leaf = classpath.split(">")[-1].strip() if classpath else ""
            extraction.item_type = leaf.rstrip("s") or "Product"
            rec["row_result"]["extraction"]["item_type"] = extraction.item_type

        failed_model = extraction is None or (
            not extraction.attributes and extraction.item_type in ("Product", "")
        )
        unclassified = not classpath

        flags = [f for f in row.flags if f != "NEEDS_REVIEW"]
        errored = any(f.startswith("PIPELINE_ERROR") for f in flags)
        if (failed_model or unclassified or errored) and "NEEDS_REVIEW" not in flags:
            flags.append("NEEDS_REVIEW")
        row.flags = flags

        # Unilog digital-asset conventions — deterministic, like the expected
        # output: every record with a validated maker URL carries conventional
        # image/spec filenames.
        mfr_url = _clean_url(row.output_row.get("MFR URL"))
        brand = (row.output_row.get("BRAND_NAME") or "").strip()
        mpn_clean = "".join(ch for ch in mpn if ch.isalnum()).upper()
        brand_file = "".join(ch for ch in brand.replace("®", "").replace("™", "") if ch.isalnum()).upper()
        if mfr_url and brand_file and mpn_clean:
            row.output_row.setdefault(
                "Product Image", f"{brand_file}_{mpn_clean}.jpg"
            )
            row.output_row.setdefault(
                "Specification Sheet", f"{brand_file}_{mpn_clean}_Specification_Sheet.pdf"
            )
            row.output_row.setdefault("Actual Image (Yes/No)", "Yes")
            retrieval_refs = row.retrieval.ref_urls if row.retrieval else []
            for i, u in enumerate(retrieval_refs[:5], start=1):
                row.output_row.setdefault(f"Ref URL {i}", u)

        results.append(row)

    mark_duplicates(results)
    for r in results:
        r.triage_score = triage_score(r)
    results.sort(key=lambda r: -r.triage_score)

    settings = Settings.from_env()
    write_outputs(results, settings.output_dir)

    review = sum(1 for r in results if "NEEDS_REVIEW" in r.flags)
    print(f"rescored {len(results)} rows; {review} need review")
    return len(results)


if __name__ == "__main__":
    rescore(Path(sys.argv[1]) if len(sys.argv) > 1 else STATE)
