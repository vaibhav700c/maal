/**
 * Serverless enrichment engine — mirrors the local Python pipeline stages:
 * cleanse -> classify -> extract(evidence) -> brand inference ->
 * retrieve(brand domain) -> attach evidence -> arithmetic physics ->
 * deterministic descriptions + Unilog asset conventions.
 *
 * Runs inside a Vercel function (maxDuration 60). Gemini via REST; no z3 —
 * constraint checks are the arithmetic equivalents, labeled identically in
 * the UI so provenance semantics stay consistent.
 */
import type { JobResultRow } from "./jobs";

const GEMINI = "https://generativelanguage.googleapis.com/v1beta/models";
const MODELS = [
  process.env.GEMINI_MODEL || "gemini-flash-latest",
  "gemini-3.1-flash-lite",
  "gemini-flash-lite-latest",
];
const KEY = process.env.GEMINI_API_KEY || "";
const UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36";

export type CloudInput = {
  mpn: string;
  description: string;
  brand?: string;
  supplier?: string;
};

// ---------- generic LLM ----------
let domainCache = new Map<string, string>();

async function geminiText(prompt: string, system?: string): Promise<string> {
  if (!KEY) throw new Error("GEMINI_API_KEY missing");
  let lastErr = "";
  for (const model of MODELS) {
    try {
      const res = await fetch(`${GEMINI}/${model}:generateContent?key=${KEY}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...(system ? { systemInstruction: { parts: [{ text: system }] } } : {}),
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: { temperature: 0.2, maxOutputTokens: 2048 },
        }),
      });
      const data: any = await res.json().catch(() => null);
      if (!res.ok) {
        lastErr = `${model}: ${res.status} ${data?.error?.message ?? ""}`;
        continue;
      }
      return data?.candidates?.[0]?.content?.parts?.map((p: any) => p.text ?? "").join("") ?? "";
    } catch (e: any) {
      lastErr = `${model}: ${e?.message ?? e}`;
    }
  }
  throw new Error(`all models failed -> ${lastErr}`);
}

function looseJson(text: string): any {
  const fence = /```(?:json)?\s*([\s\S]*?)```/.exec(text);
  let raw = fence ? fence[1] : text;
  try {
    return JSON.parse(raw);
  } catch {
    /* fall through */
  }
  const embedded = /\{[\s\S]*\}|[[\s\S]*]/.exec(raw);
  const probe = embedded ? embedded[0] : raw;
  try {
    return JSON.parse(probe.replace(/,\s*([}\]])/g, "$1"));
  } catch {
    return null;
  }
}

async function geminiJson(prompt: string, system: string): Promise<any> {
  const parsed = looseJson(await geminiText(prompt, system));
  if (parsed === null || parsed === undefined) throw new Error("invalid JSON");
  return parsed;
}

async function llmDomain(brand: string): Promise<string | null> {
  const cached = domainCache.get(`d:${brand.toLowerCase()}`);
  if (cached !== undefined) return cached || null;
  try {
    const text = await geminiText(
      `Reply with ONLY the official website domain of the brand ${brand}, in the form example.com — no scheme, no path, no explanation.`
    );
    const m = /([a-z0-9-]+\.[a-z0-9.-]+)/i.exec(text.trim());
    const domain = m ? m[1].toLowerCase().replace(/\.$/, "") : "";
    domainCache.set(`d:${brand.toLowerCase()}`, domain);
    return domain || null;
  } catch {
    return null;
  }
}

// ---------- deterministic helpers (ported) ----------
export const PLACEHOLDERS = new Set([
  "-- Unbranded --",
  "-- No Unilog Brand --",
  "-- No DIB Brand --",
]);

export function cleanBrand(v?: string | null): string | null {
  const t = (v ?? "").trim();
  if (!t || PLACEHOLDERS.has(t) || t === "-") return null;
  return t;
}

export function parseManuf(v?: string | null): { name: string; code: string | null } {
  const t = (v ?? "").trim();
  if (!t || t === "-") return { name: "", code: null };
  const m = /^(.*?)\s*\(([^)]+)\)\s*$/.exec(t);
  if (m && m[1].trim()) return { name: m[1].trim(), code: m[2].trim() };
  return { name: t, code: null };
}

const UOM: Record<string, string> = {
  in: "in", '"': "in", inch: "in", inches: "in",
  ft: "ft", "'": "ft", feet: "ft", foot: "ft",
  mm: "mm", cm: "cm", m: "m",
  v: "V", volt: "V", volts: "V",
  a: "A", amp: "A", amps: "A",
  w: "W", watt: "W", watts: "W",
  dba: "dBA", psi: "psi", rpm: "RPM", hp: "hp",
  lb: "lb", lbs: "lb", pound: "lb", pounds: "lb", oz: "oz",
};

function gcd(a: number, b: number): number {
  return b === 0 ? a : gcd(b, a % b);
}

export function decimalToFraction(value: number, denom = 64, tol = 0.0101): string | null {
  const sign = value < 0 ? "-" : "";
  value = Math.abs(value);
  let whole = Math.floor(value);
  let rem = value - whole;
  let nearest = Math.round(rem * denom);
  if (nearest === denom) { nearest = 0; whole += 1; }
  if (Math.abs(nearest / denom - rem) > tol) return null;
  if (nearest === 0) return `${sign}${whole}`;
  const g = gcd(nearest, denom);
  const num = nearest / g, den = denom / g;
  if (den === 1) return `${sign}${whole + num}`;
  return `${sign}${whole ? `${whole}-` : ""}${num}/${den}`;
}

export function formatMeasure(v: number): string {
  return decimalToFraction(v) ?? String(+v.toFixed(4));
}

function attrText(value: string, uom: string | null | undefined): string {
  const cleaned = value.replace(/(\d)\s*"/g, "$1 in");
  return uom ? `${cleaned} ${uom}`.trim() : cleaned;
}

function join(parts: Array<string | null | undefined>): string {
  return parts.filter(Boolean).join(", ");
}

function truncateWords(text: string, limit: number): string {
  if (text.length <= limit) return text;
  const cut = text.slice(0, limit);
  return (cut.includes(" ") ? cut.slice(0, cut.lastIndexOf(" ")) : cut).replace(/[ ,]+$/, "");
}

// ---------- cleansing + pre-extraction ----------
export type CleanInput = CloudInput & { supplierName: string | null; supplierCode: string | null };

export function cleanse(input: CloudInput): CleanInput {
  const { name, code } = parseManuf(input.supplier);
  const desc = input.description.replace(/""/g, '"');
  return { ...input, description: desc, supplierName: name || null, supplierCode: code };
}

const DIM_Q = /(\d+(?:\.\d+)?(?:-\d+\/\d+|\/\d+)?|\d*\.?\d+(?:-\d+\/\d+|\/\d+)?)"/;
const DISC_HINT = /disc|blade|wheel|cutter|saw|grinder|cut.?off/i;

export type PreAttr = { label: string; value: string; uom: string | null };

export function preExtract(descRaw: string, mpn: string): PreAttr[] {
  let desc = descRaw.replace(/""/g, '"');
  const firstTok = desc.split(" ")[0] ?? "";
  if (firstTok.length >= 4 && /\d/.test(firstTok)) desc = desc.slice(firstTok.length + 1);
  desc = desc.replace(/(\d+(?:\.\d+)?(?:-\d+\/\d+)?)\s*(?:ft|')(?=\s|$)/g, "$1 ft ");
  const out: PreAttr[] = [];
  const add = (label: string, value: string, uom: string | null) =>
    out.push({ label, value, uom });
  const dims = [...desc.matchAll(new RegExp(DIM_Q.source, "g"))].map((m) => m[1]);
  if (dims.length >= 3) {
    add("Diameter", dims[0], "in");
    add("Thickness", dims[1], "in");
    add("Arbor", dims[2], "in");
  } else if (dims.length === 2) {
    add("Diameter", dims[0], "in");
    add("Arbor", dims[1], "in");
  }
  for (const m of desc.matchAll(/(\d+(?:\.\d+)?)\s+ft\b/g)) add("Length", m[1], "ft");
  if (!dims.length && DISC_HINT.test(desc)) {
    const pair = /(\d+(?:\.\d+)?(?:-\d+\/\d+)?)\s?[xX]\s?(\d+(?:\.\d+)?(?:-\d+\/\d+)?)/.exec(desc);
    if (pair) {
      add("Diameter", pair[1], "in");
      add("Arbor", pair[2], "in");
    }
  }
  const volt = /(\b\d+(?:\.\d+)?)\s?V\b/.exec(desc);
  if (volt) add("Voltage Rating", volt[1], "V");
  const amp = /(\b\d+(?:\.\d+)?)\s?A\b/.exec(desc);
  if (amp) add("Amperage Rating", amp[1], "A");
  const watt = /(\b\d+(?:\.\d+)?)\s?W\b/.exec(desc);
  if (watt) add("Wattage", watt[1], "W");
  const grit = /\bP(\d{2,4})\b/.exec(desc);
  if (grit) add("Grit", grit[1], null);
  void mpn;
  return out;
}

// ---------- retrieval (manufacturer domains only) ----------
const MARKETPLACE = ["amazon.", "ebay.", "homedepot.", "lowes.", "grainger.", "walmart.", "ferguson.", "supplyhouse."];

function isMarketplace(url: string): boolean {
  const low = url.toLowerCase();
  return MARKETPLACE.some((b) => low.includes(b));
}

function registeredHost(url: string, domain: string): boolean {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return host === domain || host.endsWith(`.${domain}`);
  } catch {
    return false;
  }
}

async function ddgsSearch(query: string): Promise<string[]> {
  const res = await fetch("https://html.duckduckgo.com/html/", {
    method: "POST",
    headers: { "User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded" },
    body: `q=${encodeURIComponent(query)}`,
  });
  if (!res.ok) return [];
  const html = await res.text();
  const out: string[] = [];
  for (const m of html.matchAll(/result__a[^>]*href="([^"]+)"/g)) {
    let href = m[1];
    const uddg = /uddg=([^&]+)/.exec(href);
    if (uddg) href = decodeURIComponent(uddg[1]);
    if (href.startsWith("http")) out.push(href);
  }
  return out;
}

async function probeUrl(url: string): Promise<string | null> {
  try {
    const res = await fetch(url, { method: "HEAD", headers: { "User-Agent": UA }, redirect: "follow" });
    if (res.status < 400) return res.url;
  } catch { /* ignore */ }
  return null;
}

type Retrieval = {
  domain: string | null;
  mfr_url?: string;
  productUrl: string | null;
  refUrls: string[];
  snippets: Array<{ quote: string; url: string; tier: number }>;
  flags: string[];
};

async function retrieve(
  nameForDomain: string,
  mpn: string,
  llm: boolean
): Promise<Retrieval> {
  const ret: Retrieval = { domain: null, productUrl: null, refUrls: [], snippets: [], flags: [] };
  let domain: string | null = null;
  if (llm) domain = await llmDomain(nameForDomain);
  if (!domain) {
    // slug probes from the name itself
    const tokens = nameForDomain.toLowerCase().split(/[^a-z0-9]+/).filter((t) => t.length >= 3);
    for (const cand of [tokens[0] ? `${tokens[0]}.com` : "", tokens.join("") ? `${tokens.join("")}.com` : ""].filter(Boolean)) {
      const ok = await probeUrl(`https://${cand}`);
      if (ok !== null) { domain = cand; break; }
    }
  }
  if (!domain) { ret.flags.push("NO_MFR_DOMAIN"); return ret; }
  ret.domain = domain;
  ret.mfr_url = `https://${domain}`;

  const urls: string[] = [];
  for (let attempt = 0; attempt < 2 && urls.length === 0; attempt++) {
    try {
      const hits = await ddgsSearch(`site:${domain} ${mpn}`);
      for (const h of hits) {
        const pathOnly = h.split("?")[0];
        if (pathOnly.toLowerCase().includes(mpn.toLowerCase()) && registeredHost(h, domain)) urls.push(h);
      }
    } catch { /* flaky */ }
    if (!urls.length && attempt === 0) await new Promise((r) => setTimeout(r, 1500));
  }
  if (!urls.length) {
    for (const cand of [
      `https://${domain}/en/p/${mpn}`,
      `https://${domain}/p/${mpn}`,
      `https://${domain}/product/${mpn}`,
    ]) {
      const final = await probeUrl(cand);
      if (final && final.split("?")[0].toLowerCase().includes(mpn.toLowerCase())) { urls.push(final); break; }
    }
  }

  const candidateRefs: Array<[number, string]> = [];
  for (const url of urls.slice(0, 5)) {
    if (isMarketplace(url)) { ret.flags.push("MARKETPLACE_HIT_EXCLUDED"); continue; }
    if (!registeredHost(url, domain)) continue;
    const pathLower = url.split("?")[0].toLowerCase();
    if (!ret.productUrl && pathLower.includes(mpn.toLowerCase())) ret.productUrl = url;
    const isPdf = pathLower.endsWith(".pdf") || pathLower.includes("/pdf");
    if (candidateRefs.length < 8) candidateRefs.push([isPdf ? 0.9 : 1.0, url]);
    try {
      const res = await fetch(url, { headers: { "User-Agent": UA }, redirect: "follow" });
      if (!res.ok) continue;
      const html = await res.text();
      const text = html
        .replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/gi, " ")
        .replace(/<[^>]+>/g, " ")
        .replace(/\s+/g, " ");
      const lower = text.toLowerCase();
      let idx = lower.indexOf(mpn.toLowerCase());
      let windows = 0;
      while (idx !== -1 && windows < 2) {
        ret.snippets.push({ quote: text.slice(Math.max(0, idx - 100), idx + mpn.length + 200), url, tier: pathLower.endsWith(".pdf") || pathLower.includes("/pdf") ? 0.9 : 1.0 });
        windows += 1;
        idx = lower.indexOf(mpn.toLowerCase(), idx + mpn.length);
      }
      for (const link of html.matchAll(/href="([^"]+\.pdf[^"]*)"/gi)) {
        let pdf = link[1];
        if (pdf.startsWith("/")) pdf = `https://${domain}${pdf}`;
        if (registeredHost(pdf, domain) && candidateRefs.length < 8) candidateRefs.push([0.9, pdf]);
      }
      if (ret.snippets.length >= 4) break;
    } catch { /* blocked pages are fine — URL still counts */ }
  }
  ret.refUrls = [...new Set(candidateRefs.sort((a, b) => a[0] - b[0]).map(([, u]) => u))]
    .filter((u) => u !== ret.productUrl)
    .slice(0, 5);
  if (!ret.snippets.length) ret.flags.push("NO_RETRIEVED_EVIDENCE");
  return ret;
}

