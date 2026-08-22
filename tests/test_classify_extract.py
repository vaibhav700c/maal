from pipeline.classify import classify_rows, _parse
from pipeline.extract import extract, pre_extract_attributes
from pipeline.models import CleanRow, Classification, RetrievalResult
from pipeline.llm import StubBackend, LLMClient


class ListLLM:
    """Test double returning canned JSON for generate_json."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    async def generate_json(self, prompt, system=None):
        self.prompts.append(prompt)
        return self.responses.pop(0)


def test_parse_classification_from_classpath_only():
    parsed = _parse({"classpath": "A>B>C", "unspsc": None})
    assert (parsed.dept, parsed.klass, parsed.fine) == ("A", "B", "C")


def test_classify_batches_preserve_order():
    rows = [CleanRow(mfg_part_num=f"P{i}", part_desc=f"item {i}") for i in range(45)]
    llm = ListLLM(
        [
            [{"index": i, "classpath": f"D>C>F{i}", "unspsc": None} for i in range(20)],
            [{"index": i, "classpath": f"D>C>F{20+i}", "unspsc": None} for i in range(20)],
            # third batch: malformed first element, valid rest
            [{"bad": 1}]
            + [{"index": i, "classpath": f"D>C>F{40+i}", "unspsc": None} for i in range(1, 5)],
        ]
    )
    result = __import__("asyncio").run(classify_rows(llm, rows, batch=20))
    assert result["P0"].fine == "F0"
    assert result["P39"].fine == "F39"
    assert "P40" not in result
    assert result["P44"].fine == "F44"


def test_pre_extract_dimensions_and_electrical():
    desc = '49-94-0063 Milw 14"x.045"x7/8" Metal Cut Off Disc'
    attrs = pre_extract_attributes(desc)
    got = {a.label: a.value for a in attrs}
    assert got == {"Diameter": "14", "Thickness": ".045", "Arbor": "7/8"}
    electrical = pre_extract_attributes("Dishwasher 120V 15A 1800W")
    labels = {a.label: (a.value, a.uom) for a in electrical}
    assert labels["Voltage Rating"] == ("120", "V")
    assert labels["Amperage Rating"] == ("15", "A")
    assert labels["Wattage"] == ("1800", "W")
    grit = pre_extract_attributes("3M 775L Stikit Film P150 Disc")
    assert grit[-1].label == "Grit" and grit[-1].value == "150"
    assert all(a.evidence.tier == 0.0 for a in attrs)


async def test_extract_attaches_snippet_evidence_and_merges_preextracted():
    row = CleanRow(
        mfg_part_num="X9",
        part_desc='X9 Disc 14"x1/8"x1"',
        mfr_name="Freud Inc",
    )
    classif = Classification(
        dept="Tools", klass="Abrasives", fine="Cut Off Discs",
        classpath="Tools>Abrasives>Cut Off Discs",
    )
    snippet_text = 'X9 Disc 14"x1/8"x1" aluminum oxide cutting disc'
    retrieval = RetrievalResult(
        domain="freud.com",
        mfr_url="https://freud.com",
        snippets=[
            __import__("pipeline.models", fromlist=["Evidence"]).Evidence(
                quote=snippet_text, url="https://freud.com/p/x9", tier=1.0
            )
        ],
    )
    llm = ListLLM([
        {
            "item_type": "Cut Off Disc",
            "series": None,
            "attributes": [
                {"label": "Diameter", "value": "14", "uom": "in", "quote": snippet_text[:60]},
                {"label": "Max RPM", "value": "5100", "uom": None, "quote": "totally fabricated quote"},
            ],
            "features": ["Metal cutting"],
            "certifications": [],
            "application": None,
            "includes": None,
            "additional": None,
        }
    ])
    out = await extract(llm, row, classif, retrieval)
    by_label = {a.label: a for a in out.attributes}
    assert by_label["Diameter"].evidence.url == "https://freud.com/p/x9"
    assert by_label["Diameter"].evidence.tier == 1.0
    assert by_label["Max RPM"].verdict == "UNSUPPORTED"
    assert "Arbor" in by_label  # merged from pre-extraction
    assert out.item_type == "Cut Off Disc"


async def test_extract_many_positional_fallback_without_index():
    from pipeline.extract import extract_many

    class PosLLM:
        async def generate_json(self, prompt, system=None):
            # model omitted "index" entirely -> positional mapping must apply
            return [
                {"item_type": "Cut Off Disc", "attributes": [
                    {"label": "Diameter", "value": "14", "uom": "in", "quote": "14 inch"}]},
                {"item_type": "Sanding Belt", "attributes": []},
            ]

    rows = [
        (CleanRow(mfg_part_num="R0", part_desc='R0 Disc 14"x1/8"x1"'), None, None),
        (CleanRow(mfg_part_num="R1", part_desc="R1 Belt 1/2x18"), None, None),
    ]
    out = await extract_many(PosLLM(), rows, batch=8)
    assert [e.item_type for e in out] == ["Cut Off Disc", "Sanding Belt"]
    assert out[0].attributes[0].value == "14"
