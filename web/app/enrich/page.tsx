"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Card, Btn, PageTitle } from "@/components/ui";
import { RecordCard, type JobResultRow } from "@/components/record-card";
import { buildDeliveryCsv, type InputEcho } from "@/lib/delivery-export";
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
  const [echoes, setEchoes] = useState<InputEcho[]>([]);

  function downloadCsv() {
    if (!rows?.length) return;
    const pairs = rows.map((row, i) => [
      row,
      echoes[i] ?? {
        mpn: row.mpn,
        description: "",
        brandRaw: "",
        supplierRaw: "",
      },
    ] as [JobResultRow, InputEcho]);
    const blob = new Blob([buildDeliveryCsv(pairs)], {
      type: "text/csv;charset=utf-8",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "delivery-format.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const [progress, setProgress] = useState<string | null>(null);

  async function post(resPromise: Promise<Response>) {
    setBusy(true);
    setError(null);
    try {
      const response = await resPromise;
      const body = await response.json().catch(() => ({}));
      if (!response.ok || !body.rows) {
        setError(body.error ?? `Something went wrong (${response.status}).`);
        return null;
      }
      return body;
    } catch {
      setError("Could not reach the server. Try again.");
      return null;
    }
  }

  async function submitSingle() {
    setProgress("Enriching…");
    const res = post(
      fetch("/api/enrich", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mpn, description, brand, supplier }),
      })
    );
    const body = await res;
    if (body?.rows) {
      setRows(body.rows as JobResultRow[]);
      setTimeout(() => window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }), 50);
    }
    setBusy(false); setProgress(null);
  }

  async function submitFile() {
    if (!file) { setBusy(false); return; }
    setProgress("Reading file…");
    const text = await file.text();
    const lines = text.split(/\r?\n/).filter(l => l.trim());
    if (lines.length < 2) { setError("File has no data rows."); setBusy(false); return; }

    // Parse CSV
    const parseLine = (line: string): string[] => {
      const cells: string[] = []; let cur = ""; let q = false;
      for (const ch of line) {
        if (ch === '"') q = !q;
        else if (ch === "," && !q) { cells.push(cur); cur = ""; }
        else cur += ch;
      }
      cells.push(cur); return cells.map(c => c.trim());
    };
    const headers = parseLine(lines[0]).map(h => h.toLowerCase().trim());
    const iMpn = headers.findIndex(h => ["mfg_part_num","mpn","part number","sku"].includes(h));
    const iDesc = headers.findIndex(h => ["part_desc","description","desc","product description"].includes(h));
    const iSup = headers.findIndex(h => ["part_manuf","manufacturer","supplier","vendor"].includes(h));
    const iE1 = headers.findIndex(h => h === "e1_brand");
    const iUnilog = headers.findIndex(h => h === "unilog_brand");
    const iDib = headers.findIndex(h => h === "dib_brand");
    if (iMpn === -1 || iDesc === -1) { setError("Need part-number and description columns."); setBusy(false); return; }
    const PLACEHOLDERS = new Set(["-- unbranded --", "-- no unilog brand --", "-- no dib brand --", "-"]);
    const hint = (cells: string[], idx: number): string | undefined => {
      if (idx < 0) return undefined;
      const v = cells[idx]?.trim();
      return v && !PLACEHOLDERS.has(v.toLowerCase()) ? v : undefined;
    };

    // Build all data rows
    const allRows: Array<{mpn:string;description:string;supplier?:string;brand?:string;e1_brand?:string;unilog_brand?:string}> = [];
    for (let i = 1; i < lines.length; i++) {
      const cells = parseLine(lines[i]);
      const mpnVal = cells[iMpn]?.trim(); const descVal = cells[iDesc]?.trim();
      if (mpnVal || descVal) allRows.push({
        mpn: mpnVal || descVal.slice(0,24),
        description: descVal,
        supplier: hint(cells, iSup),
        brand: hint(cells, iDib),
        e1_brand: hint(cells, iE1),
        unilog_brand: hint(cells, iUnilog),
      });
    }

    if (!allRows.length) { setError("No usable rows found."); setBusy(false); return; }

    // Process ONE product per API call — avoids serverless timeout
    const accumulated: JobResultRow[] = [];
    const accumulatedEchoes: InputEcho[] = [];
    for (let i = 0; i < allRows.length; i++) {
      const r = allRows[i];
      setProgress(`Enriching ${i + 1} of ${allRows.length}: ${r.mpn}…`);
      // Retry with backoff — Render's free instance can recycle between
      // rows; an instant 502 must not silently drop the row.
      let body: any = null;
      for (let attempt = 0; attempt < 3 && !body?.rows?.[0]; attempt++) {
        if (attempt > 0) {
          setProgress(`Service waking up — retrying ${r.mpn} (attempt ${attempt + 1}/3)…`);
          await new Promise(res => setTimeout(res, 8000 * attempt));
        }
        try {
          const res = await fetch("/api/enrich", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(r),
          });
          body = await res.json().catch(() => null);
        } catch {
          body = null;
        }
      }
      if (body?.rows?.[0]) {
        accumulated.push(body.rows[0] as JobResultRow);
        setRows([...accumulated]);
      }
    }

    setProgress(`Done — ${accumulated.length} products enriched`);
    setTimeout(() => window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }), 50);
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
    
      {progress && (
        <p className="mt-3 rounded border border-accent/30 bg-accent/5 px-3 py-2 font-mono text-xs text-accent">
          {progress}
        </p>
      )}

      {rows && rows.length > 0 && (
        <div className="mt-8 flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-fg">
              Enriched records — {rows.length} row{rows.length === 1 ? "" : "s"}
            </h2>
            <Btn onClick={downloadCsv}>Download Delivery Format CSV</Btn>
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