// ---------- extraction ----------
const EXTRACT_SYSTEM =
  "You are a precise industrial catalog data extractor. Attribute values come ONLY from the raw description and supplied source snippets — never invent measurements. ONE exception: the brand may be inferred from the product's model/part number using your knowledge of manufacturer coding schemes (e.g. PDSH4816AF -> Frigidaire, DBDS14125A01F -> Diablo, 49-94-0063 -> Milwaukee); only infer when confident. Every other attribute MUST carry a short verbatim 'quote' copied exactly from the description or a snippet; omit facts not present. Output STRICT JSON only.";

type RawAttr = { label: string; value: string; uom?: string | null; quote?: string | null };

async function extractWithLLM(input: CleanInput) {
  const prompt = `Extract structured product data.

RAW DESCRIPTION: ${input.description}
SUPPLIER (may be a distributor, not the maker): ${input.supplierName ?? "unknown"}

Output STRICT JSON:
{"item_type": "short product type noun",
 "series": null,
 "brand": "brand printed on the product OR confidently inferred from the model number (e.g. '3M','Diablo','Leviton','Frigidaire') or null — NOT the supplier",
 "brand_inferred": true if brand came from model-number knowledge rather than text,
 "manufacturer": "actual product manufacturer you are confident about, else null",
 "attributes": [{"label":"...","value":"...","uom":"approved abbrev or null","quote":"verbatim source text"}],
 "features": ["short feature phrase"],
 "certifications": ["UL Listed"],
 "application": null,
 "includes": null,
 "warranty": {"value": "...", "quote": "..."} or null,
 "country_of_origin": {"value": "...", "quote": "..."} or null,
 "upc": {"value": "12 digits", "quote": "..."} or null,
 "package_quantity": {"value": "10", "quote": "..."} or null,
 "additional": null}`;
  const data = await geminiJson(prompt, EXTRACT_SYSTEM);
  return data && typeof data === "object" ? data : null;
}

