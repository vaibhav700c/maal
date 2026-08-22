"""Recompute flags/triage/artifacts from checkpoints without any API calls."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeline.config import Settings  # noqa: E402
from pipeline.confidence import triage_score  # noqa: E402
from pipeline.format.emit import write_outputs  # noqa: E402
from pipeline.models import RowResult  # noqa: E402

STATE = Path("output/state.jsonl")


def rescore(state_path: Path = STATE) -> int:
    records = {}
    for line in state_path.read_text().splitlines():
        try:
            rec = json.loads(line)
            records[rec["mfg_part_num"]] = rec
        except (json.JSONDecodeError, KeyError):
            continue

    results = []
    for mpn, rec in records.items():
        row = RowResult(**rec["row_result"])
        flags = [f for f in row.flags if f != "NEEDS_REVIEW"]
        extraction = row.extraction
        classpath = row.classification.classpath if row.classification else ""
        if extraction is not None and extraction.item_type in ("Product", ""):
            # derive an honest item type from the taxonomy leaf
            leaf = classpath.split(">")[-1].strip() if classpath else ""
            extraction.item_type = leaf.rstrip("s") or "Product"
            rec["row_result"]["extraction"]["item_type"] = extraction.item_type
        failed_model = extraction is None or (
            not extraction.attributes and extraction.item_type in ("Product", "")
        )
        unclassified = not classpath
        errored = any(f.startswith("PIPELINE_ERROR") for f in flags)
        if (failed_model or unclassified or errored) and "NEEDS_REVIEW" not in flags:
            flags.append("NEEDS_REVIEW")
        row.flags = flags
        row.triage_score = triage_score(row)
        results.append(row)

    settings = Settings.from_env()
    write_outputs(sorted(results, key=lambda r: -r.triage_score), settings.output_dir)
    review = sum(1 for r in results if "NEEDS_REVIEW" in r.flags)
    print(f"rescored {len(results)} rows; {review} need review")
    return len(results)


if __name__ == "__main__":
    rescore(Path(sys.argv[1]) if len(sys.argv) > 1 else STATE)
