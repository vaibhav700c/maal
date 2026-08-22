import httpx
import pytest

import pipeline.retrieve as retrieve
from pipeline.models import CleanRow
from pipeline.retrieve import (
    domain_candidates,
    is_marketplace,
    retrieve_for_row,
    snippet_windows,
    strip_html,
    trust_tier,
)


def test_domain_candidates_strips_corporate_suffixes():
    assert domain_candidates("Freud Inc")[0] == "freud.com"
    cands = domain_candidates("Mirka Abrasives Inc")
    assert "mirka.com" in cands
    assert "mirkaabrasives.com" in cands


def test_marketplace_detection():
    assert is_marketplace("https://www.amazon.com/dp/B08XYZ")
    assert is_marketplace("https://www.grainger.com/product/36YJ34")
    assert not is_marketplace("https://www.freud.com/p/dcd0500")


def test_trust_tiers():
    assert trust_tier("https://freud.com/p/x", "freud.com") == 1.0
    assert trust_tier("https://freud.com/docs/x.pdf", "freud.com") == 0.9
    assert trust_tier("https://other.com/x", "freud.com") == 0.8


def test_snippet_windows():
    text = "filler " * 100 + "The DCB518 belt fits sanders. more text" + " tail " * 50
    windows = snippet_windows(text, "DCB518")
    assert len(windows) == 1
    assert "DCB518" in windows[0].upper()


def test_strip_html():
    html = "<html><script>var x=1;</script><body><p>Hello <b>DCB518</b> world</p></body></html>"
    out = strip_html(html)
    assert "Hello" in out and "DCB518" in out and "<b>" not in out


def _mock_http(routes: dict[str, str]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for pattern, body in routes.items():
            if pattern in url:
                return httpx.Response(200, text=body)
        if url.endswith(("freud.com", "freud.com/")) or "freud.com" in url:
            if request.method == "HEAD":
                return httpx.Response(200)
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


ROW = CleanRow(
    mfg_part_num="DCB518ASTS06G",
    part_desc='DCB518ASTS06G Diablo 1/2"x18" Sanding Belt',
    mfr_name="Freud Inc",
    mfr_code="2435",
)


async def test_retrieve_happy_path_with_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(retrieve, "CACHE_PATH", tmp_path / "cache.json")
    page = "<html><body>Product page for DCB518ASTS06G sanding belt. Specs: 1/2 in x 18 in.</body></html>"
    http = _mock_http({"freud.com/search": f'<a href="/p/{ROW.mfg_part_num}">prod</a>',
                       f"/p/{ROW.mfg_part_num}": page})

    def fake_ddgs(query):
        return [
            {"href": f"https://www.amazon.com/dp/{ROW.mfg_part_num}"},
            {"href": f"https://freud.com/p/{ROW.mfg_part_num}"},
        ]

    cache: dict = {}
    result = await retrieve_for_row(ROW, cache=cache, http=http, ddgs_fn=fake_ddgs)
    assert result.domain == "freud.com"
    assert result.mfr_url == "https://freud.com"
    assert any(s.tier == 1.0 for s in result.snippets)
    assert "MARKETPLACE_HIT_EXCLUDED" in result.flags
    assert any("DCB518ASTS06G" in s.quote.upper() for s in result.snippets)
    # second run served from cache without network
    again = await retrieve_for_row(ROW, cache=cache, http=None, ddgs_fn=None)
    assert again.domain == "freud.com"


async def test_retrieve_no_domain_flags(tmp_path, monkeypatch):
    monkeypatch.setattr(retrieve, "CACHE_PATH", tmp_path / "cache.json")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    row = CleanRow(mfg_part_num="ZZZ", part_desc="unknown thing")
    result = await retrieve_for_row(row, cache={}, http=http, ddgs_fn=lambda q: [])
    assert "NO_MFR_DOMAIN" in result.flags
