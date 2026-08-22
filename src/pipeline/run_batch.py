"""Batch orchestration: staged enrichment with checkpoints and corrections."""
import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

from pipeline.classify import classify_rows
from pipeline.cleanse import cleanse_row
from pipeline.config import Settings
from pipeline.confidence import apply_scores, mark_duplicates, triage_score
from pipeline.extract import extract
from pipeline.format.descriptions import (
    DescInput,
    build_invoice_desc,
    build_long_desc,
    build_mobile_desc,
    build_retail_desc,
    build_short_desc,
)
from pipeline.format.emit import write_outputs
from pipeline.llm import LLMClient
from pipeline.models import Attribute, CleanRow, RowResult
from pipeline.physics import run_physics
from pipeline.retrieve import load_cache, retrieve_for_row, save_cache
from pipeline.verify_adversarial import verify

STATE_PATH_DEFAULT = Path("output/state.jsonl")
CORRECTIONS_PATH = Path("output/corrections.jsonl")


def load_input(path: str | Path, limit: int | None = None) -> list[CleanRow]:
    rows = []
    with open(path, newline="") as handle:
        for raw in csv.DictReader(handle):
            rows.append(
                cleanse_row(
                    raw["Mfg_Part_Num"],
                    raw["Part_Desc"],
                    raw["E1_Brand"],
                    raw["Unilog_Brand"],
                    raw["DIB_Brand"],
                    raw["Part_Manuf"],
                )
            )
            if limit and len(rows) >= limit:
                break
    return rows


