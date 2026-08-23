"""Manufacturer-site retrieval with trust tiers and marketplace exclusion."""
import json
import re
import ssl
import time

from ddgs import DDGS
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


def registered_domain(host: str, domain: str) -> bool:
    """True when host is `domain` itself or any subdomain of it."""
    h = host.lower().rstrip(".")
    d = domain.lower()
    return h == d or h.endswith("." + d)


def trust_tier(url: str, domain: str | None) -> float:
    host = url.split("/")[2] if "://" in url else url.split("/")[0]
    if domain and registered_domain(host, domain):
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
    # Many manufacturer sites block bot probes outright. Fall back to asking
    # the search engine: the top organic hit whose HOST contains one of the
    # name's own tokens IS the official domain — no fetch of their servers
    # required.
    tokens = [
        t
        for t in re.split(r"[^a-z0-9]+", (mfr_name or "").lower())
        if len(t) >= 4
    ]
    if tokens and mfr_name:
        try:
            with DDGS() as client:
                hits = list(client.text(mfr_name, max_results=8))
        except Exception:  # noqa: BLE001
            hits = []
        for hit in hits:
            href = (hit.get("href") or hit.get("url") or "").strip()
            if not href.startswith("http"):
                continue
            host = href.split("/")[2].lower()
            host_core = ".".join(host.split(".")[-2:])  # strip www./shop.
            if any(t in host_core for t in tokens):
                cache[key] = host_core
                return host_core
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


def _default_ddgs_fn():
    """Real web-search backend, built lazily so tests can inject fakes."""
    from ddgs import DDGS

    def query(text: str):
        with DDGS() as client:
            return list(client.text(text, max_results=8))

    return query


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def make_http() -> httpx.AsyncClient:
    """Browser-like client: many manufacturer sites drop default python UAs."""
    return httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True)


async def search_mpn(http, ddgs_fn, domain: str, mpn: str) -> list[str]:
    """Return candidate URLs on the manufacturer domain referencing the MPN."""
    urls: list[str] = []
    if ddgs_fn is None:
        try:
            ddgs_fn = _default_ddgs_fn()
        except Exception:  # noqa: BLE001 - optional dependency at runtime
            ddgs_fn = None
    if ddgs_fn is not None:
        for attempt in range(2):  # one retry: engines throttle intermittently
            try:
                results = ddgs_fn(f"site:{domain} {mpn}")
                for r in results or []:
                    href = r.get("href") or r.get("url") or ""
                    if href and mpn.lower() in href.lower():
                        urls.append(href)
                if urls:
                    break
            except Exception:  # noqa: BLE001 - search flakiness must not kill pipeline
                pass
            if attempt == 0 and not urls:
                time.sleep(2)
    if not urls:
        try:
            resp = await http.get(f"https://{domain}/search?q={quote_plus(mpn)}", timeout=10, follow_redirects=True)
            if resp.status_code == 200:
                for match in re.findall(r'href="([^"]+)"', resp.text)[:80]:
                    # require the part number in the PATH, not a query string
                    path_only = match.split("?", 1)[0].split("#", 1)[0]
                    if mpn.lower() in path_only.lower():
                        if match.startswith("/"):
                            match = f"https://{domain}{match}"
                        urls.append(match)
        except httpx.HTTPError:
            pass
    if not urls:
        # common storefront URL patterns that embed the part number directly
        candidates = [
            f"https://{domain}/en/p/{mpn}",
            f"https://{domain}/p/{mpn}",
            f"https://{domain}/product/{mpn}",
            f"https://{domain}?s={quote_plus(mpn)}",
            f"https://{domain}/search?query={quote_plus(mpn)}",
        ]
        for cand in candidates:
            try:
                resp = await http.head(cand, timeout=6, follow_redirects=True)
                final = str(resp.url)
                final_path = final.split("?", 1)[0]
                if resp.status_code < 400 and mpn.lower() in final_path.lower():
                    urls.append(final)
                    break
            except httpx.HTTPError:
                continue
    seen, deduped = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped[:5]


