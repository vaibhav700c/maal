"""Manufacturer-site retrieval with trust tiers and marketplace exclusion."""
import json
import re
import ssl
from pathlib import Path
from urllib.parse import quote_plus

import httpx

from pipeline.models import CleanRow, Evidence, RetrievalResult

MARKETPLACE_BLOCKLIST = (
    "amazon.",
    "ebay.",
    "homedepot.",
    "lowes.",
    "grainger.",
    "walmart.",
    "homedepot.com",
    "ferguson.com",
    "supplyhouse.com",
)

CORP_SUFFIXES = {
    "inc", "incorporated", "llc", "ltd", "limited", "co", "company",
    "corp", "corporation", "usa", "us", "na", "north america",
}

CACHE_PATH = Path(__file__).resolve().parents[2] / "output" / "cache" / "retrieval.json"


def load_cache(path: Path = CACHE_PATH) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_cache(cache: dict, path: Path = CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=1))


def domain_candidates(mfr_name: str | None) -> list[str]:
    if not mfr_name:
        return []
    tokens = [
        t for t in re.split(r"[^a-z0-9]+", mfr_name.lower())
        if t and t not in CORP_SUFFIXES and not t.isdigit()
    ]
    if not tokens:
        return []
    first = tokens[0]
    joined = "".join(tokens)
    cands = [f"{first}.com"]
    if joined != first:
        cands.append(f"{joined}.com")
    return cands


def is_marketplace(url: str) -> bool:
    low = url.lower()
    return any(b in low for b in MARKETPLACE_BLOCKLIST)


def trust_tier(url: str, domain: str | None) -> float:
    host = url.split("/")[2] if "://" in url else url.split("/")[0]
    if domain and domain.lower() in host.lower():
        return 0.9 if url.lower().split("?")[0].endswith(".pdf") else 1.0
    return 0.8


async def probe_domain(http: httpx.AsyncClient, domain: str) -> str | None:
    for scheme in ("https://", "https://www."):
        url = scheme + domain
        try:
            resp = await http.head(url, follow_redirects=True, timeout=8)
            if resp.status_code < 400:
                return domain
        except (httpx.HTTPError, ssl.SSLError):
            continue
    return None


async def resolve_domain(http, mfr_name: str | None, cache: dict) -> str | None:
    key = f"domain::{mfr_name or ''}"
    if key in cache:
        return cache[key]
    for cand in domain_candidates(mfr_name):
        if await probe_domain(http, cand):
            cache[key] = cand
            return cand
    cache[key] = ""
    return None


def strip_html(html: str) -> str:
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def snippet_windows(text: str, needle: str, width: int = 300, max_hits: int = 3) -> list[str]:
    out = []
    lowered, needle_low = text.lower(), needle.lower()
    start = 0
    for _ in range(max_hits):
        idx = lowered.find(needle_low, start)
        if idx == -1:
            break
        lo = max(0, idx - width // 3)
        out.append(text[lo : idx + width])
        start = idx + len(needle)
    return out


async def search_mpn(http, ddgs_fn, domain: str, mpn: str) -> list[str]:
    """Return candidate URLs on the manufacturer domain referencing the MPN."""
    urls: list[str] = []
    if ddgs_fn is not None:
        try:
            results = ddgs_fn(f"site:{domain} {mpn}")
            for r in results or []:
                href = r.get("href") or r.get("url") or ""
                if href and mpn.lower() in href.lower():
                    urls.append(href)
        except Exception:  # noqa: BLE001 - search flakiness must not kill pipeline
            pass
    if not urls:
        try:
            resp = await http.get(f"https://{domain}/search?q={quote_plus(mpn)}", timeout=10, follow_redirects=True)
            if resp.status_code == 200:
                for match in re.findall(r'href="([^"]+)"', resp.text)[:80]:
                    if mpn.lower() in match.lower():
                        if match.startswith("/"):
                            match = f"https://{domain}{match}"
                        urls.append(match)
        except httpx.HTTPError:
            pass
    seen, deduped = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped[:5]


async def retrieve_for_row(
    row: CleanRow,
    cache: dict | None = None,
    http: httpx.AsyncClient | None = None,
    ddgs_fn=None,
) -> RetrievalResult:
    cache = cache if cache is not None else {}
    result = RetrievalResult()
    key = f"{row.mfr_name}::{row.mfg_part_num}"
    if cache.get(key):
        return RetrievalResult(**cache[key])

    own_client = http is None
    http = http or httpx.AsyncClient()
    try:
        domain = await resolve_domain(http, row.mfr_name, cache)
        result.domain = domain or None
        if domain is None:
            result.flags.append("NO_MFR_DOMAIN")
            return result
        base_url = f"https://{domain}"
        result.mfr_url = base_url

        flagged_marketplace = False
        for url in await search_mpn(http, ddgs_fn, domain, row.mfg_part_num):
            if is_marketplace(url):
                flagged_marketplace = True
                continue
            tier = trust_tier(url, domain)
            if tier >= 0.9 and len(result.ref_urls) < 5:
                result.ref_urls.append(url)
            try:
                resp = await http.get(url, timeout=12, follow_redirects=True)
                if resp.status_code != 200:
                    continue
            except httpx.HTTPError:
                continue
            for window in snippet_windows(strip_html(resp.text), row.mfg_part_num):
                result.snippets.append(Evidence(quote=window, url=url, tier=tier))
            if len(result.snippets) >= 4:
                break
        if flagged_marketplace:
            result.flags.append("MARKETPLACE_HIT_EXCLUDED")
        if not result.snippets:
            result.flags.append("NO_RETRIEVED_EVIDENCE")
    finally:
        if own_client:
            await http.aclose()

    cache[key] = result.model_dump()
    return result
