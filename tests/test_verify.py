from pipeline.models import Attribute, Extraction, RetrievalResult
from pipeline.verify_adversarial import select_stakes, verify


class FakeLLM:
    def __init__(self, response):
        self.response = response

    async def generate_json(self, prompt, system=None):
        return self.response


def _extraction() -> Extraction:
    return Extraction(
        item_type="Disc",
        attributes=[
            Attribute(label="Diameter", value="14", uom="in"),
            Attribute(label="Arbor", value="1", uom="in"),
            Attribute(label="Material", value="Aluminum Oxide"),
        ],
    )


def test_select_stakes_numeric_only():
    stakes = select_stakes(_extraction())
    labels = [a.label for a in stakes]
    assert "Material" not in labels
    assert set(labels) == {"Diameter", "Arbor"}


async def test_verify_applies_all_three_verdicts():
    extraction = _extraction()
    retrieval = RetrievalResult(
        domain="freud.com",
        snippets=[],
    )
    response = [
        {"index": 0, "verdict": "CONFIRMED", "reason": "matches source"},
        {"index": 1, "verdict": "REFUTED", "reason": "source says 7/8 in"},
    ]
    out = await verify(FakeLLM(response), extraction, retrieval)
    by_label = {a.label: a for a in out.attributes}
    assert by_label["Diameter"].verdict == "CONFIRMED"
    assert by_label["Arbor"].verdict == "REFUTED"
    assert "7/8" in by_label["Arbor"].review_reason
    assert by_label["Material"].verdict == "UNVERIFIED"


async def test_verify_missing_verdict_defaults_unsupported():
    out = await verify(FakeLLM([]), _extraction(), None)
    diameter = next(a for a in out.attributes if a.label == "Diameter")
    assert diameter.verdict == "UNSUPPORTED"
