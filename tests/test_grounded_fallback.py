"""Grounded-search retrieval fallback: sourcing policy must hold."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backend.main import RETRIEVAL_CACHE, _grounded_retrieval_fallback
from pipeline.models import CleanRow


class GroundedBackend:
    def __init__(self, text, urls):
        self._text = text
        self._urls = urls

    async def complete_grounded(self, prompt, system=None):
        return self._text, self._urls


def _llm(backend):
    return type("L", (), {"backend": backend})()


def _clean():
    return CleanRow(
        mfg_part_num="3MABR-7100075678",
        part_desc="3M 775L Stikit Film P150 - Cubitron II 50 Disc/Box",
    )


def test_marketplace_filtered_brand_domain_preferred(monkeypatch):
    monkeypatch.setattr(__import__("backend.main", fromlist=["RETRIEVAL_CACHE"]), "RETRIEVAL_CACHE", {})
    body = (
        '{"product_url": "https://www.3m.com/3M/en_US/p/d/b40071443/", '
        '"ref_urls": ["https://www.3m.com/3M/en_US/p/d/spec.pdf"]}'
    )
    backend = GroundedBackend(body, [
        "https://www.jamindustrialsupply.com/product/3m-cubitron-ii-stikit-film-disc-775l-150/",
        "https://amazon.com/3m-cubitron/dp/B000X",
    ])
    out = asyncio.run(_grounded_retrieval_fallback(_llm(backend), "3MABR-7100075678", _clean(), brand="3M"))
    assert out is not None and "GROUNDED_SEARCH" in out.flags
    assert out.product_url and "3m.com" in out.product_url
    all_urls = [out.mfr_url, out.product_url, *out.ref_urls]
    assert not any("amazon" in u or "jamindustrial" in u for u in all_urls if u)


def test_mpn_exact_url_wins_as_product_url(monkeypatch):
    monkeypatch.setattr(__import__("backend.main", fromlist=["RETRIEVAL_CACHE"]), "RETRIEVAL_CACHE", {})
    body = (
        '{"product_url": null, "ref_urls": '
        '["https://www.3m.com/3M/en_US/p/d/7100075678/"]}'
    )
    backend = GroundedBackend(body, [])
    out = asyncio.run(_grounded_retrieval_fallback(_llm(backend), "3MABR-7100075678", _clean(), brand="3M"))
    assert out.product_url and "7100075678" in out.product_url


def test_all_marketplaces_returns_none_without_negative_cache(monkeypatch):
    cache: dict = {}
    monkeypatch.setattr(__import__("backend.main", fromlist=["RETRIEVAL_CACHE"]), "RETRIEVAL_CACHE", cache)
    backend = GroundedBackend('{"product_url": null}', ["https://ebay.com/itm/123"])
    out = asyncio.run(_grounded_retrieval_fallback(_llm(backend), "X-1", _clean()))
    assert out is None
    assert "grounded::x1" not in cache  # failures stay retryable


def test_backend_without_grounded_support_is_none(monkeypatch):
    monkeypatch.setattr(__import__("backend.main", fromlist=["RETRIEVAL_CACHE"]), "RETRIEVAL_CACHE", {})
    out = asyncio.run(_grounded_retrieval_fallback(object(), "Y-2", _clean()))
    assert out is None
