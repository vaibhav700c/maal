import csv
import json

import pipeline.run_batch as rb
from pipeline.config import Settings
from pipeline.models import Attribute, CleanRow
from pipeline.llm import StubBackend
from pipeline.models import RetrievalResult
from pathlib import Path


def _settings(tmp_path: Path) -> Settings:
    s = Settings(
        api_key="test",
        model="stub",
        rpm=6000,
        input_csv=tmp_path / "in.csv",
        expected_headers_csv=tmp_path / "expected.csv",
        output_dir=tmp_path / "out",
    )
    return s


def write_input(tmp_path, rows):
    path = tmp_path / "in.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf"])
        w.writeheader()
        for mpn, desc in rows:
            w.writerow({
                "Mfg_Part_Num": mpn, "Part_Desc": desc,
                "E1_Brand": "-- Unbranded --", "Unilog_Brand": "-- No Unilog Brand --",
                "DIB_Brand": "-- No DIB Brand --", "Part_Manuf": "Freud Inc (2435)"})
    return path


def stub_backend():
    # classification call + per-row extract + verify (order-agnostic payloads)
    responses = [
        [{"index": 0, "classpath": "Tools>Abrasives>Cut Off Discs", "unspsc": "23171503"},
         {"index": 1, "classpath": "Tools>Abrasives>Cut Off Discs", "unspsc": "23171503"},
         {"index": 2, "classpath": "Tools>Sanders>Orbit Sanders", "unspsc": None}],
    ]
    for _ in range(3):
        responses.append({
            "item_type": "Cut Off Disc",
            "series": None,
            "attributes": [
                {"label": "Diameter", "value": "6", "uom": "in", "quote": "6 inch disc"},
            ],
            "features": ["Metal cutting"],
            "certifications": [],
            "application": None,
            "includes": None,
            "additional": None,
        })
        responses.append([])
    return StubBackend(responses)


