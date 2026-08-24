"""_merge_knowledge must handle extractions with no attributes yet."""
from pipeline.models import Extraction

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.main import _merge_knowledge


def _data() -> dict:
    return {
        "attributes": [
            {"label": "Voltage Rating", "value": "120", "uom": "V"},
            {"label": "Sound Level", "value": "47", "uom": "dBA"},
        ],
        "series": "Top Control",
        "features": ["Third rack"],
        "certifications": ["ENERGY STAR Certified"],
    }


def test_merge_into_empty_attributes():
    ext = Extraction(item_type="Dishwasher")
    _merge_knowledge(ext, _data())
    assert len(ext.attributes) == 2
    assert ext.attributes[0].verdict == "UNVERIFIED"
    assert ext.series == "Top Control"


def test_merge_dedupes_existing_labels():
    ext = Extraction(
        item_type="Dishwasher",
        attributes=[{"label": "Voltage Rating", "value": "115", "uom": "V"}],
    )
    _merge_knowledge(ext, _data())
    assert len(ext.attributes) == 2
    voltage = next(a for a in ext.attributes if a.label == "Voltage Rating")
    assert voltage.value == "115"  # existing value wins


def test_merge_threads_brand_when_missing():
    ext = Extraction(item_type="Heater Kit")
    _merge_knowledge(ext, {"attributes": [], "brand": "Speed Queen"})
    assert ext.brand == "Speed Queen"


def test_merge_keeps_existing_brand():
    ext = Extraction(item_type="Disc", brand="Diablo")
    _merge_knowledge(ext, {"attributes": [], "brand": "Freud"})
    assert ext.brand == "Diablo"