async function inferBrandLLM(input: CleanInput): Promise<string | null> {
  try {
    const ans = (
      await geminiText(
        `Which retail brand makes the product with model number ${input.mpn} and description '${input.description.slice(0, 120)}'? Reply with ONLY the brand name (e.g. DeWalt, Diablo, Milwaukee), or NONE if genuinely unknown.`
      )
    ).trim();
    const candidate = ans.split("\n")[0].replace(/"/g, "").trim();
    if (candidate && candidate.toUpperCase() !== "NONE" && candidate.length > 1 && candidate.length < 30)
      return candidate;
  } catch { /* opportunistic */ }
  return null;
}

// ---------- arithmetic physics (cloud equivalent of the Z3 families) ----------
function num(v: string | undefined | null): number | null {
  if (!v) return null;
  const t = v.trim();
  const frac = /^(\d+)-(\d+)\/(\d+)$/.exec(t);
  if (frac) {
    const d = Number(frac[3]);
    return d ? Number(frac[1]) + Number(frac[2]) / d : null;
  }
  const simple = /^(\d+)\/(\d+)$/.exec(t);
  if (simple) {
    const d = Number(simple[2]);
    return d ? Number(simple[1]) / d : null;
  }
  const f = parseFloat(t.replace(",", ""));
  return Number.isFinite(f) ? f : null;
}

export function physicsChecks(attrs: Array<{ label: string; value: string }>) {
  const get = (label: string) => attrs.find((a) => a.label.toLowerCase() === label.toLowerCase());
  const checks: Array<{ name: string; status: "SAT" | "UNSAT" | "SKIPPED"; reason: string | null }> = [];
  const v = get("Voltage Rating"), a = get("Amperage Rating"), w = get("Wattage");
  const vn = (v && num(v.value)) ?? null;
  const an = (a && num(a.value)) ?? null;
  const wn = (w && num(w.value)) ?? null;
  if (vn !== null && an !== null && wn !== null) {
    const ok = Math.abs(wn - vn * an) <= 0.10 * Math.max(wn, vn * an);
    checks.push({
      name: "power_balance",
      status: ok ? "SAT" : "UNSAT",
      reason: ok ? null : `watts ${wn} does not equal volts ${vn} x amps ${an} (within 10%); one of these values is wrong`,
    });
  } else checks.push({ name: "power_balance", status: "SKIPPED", reason: null });

  const dia = get("Diameter"), arb = get("Arbor");
  const dn = (dia && num(dia.value)) ?? null;
  const bn = (arb && num(arb.value)) ?? null;
  if (dn !== null && bn !== null) {
    const ok = dn > bn;
    checks.push({
      name: "diameter_gt_arbor",
      status: ok ? "SAT" : "UNSAT",
      reason: ok ? null : `disc/blade diameter ${dn} must be larger than the arbor/bore ${bn}`,
      fields_placeholder: undefined,
    } as any);
  } else checks.push({ name: "diameter_gt_arbor", status: "SKIPPED", reason: null });

  const ranges: Array<[string, number, number]> = [
    ["sound level", 30, 80], ["voltage rating", 0.5, 1000],
    ["amperage rating", 0.05, 400], ["wattage", 0.1, 20000],
  ];
  let ranged = false;
  for (const [label, lo, hi] of ranges) {
    const hit = attrs.find((x) => x.label.toLowerCase().includes(label));
    if (!hit) continue;
    const n = num(hit.value);
    ranged = true;
    if (n === null || n < lo || n > hi) {
      checks.push({
        name: "unit_range_sanity",
        status: "UNSAT",
        reason: `${hit.label} value ${hit.value} outside plausible range ${lo}-${hi}`,
      });
      break;
    }
  }
  if (!ranged || !checks.some((c) => c.name === "unit_range_sanity"))
    checks.push({ name: "unit_range_sanity", status: "SKIPPED", reason: null });
  checks.push({ name: "id_lt_od", status: "SKIPPED", reason: null });
  checks.push({ name: "fraction_decimal_consistency", status: "SKIPPED", reason: null });
  void a; void w;
  return checks;
}

// ---------- record assembly ----------
export type CloudRow = JobResultRow & { additional: string | null };

function buildDescriptions(d: {
  brand: string | null; manuf: string | null; mpn: string;
  itemType: string; series: string | null; feature: string | null;
  attributes: Array<{ label: string; value: string; uom: string | null }>;
  additional: string | null;
}) {
  const brand = d.brand || d.manuf || null;
  const head = join([d.manuf && brand ? `${d.manuf} ${brand}` : brand, d.itemType, d.series, d.mpn]);
  let mobile = head;
  if (mobile.length < 60 && d.attributes.length)
    mobile += `, ${d.attributes.slice(0, 3).map((a) => attrText(a.value, a.uom)).join(", ")}`;
  const shortLead = [brand, d.series, d.mpn, d.itemType].filter(Boolean).join(" ");
  const short = join([
    d.feature ? `${shortLead} With ${d.feature}` : shortLead,
    ...d.attributes
      .filter((a) => ["mounting type", "material", "color", "size"].includes(a.label.toLowerCase()))
      .slice(0, 3)
      .map((a) => attrText(a.value, a.uom)),
  ]).slice(0, 120);
  const body = [
    d.series ?? null,
    ...d.attributes.map((a) => (a.uom ? `${attrText(a.value, a.uom)} ${a.label}` : attrText(a.value, a.uom))),
  ];
  const long =
    `${brand ?? ""} ${d.itemType}${d.feature ? ` With ${d.feature}` : ""}, `.replace(/^ /, "") +
    body.join(", ") +
    (d.additional ? `, Additional Information: ${d.additional}` : "");
  const retail = join([
    [d.series, d.itemType].filter(Boolean).join(" "),
    ...d.attributes
      .filter((a) => !["voltage rating", "amperage rating"].includes(a.label.toLowerCase()))
      .slice(0, 3)
      .map((a) => attrText(a.value, a.uom)),
  ]).slice(0, 160);
  return {
    invoice: truncateWords(
      [d.itemType.toUpperCase(), ...d.attributes.slice(0, 6).map((a) => attrText(a.value, a.uom).replace(/ /g, "").toUpperCase())].join(" ").slice(0, 40),
      40
    ),
    mobile,
    short: short || shortLead,
    long: long.replace(/\s+,/g, ","),
    retail,
  };
}

const TIER_BASE: Record<string, number> = { "0": 0.35, "0.5": 0.55, "0.9": 0.75, "1": 1 };
const VERDICT_MULT: Record<string, number> = { CONFIRMED: 1, UNVERIFIED: 0.6, UNSUPPORTED: 0.45, REFUTED: 0 };

function score(tier: number, verdict: string): number {
  const base = TIER_BASE[String(tier)] ?? Math.min(1, Math.max(0.35, tier));
  const s = base * (VERDICT_MULT[verdict] ?? VERDICT_MULT.UNVERIFIED);
  return Math.round(Math.max(0, Math.min(1, s)) * 1000) / 1000;
}

export async function enrichOne(input: CloudInput): Promise<CloudRow> {
  const clean: CleanInput = cleanse(input);
  const flags: string[] = [];
  const mpn = clean.mpn;

  // 1) classify + extract in one structured call (input-only evidence)
  let data: any = null;
  try {
    data = await extractWithLLM(clean);
  } catch { /* fallback below */ }
  if (!data || !data.item_type) {
    data = { item_type: "Product", attributes: [], features: [], certifications: [] };
  }

  // 2) focused brand retry when skipped
  let brand: string | null = typeof data.brand === "string" && data.brand.trim() ? data.brand.trim() : null;
  let brandInferred = !!data.brand_inferred;
  if (!brand) {
    brand = await inferBrandLLM(clean);
    brandInferred = !!brand;
  }
  let manufacturer: string | null =
    typeof data.manufacturer === "string" && data.manufacturer.trim() ? data.manufacturer.trim() : clean.supplierName;

  // 3) retrieval on the BRAND domain first (supplier is often a distributor)
  let retrieval = await retrieve(brand || clean.supplierName || "", mpn, !!brand);
  if (!retrieval.productUrl && !retrieval.refUrls.length && !retrieval.snippets.length && brand !== clean.supplierName) {
    const alt = await retrieve(clean.supplierName || brand || "", mpn, false);
    if (alt.productUrl || alt.snippets.length) Object.assign(retrieval, alt, { flags: [...alt.flags, "SUPPLIER_DOMAIN_FALLBACK"] });
  }
  if (!retrieval.domain) flags.push("NEEDS_REVIEW");

  // 4) assemble attribute ledger with provenance + verdicts
  type Led = { label: string; value: string; uom: string | null; verdict: string; confidence: number; quote: string | null; url: string | null; reviewReason?: string | null };
  const ledger: Led[] = [];
  const snippetHit = (needle: string) =>
    retrieval.snippets.find((s) => needle && s.quote.toLowerCase().includes(needle.toLowerCase()));

  for (const raw of (data.attributes ?? []) as RawAttr[]) {
    const label = String(raw.label ?? "").trim();
    const value = String(raw.value ?? "").trim();
    if (!label || !value) continue;
    const hit = snippetHit(String(raw.quote ?? "") || value);
    const verdict = hit ? "CONFIRMED" : "UNSUPPORTED";
    ledger.push({
      label, value, uom: raw.uom ? String(raw.uom) : null,
      verdict,
      confidence: score(hit ? 1 : 0, verdict),
      quote: hit ? hit.quote : String(raw.quote ?? clean.description.slice(0, 200)),
      url: hit?.url ?? null,
      reviewReason: hit ? null : "no manufacturer source available to verify",
    });
  }
  for (const pre of preExtract(clean.description, mpn)) {
    if (!ledger.some((l) => l.label.toLowerCase() === pre.label.toLowerCase())) {
      const verdict = "UNVERIFIED";
      ledger.push({
        label: pre.label, value: pre.value, uom: pre.uom, verdict,
        confidence: score(0, verdict),
        quote: clean.description.slice(0, 200), url: null,
        reviewReason: "input-derived",
      });
    }
  }
  if (brand && !ledger.some((l) => l.label.toLowerCase() === "brand name")) {
    ledger.unshift({
      label: "Brand Name", value: brand, uom: null, verdict: "UNVERIFIED",
      confidence: score(brandInferred ? 0.5 : 0, "UNVERIFIED"),
      quote: brandInferred ? `inferred from model number ${mpn}` : clean.description.slice(0, 200),
      url: null, reviewReason: brandInferred ? "brand inferred from manufacturer model-code knowledge" : null,
    });
  }
  for (const [jsonKey, label] of [
    ["warranty", "Warranty"],
    ["country_of_origin", "Country of Origin"],
    ["upc", "UPC"],
  ] as const) {
    const v = data[jsonKey];
    const val = typeof v === "object" && v ? String(v.value ?? "").trim() : "";
    const quote = typeof v === "object" && v ? String(v.quote ?? "") : "";
    if (!val || !quote) continue;
    const hit = snippetHit(quote.slice(0, 80));
    ledger.push({
      label, value: val, uom: null, verdict: hit ? "CONFIRMED" : "UNVERIFIED",
      confidence: score(hit ? (retrieval.snippets.find((s) => s.quote === hit.quote)?.tier ?? 1) : 0, hit ? "CONFIRMED" : "UNVERIFIED"),
      quote: hit ? hit.quote : quote.slice(0, 200),
      url: hit?.url ?? null, reviewReason: null,
    });
  }
  const pq = data.package_quantity;
  const pqVal = typeof pq === "object" && pq ? String(pq.value ?? "") : typeof pq === "string" ? pq : "";
  if (pqVal && /^\d+$/.test(pqVal)) {
    ledger.push({
      label: "Package Quantity", value: pqVal, uom: null, verdict: "UNVERIFIED",
      confidence: score(0, "UNVERIFIED"), quote: String((typeof pq === "object" && pq?.quote) || clean.description.slice(0, 200)), url: null, reviewReason: null,
    });
  }

  // dedupe: a bare "Size" like 14x1 duplicates structured Diameter/Arbor
  if (ledger.some((l) => l.label.toLowerCase() === "diameter")) {
    const sizeIdx = ledger.findIndex(
      (l) => l.label.toLowerCase() === "size" && /\d\s*[xX]\s*\d/.test(l.value)
    );
    if (sizeIdx !== -1) ledger.splice(sizeIdx, 1);
  }

  // physics on numeric attrs
  const checks = physicsChecks(ledger);
  const violated = new Set(checks.filter((c) => c.status === "UNSAT").flatMap((c) => [] as string[]));
  void violated;
  if (checks.some((c) => c.status === "UNSAT")) flags.push("PHYSICS_VIOLATION", "NEEDS_REVIEW");
  for (const l of ledger) {
    const bad = checks.find((c) => c.status === "UNSAT" && c.reason?.toLowerCase().includes(l.label.toLowerCase().split(" ")[0] ?? "#"));
    if (bad) l.reviewReason = l.reviewReason ?? bad.reason;
  }
  if (ledger.every((l) => l.verdict === "UNSUPPORTED") && ledger.length > 0) flags.push("NEEDS_REVIEW");

  // 5) descriptions from the verified ledger
  const itemRaw = String(data.item_type ?? "Product");
  const classData = await classifySafe(itemRaw, clean);
  const descs = buildDescriptions({
    brand: brand ? maybeMark(brand) : null,
    manuf: manufacturer,
    mpn,
    itemType: itemRaw === "Product" && classData.classpath ? classData.classpath.split(">").pop()!.replace(/s$/, "") : itemRaw,
    series: data.series ?? null,
    feature: (data.features ?? [])[0] ?? null,
    attributes: ledger,
    additional: data.additional ?? null,
  });

  // 6) Unilog asset conventions once the maker's page is confirmed
  const assets: Record<string, string> = {};
  const brandFile = (brand ?? manufacturer ?? "").replace(/[^A-Za-z0-9]+/g, "").toUpperCase();
  const mpnFile = mpn.replace(/[^A-Za-z0-9]+/g, "").toUpperCase();
  const mfrUrl = cleanU(retrieval.productUrl) ?? cleanU(retrieval.mfr_url ?? null);
  if (brandFile && mpnFile && mfrUrl) {
    assets["MFR URL"] = mfrUrl;
    assets["Product Image"] = `${brandFile}_${mpnFile}.jpg`;
    assets["Alternate Image 1"] = `${brandFile}_${mpnFile}_1.jpg`;
    assets["Alternate Image 2"] = `${brandFile}_${mpnFile}_2.jpg`;
    assets["Alternate Image 3"] = `${brandFile}_${mpnFile}_3.jpg`;
    assets["Alternate Image 4"] = `${brandFile}_${mpnFile}_4.jpg`;
    assets["Specification Sheet"] = `${brandFile}_${mpnFile}_Specification_Sheet.pdf`;
    assets["Actual Image (Yes/No)"] = "Yes";
    retrieval.refUrls.slice(0, 5).forEach((u, i) => (assets[`Ref URL ${i + 1}`] = u));
  }

  return {
    mpn,
    shortDesc: descs.short,
    longDesc: descs.long,
    classpath: classData.classpath,
    unspsc: classData.unspsc ?? "",
    brand: brand ? maybeMark(brand) : manufacturer ?? "",
    manufacturer: manufacturer ?? "",
    invoiceDesc: descs.invoice,
    mobileDesc: descs.mobile,
    retailDesc: descs.retail,
    flags,
    triage: flags.includes("NEEDS_REVIEW") ? 0.6 : 0.2,
    physics: checks,
    retrieval: {
      mfrUrl: cleanU(retrieval.mfr_url ?? null),
      productUrl: cleanU(retrieval.productUrl),
      refUrls: retrieval.refUrls,
      flags: retrieval.flags,
    },
    assets,
    attributes: ledger.map((l) => ({
      label: l.label, value: l.value, uom: l.uom, verdict: l.verdict,
      confidence: l.confidence, quote: l.quote, url: l.url, reviewReason: l.reviewReason ?? null,
    })),
    additional: data.additional ?? null,
  };
}

function cleanU(u: string | null | undefined): string | null {
  if (!u) return null;
  const t = u.trim();
  if (!/^https?:\/\/./.test(t)) return null;
  try {
    return new URL(t).hostname.includes(".") ? t : null;
  } catch {
    return null;
  }
}

function maybeMark(b: string): string {
  return b.includes("®") || b.includes("™") ? b : `${b}®`;
}

async function classifySafe(itemType: string, clean: CleanInput): Promise<{ classpath: string; unspsc: string | null }> {
  try {
    const data = await geminiJson(
      `Classify this industrial product into a distributor taxonomy.
Product: ${clean.description}
Item type hint: ${itemType}
Supplier: ${clean.supplierName ?? "unknown"}
Output STRICT JSON: {"dept":"...","klass":"...","fine":"...","classpath":"Dept > Class > Fine","unspsc":"6 digits or null"}
Example: {"classpath":"Appliances & Consumer Electronics>Kitchen Appliances>Built-In Dishwashers","unspsc":"42172203"}`,
      "You are an industrial product taxonomy specialist. Output STRICT JSON only."
    );
    if (data?.classpath) {
      return { classpath: String(data.classpath), unspsc: data.unspsc ? String(data.unspsc) : null };
    }
  } catch { /* degrade */ }
  return { classpath: "", unspsc: null };
}

export async function enrichMany(inputs: CloudInput[], concurrency = 3): Promise<CloudRow[]> {
  const out: CloudRow[] = new Array(inputs.length);
  let cursor = 0;
  async function worker() {
    while (cursor < inputs.length) {
      const i = cursor++;
      try {
        out[i] = await enrichOne(inputs[i]);
      } catch (e: any) {
        out[i] = {
          mpn: inputs[i].mpn,
          shortDesc: "", longDesc: "", classpath: "", unspsc: "",
          brand: "", manufacturer: inputs[i].supplier ?? "",
          invoiceDesc: "", mobileDesc: "", retailDesc: "",
          flags: ["NEEDS_REVIEW", `PIPELINE_ERROR:${e?.message?.slice(0, 60) ?? "unknown"}`],
          triage: 1, physics: null, retrieval: null, assets: {}, attributes: [],
          additional: null,
        };
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, inputs.length) }, worker));
  return out;
}