async def test_run_batch_end_to_end(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    write_input(tmp_path, [
        ("A1", 'A1 Disc 14"x1/8"x1" Metal Cut Off'),
        ("B2", 'B2 Disc 14"x1/8"x1" Metal Cut Off'),   # near-dup of A1
        ("C3", "C3 Sander M12"),
    ])
    monkeypatch.chdir(tmp_path)
    state = tmp_path / "state.jsonl"

    async def fake_retrieve(row, cache=None, http=None, ddgs_fn=None):
        return RetrievalResult(flags=["NO_MFR_DOMAIN"])

    monkeypatch.setattr(rb, "retrieve_for_row", fake_retrieve)

    results = await rb.run_batch(
        settings, limit=3, resume=True, state_path=state,
        backend=stub_backend(), http=object(), ddgs_fn=lambda q: [],
    )

    assert len(results) == 3
    dup = [r for r in results if "DUPLICATE_SUSPECT" in r.flags]
    assert {r.mfg_part_num for r in dup} >= {"A1", "B2"}
    csv_path = settings.output_dir / "result.csv"
    with open(csv_path, newline="") as f:
        header = next(csv.reader(f))
        body = list(csv.reader(f))
    assert len(header) == 252 and len(body) == 3
    sidecar_lines = (settings.output_dir / "sidecar.jsonl").read_text().strip().splitlines()
    assert len(sidecar_lines) == 3
    rec = json.loads(sidecar_lines[0])
    assert rec["mfg_part_num"] in {"A1", "B2", "C3"}
    # checkpoint resume: rerun loads from state, no new backend calls needed
    empty_stub = StubBackend([])  # would fail loudly if LLM were called again
    results2 = await rb.run_batch(
        settings, limit=3, resume=True, state_path=state,
        backend=empty_stub, http=object(), ddgs_fn=lambda q: [],
    )
    assert len(results2) == 3


async def test_corrections_applied(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    write_input(tmp_path, [("Z9", "Z9 Disc")])
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    corr = tmp_path / "output" / "corrections.jsonl"
    corr.write_text(json.dumps({
        "mfg_part_num": "Z9",
        "attributes": {"Max RPM": "6600"},
        "output_row": {"SHORT_DESC": "Human approved title"},
    }) + "\n")

    async def fake_retrieve(row, cache=None, http=None, ddgs_fn=None):
        return RetrievalResult(flags=["NO_MFR_DOMAIN"])

    monkeypatch.setattr(rb, "retrieve_for_row", fake_retrieve)

    responses = [[{"index": 0, "classpath": "T>A>C", "unspsc": None}]]
    responses.append({"item_type": "Disc", "attributes": [], "features": []})
    responses.append([])

    results = await rb.run_batch(
        settings, limit=1, resume=False, state_path=tmp_path / "s.jsonl",
        backend=StubBackend(responses), http=object(),
    )
    row = results[0]
    rpm = next(a for a in row.extraction.attributes if a.label == "Max RPM")
    assert rpm.value == "6600" and rpm.verdict == "CONFIRMED"
    assert row.output_row["SHORT_DESC"] == "Human approved title"


def test_brand_from_extraction_overrides_supplier():
    from pipeline.models import Attribute, Extraction
    from pipeline.run_batch import build_output_row

    clean = CleanRow(mfg_part_num="M1", part_desc="3M disc", mfr_name="Jam Industrial Supply LLC")
    extraction = Extraction(
        item_type="Cut Off Disc",
        brand="3M",
        manufacturer="3M Company",
        attributes=[Attribute(label="Grit", value="150")],
    )
    out = build_output_row(clean, None, None, extraction)
    assert out["BRAND_NAME"] == "3M\u00ae"  # house style: resolved brands carry the mark
    assert out["MANUFACTURER_NAME"] == "3M Company"
    assert out["TRADE_NAME"].startswith("3M")


def test_mobile_desc_dedupes_head_and_pads():
    from pipeline.format.descriptions import DescInput, build_mobile_desc

    view = DescInput(
        brand_display="Acme", manuf_name="Acme", mpn="X1", item_type="Disc",
        series=None, feature=None,
        attributes=[Attribute(label="Diameter", value="14", uom="in")],
    )
    out = build_mobile_desc(view)
    assert "Acme Acme" not in out


async def test_topup_run_preserves_full_catalog_artifacts(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.chdir(tmp_path)
    write_input(tmp_path, [("A1", 'A1 Disc 14"x1" Metal'), ("B2", "B2 Sander M12")])
    state = tmp_path / "state.jsonl"

    async def fake_retrieve(row, cache=None, http=None, ddgs_fn=None):
        return RetrievalResult(flags=["NO_MFR_DOMAIN"])

    monkeypatch.setattr(rb, "retrieve_for_row", fake_retrieve)
    responses = [[{"index": i, "classpath": "T>A>C", "unspsc": None} for i in range(2)]]
    for _ in range(2):
        responses.append({"item_type": "Disc", "attributes": [
            {"label": "Diameter", "value": "14", "uom": "in", "quote": "q"}]})
        responses.append([])
    await rb.run_batch(settings, limit=2, resume=False, state_path=state,
                       backend=StubBackend(responses), http=object())

    # second run adds one NEW row; artifact must contain 1 + 2 = 3 rows
    write_input_rows = [("C3", "C3 Disc 7in")]
    with open(settings.input_csv, "w") as f:
        import csv as _csv
        w = _csv.writer(f)
        w.writerow(["Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf"])
        for mpn, desc in write_input_rows:
            w.writerow([mpn, desc, "-- Unbranded --", "-- No Unilog Brand --", "-- No DIB Brand --", "Freud Inc"])

    responses2 = [[{"index": 0, "classpath": "T>A>C", "unspsc": None}]]
    responses2.append({"item_type": "Disc", "attributes": []})
    responses2.append([])
    await rb.run_batch(settings, limit=1, resume=False, state_path=state,
                       backend=StubBackend(responses2), http=object())

    import csv as _csv
    with open(settings.output_dir / "result.csv", newline="") as f:
        body = list(_csv.reader(f))[1:]
    assert len(body) == 3  # A1 + B2 from history + C3 new


def test_resolve_manufacturers_static_map_no_llm_call(tmp_path, monkeypatch):
    from pipeline import run_batch as r
    monkeypatch.setattr(r, "MFR_CACHE_PATH", tmp_path / "mfr.json")
    backend = StubBackend([])
    calls = []
    original = backend.complete
    async def spy(prompt, system=None):
        calls.append(prompt)
        return await original(prompt, system)
    backend.complete = spy

    async def run():
        return await rb.resolve_manufacturers(
            type("L", (), {"backend": backend})(),
            [{"mpn": "DBD090", "brand": "Diablo®", "supplier": "Freud Inc (2435)", "desc": "cut off disc"}],
        )
    out = asyncio.run(run())
    assert out.get("DBD090") == "Freud Inc"
    assert calls == []  # static map resolved it; zero LLM tokens


def test_resolve_manufacturers_llm_and_cache(tmp_path, monkeypatch):
    from pipeline import run_batch as r
    cache_file = tmp_path / "mfr.json"
    monkeypatch.setattr(r, "MFR_CACHE_PATH", cache_file)
    backend = StubBackend([
        '{"results": [{"mpn": "A1", "manufacturer": "Signify North America Corporation"}]}',
    ])
    llm = type("L", (), {"backend": backend})()

    async def first():
        return await rb.resolve_manufacturers(
            llm, [{"mpn": "A1", "brand": "Philips", "supplier": "Unknown Dist (X)", "desc": "led bulb"}])

    out1 = asyncio.run(first())
    assert out1["A1"] == "Signify North America Corporation"

    # second call: served from disk cache, no new LLM call
    fresh = StubBackend([])
    llm2 = type("L", (), {"backend": fresh})()

    async def second():
        return await rb.resolve_manufacturers(
            llm2, [{"mpn": "A1", "brand": "Philips", "supplier": "Unknown Dist (X)", "desc": "led bulb"}])

    out2 = asyncio.run(second())
    assert out2["A1"] == "Signify North America Corporation"
    assert len(fresh.calls) == 0


import asyncio