def load_corrections(path: Path = CORRECTIONS_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        mpn = rec.get("mfg_part_num")
        if mpn:
            out[mpn] = rec
    return out


def apply_corrections(result: RowResult, corrections: dict[str, dict]) -> None:
    rec = corrections.get(result.mfg_part_num)
    if not rec:
        return
    for label, value in (rec.get("attributes") or {}).items():
        match = next(
            (a for a in result.extraction.attributes if a.label.lower() == label.lower()),
            None,
        ) if result.extraction else None
        if match:
            match.value = str(value)
            match.verdict = "CONFIRMED"
            match.review_reason = "verified by human correction"
            match.evidence = None
        elif result.extraction is not None:
            result.extraction.attributes.append(
                Attribute(label=label, value=str(value), verdict="CONFIRMED",
                          review_reason="verified by human correction")
            )
    for column, value in (rec.get("output_row") or {}).items():
        result.output_row[column] = str(value)


def _brand_display(row: CleanRow) -> str | None:
    brand = row.dib_brand or row.unilog_brand or row.e1_brand or row.mfr_name
    return brand


def build_output_row(
    row: CleanRow,
    classification,
    retrieval,
    extraction,
) -> dict[str, str]:
    view = DescInput(
        brand_display=_brand_display(row),
        manuf_name=row.mfr_name,
        mpn=row.mfg_part_num,
        item_type=extraction.item_type if extraction else "Product",
        series=extraction.series if extraction else None,
        feature=(extraction.features[0] if extraction and extraction.features else None),
        attributes=extraction.attributes if extraction else [],
        additional=extraction.additional if extraction else None,
    )
    brand = (
        (extraction.brand if extraction else None)
        or _brand_display(row)
    )
    manufacturer = (
        (extraction.manufacturer if extraction else None)
        or row.mfr_name
        or ""
    )
    out: dict[str, str] = {
        "MANUFACTURER_NAME": manufacturer,
        "BRAND_NAME": brand or "",
        "TRADE_NAME": brand if brand and extraction and extraction.brand else "",
        "MANUFACTURER_PART_NUMBER": row.mfg_part_num,
        "Classpath": classification.classpath if classification else "",
        "UNSPSC": (classification.unspsc or "") if classification else "",
        "MOBILE_DESC": build_mobile_desc(view),
        "INVOICE_DESC": build_invoice_desc(view),
        "SHORT_DESC": build_short_desc(view),
        "LONG_DESC1": build_long_desc(view),
        "RETAIL_DESC": build_retail_desc(view),
        "MARKETING_DESCRIPTION": build_retail_desc(view),
    }
    if retrieval:
        out["MFR URL"] = retrieval.mfr_url or ""
        for i, url in enumerate(retrieval.ref_urls[:5], start=1):
            out[f"Ref URL {i}"] = url
    if extraction:
        if extraction.features:
            out["With"] = f"With {extraction.features[0]}"
        if extraction.certifications:
            out["Standard/Approvals"] = "|".join(extraction.certifications)
        if extraction.application:
            out["Application"] = extraction.application
        if extraction.includes:
            out["Includes"] = extraction.includes
        for i, feat in enumerate(extraction.features[:20], start=1):
            out[f"ITEM_FEATURES_{i}"] = feat
        for i, attr in enumerate(extraction.attributes[:50], start=1):
            out[f"ATTRIBUTE_LABEL {i}"] = attr.label
            out[f"ATTRIBUTE_VALUE {i}"] = attr.value
            out[f"ATTRIBUTE_UOM {i}"] = attr.uom or ""
    return {k: v for k, v in out.items() if v != ""}


async def process_row(
    row: CleanRow,
    llm,
    classification,
    retrieval_cache: dict,
    http=None,
    ddgs_fn=None,
    corrections: dict[str, dict] | None = None,
) -> RowResult:
    result = RowResult(mfg_part_num=row.mfg_part_num, clean=row)
    try:
        retrieval = await retrieve_for_row(row, cache=retrieval_cache, http=http, ddgs_fn=ddgs_fn)
        result.retrieval = retrieval
        extraction = await extract(llm, row, classification, retrieval)
        extraction = await verify(llm, extraction, retrieval)
    except Exception as exc:  # noqa: BLE001 - one bad row must not kill the batch
        result.flags.extend(["NEEDS_REVIEW", f"PIPELINE_ERROR:{type(exc).__name__}"])
        return result
    result.extraction = extraction
    report = run_physics(extraction)
    result.physics = report
    apply_scores(extraction)
    if not report.ok:
        violated = sorted(report.violated_fields)
        for attr in extraction.attributes:
            if attr.label in violated:
                attr.review_reason = (
                    attr.review_reason or f"physics check failed: "
                    + "; ".join(c.reason or c.name for c in report.checks if attr.label in c.fields)
                )
        result.flags.append("PHYSICS_VIOLATION")
        result.flags.append("NEEDS_REVIEW")
    if classification is None:
        result.flags.append("NEEDS_REVIEW")
    result.output_row = build_output_row(row, classification, retrieval, extraction)
    unsupported = [
        a.label for a in extraction.attributes if a.verdict == "UNSUPPORTED"
    ]
    if len(unsupported) >= max(1, len(extraction.attributes)):
        result.flags.append("NEEDS_REVIEW")
    apply_corrections(result, corrections or {})
    result.flags = list(dict.fromkeys(result.flags))
    result.triage_score = triage_score(result)
    return result


class Checkpoint:
    def __init__(self, path: Path, resume: bool):
        self.path = path
        self.done: dict[str, dict] = {}
        if resume and path.exists():
            for line in path.read_text().splitlines():
                try:
                    rec = json.loads(line)
                    self.done[rec["mfg_part_num"]] = rec
                except (json.JSONDecodeError, KeyError):
                    continue

    def has(self, mpn: str) -> bool:
        return mpn in self.done

    def append(self, result: RowResult) -> None:
        self.done[result.mfg_part_num] = {
            "mfg_part_num": result.mfg_part_num,
            "row_result": result.model_dump(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as fh:
            fh.write(json.dumps(self.done[result.mfg_part_num], ensure_ascii=False) + "\n")

    def results(self) -> list[RowResult]:
        return [RowResult(**rec["row_result"]) for rec in self.done.values()]


async def run_batch(
    settings: Settings,
    limit: int | None = None,
    resume: bool = True,
    state_path: Path = STATE_PATH_DEFAULT,
    backend=None,
    http=None,
    ddgs_fn=None,
    concurrency: int = 4,
) -> list[RowResult]:
    rows = load_input(settings.input_csv, limit)
    checkpoint = Checkpoint(state_path, resume)
    pending_rows = [r for r in rows if not checkpoint.has(r.mfg_part_num)]

    retrieval_cache = load_cache()
    corrections = load_corrections()

    if backend is None:
        if not settings.api_key:
            raise SystemExit("GEMINI_API_KEY missing; add it to .env")
    llm = LLMClient(settings, backend=backend)

    classifications: dict = {}
    if pending_rows:
        try:
            classifications = await classify_rows(llm, pending_rows)
        except Exception as exc:  # noqa: BLE001 - degrade, don't die
            print(f"classification failed ({exc}); continuing unclassified",
                  file=sys.stderr)
            for row in pending_rows:
                pass  # rows proceed without classpath; flagged at emit time

    semaphore = asyncio.Semaphore(concurrency)
    counter = {"n": 0}

    async def worker(row: CleanRow) -> RowResult:
        async with semaphore:
            result = await process_row(
                row,
                llm,
                classifications.get(row.mfg_part_num),
                retrieval_cache,
                http=http,
                ddgs_fn=ddgs_fn,
                corrections=corrections,
            )
            checkpoint.append(result)
            counter["n"] += 1
            print(f"[{counter['n']}/{len(pending_rows)}] {row.mfg_part_num} "
                  f"flags={result.flags}", file=sys.stderr)
            return result

    fresh = await asyncio.gather(*(worker(r) for r in pending_rows))
    save_cache(retrieval_cache)

    all_results = checkpoint.results()
    keep = {r.mfg_part_num for r in rows}
    all_results = [r for r in all_results if r.mfg_part_num in keep]
    mark_duplicates(all_results)
    for r in all_results:
        r.triage_score = triage_score(r)
    all_results.sort(key=lambda r: -r.triage_score)
    write_outputs(all_results, settings.output_dir)
    return all_results


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Maal enrichment pipeline")
    parser.add_argument("--input", default=None, help="override input CSV path")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--state", default=str(STATE_PATH_DEFAULT))
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    if args.input:
        settings.input_csv = Path(args.input)
    state_path = Path(args.state)
    results = asyncio.run(
        run_batch(
            settings,
            limit=args.limit,
            resume=not args.no_resume,
            state_path=state_path,
        )
    )
    review = [r for r in results if "NEEDS_REVIEW" in r.flags]
    print(f"done: {len(results)} rows, {len(review)} need review", file=sys.stderr)


if __name__ == "__main__":
    main()