async def _retrieve(
    name_for_domain: str | None,
    part_num: str,
    desc: str,
    cache: dict,
    http: httpx.AsyncClient,
    ddgs_fn=None,
) -> RetrievalResult:
    result = RetrievalResult()
    key = f"{name_for_domain}::{part_num}"
    if cache.get(key):
        cached = RetrievalResult(**cache[key])
        has_value = (
            cached.product_url or cached.snippets or cached.ref_urls
        )
        blocked = "NO_MFR_DOMAIN" in cached.flags
        if has_value or blocked:
            return cached  # dead entries fall through so a later run retries
        del cache[key]

    domain = await resolve_domain(http, name_for_domain, cache)
    result.domain = domain or None
    if domain is None:
        result.flags.append("NO_MFR_DOMAIN")
        return result
    base_url = f"https://{domain}"
    result.mfr_url = base_url

    flagged_marketplace = False
    product_page: str | None = None
    candidate_refs: list[tuple[float, str]] = []
    for url in await search_mpn(http, ddgs_fn, domain, part_num):
        if is_marketplace(url):
            flagged_marketplace = True
            continue
        tier = trust_tier(url, domain)
        if part_num.lower() in url.lower() and product_page is None:
            product_page = url  # deep link to the exact product page
        # collect docs (PDFs) and supporting owned pages for Ref URL slots
        if len(candidate_refs) < 8:
            candidate_refs.append((0.9 if url.lower().endswith(".pdf") or "/pdf" in url.lower() else (1.0 if tier == 1.0 else 2.0), url))
        text: str | None = None
        try:
            resp = await http.get(url, timeout=12, follow_redirects=True)
            if resp.status_code == 200:
                text = strip_html(resp.text)
        except httpx.HTTPError:
            text = None
        if not text:
            text = reader_text(url)  # bot-blocked pages stay readable via Jina
        if not text:
            continue
        for window in snippet_windows(text, part_num):
            result.snippets.append(Evidence(quote=window, url=url, tier=tier))
        # spec sheets / manuals are usually linked from the product page
        for link in re.findall(r'href="([^"]+\.pdf[^"]*)"', text if "href=" in text else "", re.I)[:0]:
            pass
        for link in (re.findall(r'href="([^"]+\.pdf[^"]*)"', resp.text, re.I)[:5] if 'resp' in dir() else []):
            pass
        for link_match in re.finditer(r"\[([^\]]*)\]\(([^)]+\.pdf[^)]*)\)", text):
            pdf = link_match.group(2)
            if pdf.startswith("/"):
                pdf = f"https://{domain}{pdf}"
            if domain.lower() in pdf.lower() and len(candidate_refs) < 8:
                candidate_refs.append((0.9, pdf))
        if len(result.snippets) >= 4:
            break
    result.product_url = product_page
    # Ref URLs: spec-sheet PDFs first, then other owned pages, never the
    # chosen product URL itself; non-owned tiers (2.0 = off-domain) dropped
    pdfs = sorted([c for c in candidate_refs if c[0] == 0.9], key=lambda c: c[1])
    pages = sorted(
        [c for c in candidate_refs if c[0] == 1.0 and c[1] != product_page],
        key=lambda c: c[1],
    )
    for _, u in (pdfs + pages)[:5]:
        if u not in result.ref_urls:
            result.ref_urls.append(u)
    if flagged_marketplace:
        result.flags.append("MARKETPLACE_HIT_EXCLUDED")
    if not result.snippets:
        result.flags.append("NO_RETRIEVED_EVIDENCE")

    cache[key] = result.model_dump()
    return result


async def retrieve_for_row(
    row: CleanRow,
    cache: dict | None = None,
    http: httpx.AsyncClient | None = None,
    ddgs_fn=None,
) -> RetrievalResult:
    cache = cache if cache is not None else {}
    own_client = http is None
    http = http or make_http()
    try:
        return await _retrieve(
            row.mfr_name, row.mfg_part_num, row.part_desc, cache, http, ddgs_fn
        )
    finally:
        if own_client:
            await http.aclose()


async def retrieve_by_brand(
    brand: str,
    row: CleanRow,
    cache: dict | None = None,
    http: httpx.AsyncClient | None = None,
    ddgs_fn=None,
) -> RetrievalResult:
    """Second-pass lookup keyed by the resolved BRAND instead of the supplier."""
    cache = cache if cache is not None else {}
    own_client = http is None
    http = http or make_http()
    try:
        return await _retrieve(
            brand, row.mfg_part_num, row.part_desc, cache, http, ddgs_fn
        )
    finally:
        if own_client:
            await http.aclose()
