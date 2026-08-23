/**
 * Builds a full 252-column Delivery Format record from an enriched row plus
 * the original input echo — the exact structure of the challenge's expected
 * output. Single source of truth for CSV downloads on every surface.
 */
import { DELIVERY_HEADERS } from "./delivery-headers";
import type { JobResultRow } from "@/components/record-card";

export type InputEcho = {
  mpn: string;
  description: string;
  brandRaw: string; // as the user typed it (may be placeholder or supplier)
  supplierRaw: string;
};

function attrMap(row: JobResultRow): Map<string, { value: string; uom: string }> {
  const m = new Map<string, { value: string; uom: string }>();
  for (const a of row.attributes) {
    if (!m.has(a.label.toLowerCase()))
      m.set(a.label.toLowerCase(), { value: a.value, uom: a.uom ?? "" });
  }
  return m;
}

const PLACEHOLDERS = ["-- Unbranded --", "-- No Unilog Brand --", "-- No DIB Brand --"];

export function buildDeliveryRecord(
  row: JobResultRow,
  echo: InputEcho
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const h of DELIVERY_HEADERS) out[h] = "";
  const attrs = attrMap(row);
  const get = (label: string) => attrs.get(label.toLowerCase());

  // passthrough block exactly as supplied
  out["Mfg_Part_Num"] = echo.mpn;
  out["Part_Desc"] = echo.description;
  out["E1_Brand"] = echo.brandRaw || "-- Unbranded --";
  out["Unilog_Brand"] = "-- No Unilog Brand --";
  out["DIB_Brand"] = "-- No DIB Brand --";
  out["Part_Manuf"] = echo.supplierRaw || "-";

  // identity
  out["MANUFACTURER_NAME"] = row.manufacturer || echo.supplierRaw.replace(/\s*\([^)]*\)\s*$/, "") || "";
  out["BRAND_NAME"] = row.brand || out["MANUFACTURER_NAME"];
  out["TRADE_NAME"] =
    row.brand && row.manufacturer && row.brand !== row.manufacturer ? row.brand : "";
  out["MANUFACTURER_PART_NUMBER"] = echo.mpn;

  // classification
  out["Classpath"] = row.classpath;
  out["UNSPSC"] = row.unspsc;

  // descriptions — all five formats
  out["MOBILE_DESC"] = row.mobileDesc;
  out["INVOICE_DESC"] = row.invoiceDesc;
  out["SHORT_DESC"] = row.shortDesc;
  out["LONG_DESC1"] = row.longDesc;
  out["RETAIL_DESC"] = row.retailDesc;
  out["MARKETING_DESCRIPTION"] = row.retailDesc;

  // attribute triplets (official layout)
  row.attributes.slice(0, 50).forEach((a: { label: string; value: string; uom: string | null }, i: number) => {
    const n = i + 1;
    out[`ATTRIBUTE_LABEL ${n}`] = a.label;
    out[`ATTRIBUTE_VALUE ${n}`] = a.value;
    out[`ATTRIBUTE_UOM ${n}`] = a.uom ?? "";
  });

  // scalar columns mapped from well-known attributes
  const setIf = (header: string, v: string | undefined | null) => {
    if (v) out[header] = v;
  };
  const warranty = get("warranty");
  if (warranty) {
    setIf("Warranty", warranty.value);
    setIf("Warranty Information", warranty.value);
  }
  const coo = get("country of origin");
  setIf("Country Of Origin", coo?.value);
  const upc = get("upc");
  if (upc?.value && /^\d{8,14}$/.test(upc.value)) out["UPC"] = upc.value;
  const pq = get("package quantity");
  if (pq?.value && /^\d+$/.test(pq.value)) {
    out["Selling Qty"] = pq.value;
    out["Selling UOM"] = "each";
  }
  const dims: Array<[string, string, string]> = [
    ["length", "LENGTH", "LENGTH_UOM"],
    ["height", "HEIGHT", "HEIGHT_UOM"],
    ["width", "WIDTH", "WIDTH_UOM"],
    ["weight", "WEIGHT", "WEIGHT_UOM"],
  ];
  for (const [label, col, uomCol] of dims) {
    const d = get(label);
    if (d) {
      out[col] = d.value;
      out[uomCol] = d.uom;
    }
  }

  // sourcing + Unilog asset conventions
  const pick = (...urls: Array<string | null | undefined>) =>
    urls.find((u) => u && u !== "https://" && /^https:\/\/.+/.test(u)) ?? "";
  out["MFR URL"] = pick(row.retrieval?.productUrl, row.assets["MFR URL"], row.retrieval?.mfrUrl);
  let slot = 1;
  for (const u of row.retrieval?.refUrls ?? []) {
    if (slot > 5) break;
    if (u && !Object.values(out).includes(u)) {
      out[`Ref URL ${slot}`] = u;
      slot += 1;
    }
  }
  for (const [k, v] of Object.entries(row.assets)) {
    if (k === "MFR URL" || k.startsWith("Ref URL")) continue;
    out[k] = v;
  }
  if (out["Product Image"]) out["Actual Image (Yes/No)"] = "Yes";

  return out;
}

export function buildDeliveryCsv(pairs: Array<[JobResultRow, InputEcho]>): string {
  const rows = pairs.map(([row, echo]) => buildDeliveryRecord(row, echo));
  const esc = (v: string) => (/["\n,]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  const lines = [DELIVERY_HEADERS.join(",")];
  for (const r of rows) lines.push(DELIVERY_HEADERS.map((h) => esc(r[h] ?? "")).join(","));
  // UTF-8 BOM so Excel renders ® / ™ correctly on double-click
  return "\uFEFF" + lines.join("\r\n") + "\r\n";
}
