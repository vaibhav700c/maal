"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Card, Btn, PageTitle } from "@/components/ui";
import { RecordCard, type JobResultRow } from "@/components/record-card";
import RevealOnMount from "@/components/reveal";

export default function EnrichPage() {
  const router = useRouter();
  const [mpn, setMpn] = useState("");
  const [description, setDescription] = useState("");
  const [brand, setBrand] = useState("");
  const [supplier, setSupplier] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rows, setRows] = useState<JobResultRow[] | null>(null);

  async function downloadCsv() {
    if (!rows?.length) return;
    const headers = ["mpn", "classpath", "unspsc", "brand", "manufacturer",
      "invoiceDesc", "mobileDesc", "shortDesc", "longDesc", "retailDesc"];
    for (let i = 1; i <= Math.max(...rows.map((r) => r.attributes.length)); i++) {
      headers.push(`attr${i}_label`, `attr${i}_value`, `attr${i}_uom`);
    }
    const esc = (v: string) => (/["\n,]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
    const lines = [headers.join(",")];
    for (const r of rows) {
      const base: Record<string, string> = {
        mpn: r.mpn, classpath: r.classpath, unspsc: r.unspsc,
        brand: r.brand, manufacturer: r.manufacturer,
        invoiceDesc: r.invoiceDesc, mobileDesc: r.mobileDesc,
        shortDesc: r.shortDesc, longDesc: r.longDesc, retailDesc: r.retailDesc,
      };
      const cells = headers.map((h) => {
        if (h in base) return esc(base[h]);
        const m = /attr(\d+)_(label|value|uom)/.exec(h);
        if (m) return esc(r.attributes[Number(m[1]) - 1]?.[(m[2] as "label" | "value" | "uom")] ?? "");
        return "";
      });
      lines.push(cells.join(","));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "enriched.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function post(resPromise: Promise<Response>) {
    setBusy(true);
    setError(null);
    setRows(null);
    try {
      const response = await resPromise;
      const body = await response.json().catch(() => ({}));
      if (!response.ok || !body.rows) {
        setError(body.error ?? `Something went wrong (${response.status}).`);
        return;
      }
      setRows(body.rows as JobResultRow[]);
      setTimeout(() => window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }), 50);
    } catch {
      setError("Could not reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function submitSingle() {
    await post(
      fetch("/api/enrich", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mpn, description, brand, supplier }),
      })
    );
  }

  async function submitFile() {
    const form = new FormData();
    if (file) form.append("file", file);
    await post(fetch("/api/enrich", { method: "POST", body: form }));
  }

  return (
    <section className="mx-auto max-w-4xl">
      <RevealOnMount />
      <div className="reveal">
        <PageTitle
          title="Enrich products"
          sub="Send one product or a whole spreadsheet. Every value comes back with its source, an audit verdict, and a physics check."
        />
      </div>

      {error && <p className="mt-4 text-sm text-bad">{error}</p>}

      <div className="mt-8 grid gap-6 md:grid-cols-2 md:items-start">
        <Card>
          <h2 className="font-display text-xl font-semibold tracking-tight text-fg">
            Single product
          </h2>
          <p className="mt-1 text-sm text-fg-dim">
            Enrich one part number with its raw description.
          </p>
          <form
            className="mt-5 flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              void submitSingle();
            }}
          >
            <Field label="Part number *">
              <input
                value={mpn}
                onChange={(e) => setMpn(e.target.value)}
                placeholder="e.g. PDSH4816AF"
                className="w-full rounded-md border border-line bg-surface-2 px-3 py-2 font-mono text-[13px] text-fg placeholder:text-fg-faint focus:border-accent focus:outline-none"
              />
            </Field>
            <Field label="Raw description *">
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                placeholder='e.g. PDSH4816AF Dishwasher SS, Display Only'
                className="w-full rounded-md border border-line bg-surface-2 px-3 py-2 font-mono text-[13px] text-fg placeholder:text-fg-faint focus:border-accent focus:outline-none"
              />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Brand, optional">
                <input
                  value={brand}
                  onChange={(e) => setBrand(e.target.value)}
                  placeholder="e.g. Frigidaire"
                  className="w-full rounded-md border border-line bg-surface-2 px-3 py-2 font-mono text-[13px] text-fg placeholder:text-fg-faint focus:border-accent focus:outline-none"
                />
              </Field>
              <Field label="Supplier, optional">
                <input
                  value={supplier}
                  onChange={(e) => setSupplier(e.target.value)}
                  placeholder="e.g. Acme Supply Co"
                  className="w-full rounded-md border border-line bg-surface-2 px-3 py-2 font-mono text-[13px] text-fg placeholder:text-fg-faint focus:border-accent focus:outline-none"
                />
              </Field>
            </div>
            <Btn
              type="submit"
              disabled={!mpn.trim() || !description.trim() || busy}
              className="self-start"
            >
              {busy ? "Running live enrichment…" : "Enrich now"}
            </Btn>
          </form>
        </Card>

        <Card>
          <h2 className="font-display text-xl font-semibold tracking-tight text-fg">
            Upload a file
          </h2>
          <p className="mt-1 text-sm text-fg-dim">
            Drop a spreadsheet with a part-number column and a description
            column.
          </p>
          <label
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              setFile(e.dataTransfer.files?.[0] ?? null);
            }}
            className={`mt-5 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border border-dashed px-6 py-10 text-center transition-colors duration-150 ease-out ${
              dragOver
                ? "border-accent bg-accent/5"
                : "border-line bg-surface-2 hover:border-line-2"
            }`}
          >
            <span className="font-mono text-sm text-fg">
              {file ? file.name : "Drop or choose a .csv, .xlsx or .tsv file"}
            </span>
            <span className="max-w-xs text-xs text-fg-dim">
              Needs a part-number column and a description column. Other
              columns are optional and auto-detected.
            </span>
            <input
              type="file"
              accept=".csv,.xlsx,.xls,.tsv,.txt"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <span className="rounded-full border border-line px-3 py-1 font-mono text-xs text-fg-dim">
              Browse files
            </span>
          </label>
          <Btn
            type="button"
            onClick={() => void submitFile()}
            disabled={!file || busy}
            className="mt-4 self-start"
          >
            {busy ? "Starting enrichment..." : "Upload catalog"}
          </Btn>
        </Card>
      </div>
    
      {rows && rows.length > 0 && (
        <div className="mt-8 flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-fg">
              Enriched records — {rows.length} row{rows.length === 1 ? "" : "s"}
            </h2>
            <Btn onClick={downloadCsv}>Download enriched.csv</Btn>
          </div>
          <ul className="flex flex-col gap-3">
            {rows.map((r) => (
              <RecordCard key={r.mpn} row={r} />
            ))}
          </ul>
          {rows.some((r) => r.flags.includes("NEEDS_REVIEW")) && (
            <p className="text-xs text-fg-dim">
              Rows flagged NEEDS_REVIEW had values the pipeline could not verify
              against a manufacturer source. They are marked, never invented.
            </p>
          )}
        </div>
      )}
    </section>

  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs text-fg-faint">{label}</span>
      {children}
    </label>
  );
}