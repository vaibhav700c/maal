"""Batch orchestration: staged enrichment with checkpoints and corrections.

Free-tier strategy: rows are processed in chunks sharing one batched extract
call and one batched audit call; rows without retrieved evidence skip the
audit entirely. On daily-quota exhaustion the runner stops cleanly so a
rerun resumes where it left off.
"""
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
from pipeline.extract import extract_many
from pipeline.format.descriptions import (
    DescInput,
    build_invoice_desc,
    build_long_desc,
    build_mobile_desc,
    build_retail_desc,
    build_short_desc,
)
from pipeline.format.emit import write_outputs
from pipeline.llm import LLMClient, LLMError
from pipeline.models import (
    Attribute,
    CleanRow,
    Extraction,
    RetrievalResult,
    RowResult,
)
from pipeline.physics import run_physics
from pipeline.retrieve import (
    load_cache,
    retrieve_by_brand,
    retrieve_for_row,
    save_cache,
)
from pipeline.verify_adversarial import verify_many

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
    return row.dib_brand or row.unilog_brand or row.e1_brand or row.mfr_name


def build_output_row(
    row: CleanRow,
    classification,
    retrieval,
    extraction,
) -> dict[str, str]:
    brand = (
        (extraction.brand if extraction else None)
        or _brand_display(row)
    )
    if brand and extraction and extraction.brand and "\u00ae" not in brand:
        brand = f"{brand}\u00ae"  # house style: resolved brands carry the mark
    manufacturer = (
        (extraction.manufacturer if extraction else None)
        or row.mfr_name
        or ""
    )
    view = DescInput(
        brand_display=brand or manufacturer or None,
        manuf_name=manufacturer or None,
        mpn=row.mfg_part_num,
        item_type=extraction.item_type if extraction else "Product",
        series=extraction.series if extraction else None,
        feature=(extraction.features[0] if extraction and extraction.features else None),
        attributes=extraction.attributes if extraction else [],
        additional=extraction.additional if extraction else None,
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
        out["MFR URL"] = (
            retrieval.product_url or retrieval.mfr_url or ""
        )
        for i, url in enumerate(retrieval.ref_urls[:5], start=1):
            out[f"Ref URL {i}"] = url

    # Unilog asset conventions: named images + specification sheet follow the
    # BRAND_MPN pattern once the maker's own page for this part is confirmed.
    brand_source = (extraction.brand if extraction else None) or _brand_display(row)
    brand_domain_confirmed = bool(
        retrieval and "BRAND_DOMAIN_LOOKUP" in (retrieval.flags or [])
    )
    if brand_source and retrieval and (
        retrieval.product_url or retrieval.ref_urls or brand_domain_confirmed
    ):
        import re as _re

        brand_file = _re.sub(r"[^A-Za-z0-9]+", "", brand_source).upper()
        mpn_file = _re.sub(r"[^A-Za-z0-9]+", "", row.mfg_part_num).upper()
        out["Product Image"] = f"{brand_file}_{mpn_file}.jpg"
        out["Alternate Image 1"] = f"{brand_file}_{mpn_file}_1.jpg"
        out["Alternate Image 2"] = f"{brand_file}_{mpn_file}_2.jpg"
        out["Alternate Image 3"] = f"{brand_file}_{mpn_file}_3.jpg"
        out["Alternate Image 4"] = f"{brand_file}_{mpn_file}_4.jpg"
        out["Specification Sheet"] = f"{brand_file}_{mpn_file}_Specification_Sheet.pdf"
        out["Actual Image (Yes/No)"] = "Yes"
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
        # dedicated delivery-format columns mapped from well-known attributes
        DIM_MAP = {
            "Length": ("LENGTH", "LENGTH_UOM"),
            "Height": ("HEIGHT", "HEIGHT_UOM"),
            "Width": ("WIDTH", "WIDTH_UOM"),
            "Weight": ("WEIGHT", "WEIGHT_UOM"),
        }
        for attr in extraction.attributes:
            label_low = attr.label.lower()
            if label_low == "warranty":
                out.setdefault("Warranty", attr.value)
                out.setdefault("Warranty Information", attr.value)
            elif label_low == "country of origin":
                out.setdefault("Country Of Origin", attr.value)
            elif label_low == "upc" and attr.value.isdigit():
                out.setdefault("UPC", attr.value)
            elif label_low in ("package quantity", "pack quantity") and attr.value.isdigit():
                out.setdefault("Selling Qty", attr.value)
                out.setdefault("Selling UOM", "each")
            elif label_low in DIM_MAP:
                col, uom_col = DIM_MAP[label_low]
                try:
                    out.setdefault(col, f"{float(attr.value):g}")
                    out.setdefault(uom_col, (attr.uom or "").strip())
                except ValueError:
                    pass
    return {k: v for k, v in out.items() if v != ""}


def finalize_row(
    row: CleanRow,
    classification,
    retrieval: RetrievalResult | None,
    extraction: Extraction | None,
    corrections: dict[str, dict],
    error: str | None = None,
) -> RowResult:
    result = RowResult(mfg_part_num=row.mfg_part_num, clean=row)
    if error is not None:
        result.flags.extend(["NEEDS_REVIEW", f"PIPELINE_ERROR:{error}"])
        return result
    result.retrieval = retrieval
    result.extraction = extraction
    result.classification = classification
    if extraction.item_type in ("Product", "") and classification:
        leaf = classification.classpath.split(">")[-1].strip()
        extraction.item_type = leaf.rstrip("s") or extraction.item_type or "Product"
        if not extraction.attributes:
            extraction.attributes.append(
                Attribute(label="Product Type", value=extraction.item_type,
                          verdict="UNVERIFIED")
            )
    report = run_physics(extraction)
    result.physics = report
    apply_scores(extraction)
    if not report.ok:
        violated = sorted(report.violated_fields)
        for attr in extraction.attributes:
            if attr.label in violated and not attr.review_reason:
                attr.review_reason = "; ".join(
                    c.reason or c.name for c in report.checks if attr.label in c.fields
                )
        result.flags.extend(["PHYSICS_VIOLATION", "NEEDS_REVIEW"])
    if classification is None:
        result.flags.append("NEEDS_REVIEW")
    result.output_row = build_output_row(row, classification, retrieval, extraction)
    unsupported = [a for a in extraction.attributes if a.verdict == "UNSUPPORTED"]
    if extraction.attributes and len(unsupported) >= len(extraction.attributes):
        result.flags.append("NEEDS_REVIEW")
    apply_corrections(result, corrections)
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


def _chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _is_quota_dead(exc: BaseException) -> bool:
    text = str(exc)
    return "all models failed" in text or isinstance(exc, LLMError) and "daily quota" in text.lower()


async def run_batch(
    settings: Settings,
    limit: int | None = None,
    resume: bool = True,
    state_path: Path = STATE_PATH_DEFAULT,
    backend=None,
    http=None,
    ddgs_fn=None,
    concurrency: int = 6,
    extraction_batch: int | None = None,
) -> list[RowResult]:
    rows = load_input(settings.input_csv, limit)
    checkpoint = Checkpoint(state_path, resume)
    pending_rows = [r for r in rows if not checkpoint.has(r.mfg_part_num)]

    retrieval_cache = load_cache()
    corrections = load_corrections()
    batch_size = extraction_batch or int(__import__("os").environ.get("EXTRACT_BATCH", "8"))

    if backend is None and not settings.api_key:
        raise SystemExit("GEMINI_API_KEY missing; add it to .env")
    llm = LLMClient(settings, backend=backend)

    classifications: dict = {}
    if pending_rows:
        try:
            classifications = await classify_rows(llm, pending_rows)
        except LLMError as exc:
            if _is_quota_dead(exc):
                print("daily quota exhausted before classification; rerun later",
                      file=sys.stderr)
                return checkpoint.results()
            print(f"classification failed ({exc}); continuing unclassified",
                  file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"classification failed ({exc}); continuing unclassified",
                  file=sys.stderr)

    done_count = 0
    quota_dead = False
    for rows_chunk in _chunked(pending_rows, batch_size):
        # 1) retrieval — pure HTTP, fully concurrent, never fatal
        outcomes = await asyncio.gather(
            *(
                retrieve_for_row(r, cache=retrieval_cache, http=http, ddgs_fn=ddgs_fn)
                for r in rows_chunk
            ),
            return_exceptions=True,
        )
        retrievals: list[RetrievalResult | None] = []
        for r, outcome in zip(rows_chunk, outcomes):
            if isinstance(outcome, RetrievalResult):
                retrievals.append(outcome)
            else:
                retrievals.append(RetrievalResult(flags=["NO_MFR_DOMAIN"]))

        # 2) batched extraction — one call per chunk
        try:
            extractions = await extract_many(
                llm,
                [
                    (r, classifications.get(r.mfg_part_num), ret)
                    for r, ret in zip(rows_chunk, retrievals)
                ],
                batch=batch_size,
            )
        except LLMError as exc:
            if _is_quota_dead(exc):
                quota_dead = True
                break
            raise

        # 2b) brand-based second-pass retrieval: the supplier name often is a
        # distributor; once the true brand is known, look on ITS domain.
        async def llm_brand_domain(brand: str) -> str | None:
            """One cached LLM call per brand: its official website domain."""
            import re as _re

            key = f"domain::{brand}"
            if retrieval_cache.get(key):
                return retrieval_cache[key] or None
            try:
                text = await llm.generate(
                    f"Reply with ONLY the official website domain of the brand "
                    f"{brand}, in the form example.com — no scheme, no path, "
                    f"no explanation."
                )
                match = _re.search(r"([a-z0-9-]+\.[a-z0-9.-]+)", text.strip(), _re.I)
                domain = match.group(1).lower().rstrip(".") if match else ""
            except Exception:  # noqa: BLE001
                domain = ""
            retrieval_cache[key] = domain
            return domain or None

        async def upgrade(row: CleanRow, ext: Extraction | None, ret):
            if ext is None or not ext.brand:
                return ret
            brand_tokens = [
                t for t in __import__("re").split(r"[^a-z0-9]+", ext.brand.lower()) if len(t) >= 4
            ]
            host = (ret.product_url or ret.mfr_url or "").split("/")[2] if (
                ret and (ret.product_url or ret.mfr_url)
            ) else ""
            host_ok = any(t in host.lower() for t in brand_tokens)
            # wrong-domain hit (e.g. distributor slug) or no evidence at all
            # -> try the brand's own domain
            if ret and ret.snippets and host_ok:
                return ret
            try:
                await llm_brand_domain(ext.brand)
                upgraded = await retrieve_by_brand(
                    ext.brand, row, cache=retrieval_cache, http=http, ddgs_fn=ddgs_fn
                )
            except Exception:  # noqa: BLE001 - upgrade is opportunistic
                return ret
            upgraded_host = (upgraded.mfr_url or "").split("/")[2] if upgraded.mfr_url else ""
            def _registered(host: str, tokens: list[str]) -> bool:
                core = ".".join(host.lower().split(".")[-2:])
                return any(t in core for t in tokens)

            brand_correct = (
                _registered(upgraded_host, brand_tokens) if upgraded_host else False
            )
            if (
                upgraded.product_url
                or upgraded.ref_urls
                or upgraded.snippets
                or brand_correct
            ):
                upgraded.flags.append("BRAND_DOMAIN_LOOKUP")
                return upgraded
            return ret

        upgrades = await asyncio.gather(
            *(
                upgrade(r, e, rt)
                for r, e, rt in zip(rows_chunk, extractions, retrievals)
            ),
            return_exceptions=True,
        )
        retrievals = [
            u if isinstance(u, RetrievalResult) else old
            for u, old in zip(upgrades, retrievals)
        ]

        # 3) batched adversarial audit — only rows with evidence consume calls
        try:
            extractions = await verify_many(
                llm, list(zip(extractions, retrievals)), batch=batch_size
            )
        except LLMError as exc:
            if _is_quota_dead(exc):
                quota_dead = True
                break
            raise

        # 4) deterministic finalize + checkpoint
        for row, ret, ext in zip(rows_chunk, retrievals, extractions):
            error = None if ret is not None else "RETRIEVAL_FAILED"
            try:
                result = finalize_row(row, classifications.get(row.mfg_part_num), ret,
                                      ext, corrections, error=error)
            except Exception as exc:  # noqa: BLE001 - one bad row never kills a batch
                result = finalize_row(row, classifications.get(row.mfg_part_num),
                                      ret, None, corrections,
                                      error=f"{type(exc).__name__}")
                result.flags.append("NEEDS_REVIEW")
            checkpoint.append(result)
            done_count += 1
            print(f"[{done_count}/{len(pending_rows)}] {row.mfg_part_num} "
                  f"flags={result.flags}", file=sys.stderr)

    save_cache(retrieval_cache)

    # rebuild from the FULL checkpoint file so a top-up run never erases
    # previously enriched rows from the shared artifacts
    all_results = Checkpoint(state_path, resume=True).results()
    mark_duplicates(all_results)
    for r in all_results:
        r.triage_score = triage_score(r)
    all_results.sort(key=lambda r: -r.triage_score)
    write_outputs(all_results, settings.output_dir)
    if quota_dead:
        remaining = len(pending_rows) - sum(1 for r in pending_rows if checkpoint.has(r.mfg_part_num))
        print(f"daily quota exhausted; ~{max(0, remaining)} rows remain, "
              "rerun tomorrow or after billing is enabled", file=sys.stderr)
    return all_results


async def classify_backfill(settings: Settings, state_path: Path, backend=None) -> None:
    """Re-run classification ONLY for checkpointed rows missing a classpath."""
    checkpoint = Checkpoint(state_path, resume=True)
    targets = [
        r.clean for r in checkpoint.results()
        if r.classification is None or not r.classification.classpath
    ]
    if not targets:
        print("all rows already classified", file=sys.stderr)
        return
    llm = LLMClient(settings, backend=backend)
    fresh = await classify_rows(llm, targets)
    # rewrite state with patched classifications
    lines_out = []
    for line in state_path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        mpn = rec.get("mfg_part_num")
        cls = fresh.get(mpn)
        if cls is not None:
            rec["row_result"]["classification"] = cls.model_dump()
            flags = [f for f in rec["row_result"].get("flags", [])]
            lines_out.append(json.dumps(rec, ensure_ascii=False))
        else:
            lines_out.append(line)
    state_path.write_text("\n".join(lines_out) + "\n")
    print(f"classified {len(fresh)}/{len(targets)} rows", file=sys.stderr)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Maal enrichment pipeline")
    parser.add_argument("--input", default=None, help="override input CSV path")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--classify-only", action="store_true",
                        help="backfill missing classifications in checkpoints, no extraction")
    parser.add_argument("--state", default=str(STATE_PATH_DEFAULT))
    parser.add_argument("--out-dir", default=None,
                        help="write artifacts here instead of the shared output dir")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    if args.input:
        settings.input_csv = Path(args.input)
    if args.out_dir:
        settings.output_dir = Path(args.out_dir)
    state_path = Path(args.state)

    if args.classify_only:
        asyncio.run(classify_backfill(settings, state_path, backend=None))
        return

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
