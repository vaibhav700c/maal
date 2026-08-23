"""Manufacturer-site retrieval with trust tiers and marketplace exclusion."""
import json
import re
import ssl
import time

from ddgs import DDGS
from pathlib import Path
import urllib.parse
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


async def ddgs_site_hit(
    http: httpx.AsyncClient | None, domain: str, mpn: str
) -> tuple[bool, str | None]:
    """(True, deepUrl) when a site-scoped search against `domain` finds the
    MPN. Uses the Jina proxy so datacenter IP blocks don't matter."""
    try:
        for u in jina_ddg_urls(f"site:{domain} {mpn}"):
            if registeredHost(u, domain) and mpn.lower() in u.split("?")[0].lower():
                return True, u
    except Exception:  # noqa: BLE001
        pass
    return False, None


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


_JINA_CACHE: dict[str, str] = {}


def reader_text(url: str, timeout: int = 15) -> str | None:
    """Free Reader proxy (jina.ai): clean markdown for any URL, defeats
    TLS/bot walls that drop datacenter/serverless fetches.

    Resilience: 3-attempt ladder with backoff on 429/451 (shared-IP rate
    limits), plus a per-process cache so identical pages cost one read."""
    import os

    key = f"jina:{url}"
    if key in _JINA_CACHE:
        return _JINA_CACHE[key]

    headers = dict(BROWSER_HEADERS)
    api_key = os.environ.get("JINA_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    backoff = [1.0, 2.5, 5.0]
    last_exc: Exception | None = None
    for attempt in range(len(backoff) + 1):
        try:
            req = httpx.Request("GET", f"https://r.jina.ai/{url}")
            with httpx.Client(headers=headers, timeout=timeout) as client:
                resp = client.send(req)
            if resp.status_code == 200 and len(resp.text) > 40:
                _JINA_CACHE[key] = resp.text
                return resp.text
            if resp.status_code in (429, 451) and attempt < len(backoff):
                time.sleep(backoff[attempt])
                continue
            return None
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < len(backoff):
                time.sleep(backoff[attempt])
    if last_exc:
        print(f"[reader_text] {url[:60]} failed: {last_exc}", file=sys.stderr)
    return None


def jina_ddg_urls(query: str, timeout: int = 12) -> list[str]:
    """Search results via Jina-proxied DuckDuckGo Lite (IP-block resistant).
    Decodes DDG's uddg= redirect wrappers into real target URLs."""
    body = reader_text(f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}", timeout)
    if not body:
        return []
    urls: list[str] = []
    for raw in re.findall(r"https?://[^\s)\"<>\]]+", body):
        u = raw
        uddg = re.search(r"[?&]uddg=([^&\s]+)", u)
        if uddg:
            u = urllib.parse.unquote(uddg.group(1))
        if u not in urls:
            urls.append(u)
    return urls


async def resolve_domain(
    http, mfr_name: str | None, cache: dict, mpn: str | None = None
) -> str | None:
    key = f"domain::{mfr_name or ''}"
    if key in cache:
        return cache[key]
    for cand in domain_candidates(mfr_name):
        if await probe_domain(http, cand):
            # a live HEAD isn't enough: parked/lookalike domains pass it.
            # require that a site-scoped search against this domain actually
            # returns the part number before trusting it.
            if mpn:
                ok, deep = await ddgs_site_hit(http, cand, mpn)
                if ok:
                    cache[key] = cand
                    cache.setdefault(f"deep::{mfr_name}:{mpn}", deep or "")
                    return cand
            else:
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
        # Jina-proxied search: works from datacenter IPs where direct DDG is blocked
        for url in jina_ddg_urls(f"{mpn or ''} {mfr_name}".strip()):
            try:
                host = urllib.parse.urlsplit(url).hostname or ""
            except ValueError:
                continue
            host_core = ".".join(host.split(".")[-2:])
            if any(t in host_core for t in tokens):
                cache[key] = host_core
                if mpn and mpn.lower() in url.lower():
                    cache.setdefault(f"deep::{mfr_name}:{mpn}", url)
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

    domain = await resolve_domain(http, name_for_domain, cache, part_num)
    result.domain = domain or None
    deep_cached = cache.get(f"deep::{name_for_domain}:{part_num}")
    if domain is None:
        result.flags.append("NO_MFR_DOMAIN")
        return result
    result.mfr_url = f"https://{domain}"
    if deep_cached and not result.product_url:
        result.product_url = deep_cached
        if deep_cached not in result.ref_urls:
            result.ref_urls.insert(0, deep_cached)
    elif deep_cached:
        if deep_cached not in result.ref_urls:
            result.ref_urls.append(deep_cached)
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
        # spec sections live beyond the MPN mention — feed them to the
        # extractor so Voltage/Mounting/Sound Level/etc. become extractable
        lower = text.lower()
        for kw in ("specification", "dimension", "feature", "warranty"):
            kidx = lower.find(kw)
            if kidx != -1:
                chunk = text[max(0, kidx - 80): kidx + 900]
                result.snippets.append(Evidence(quote=chunk, url=url, tier=tier))
        head = text[:1200]
        if head:
            result.snippets.append(Evidence(quote=head, url=url, tier=tier))
        result.snippets = result.snippets[:8]
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
