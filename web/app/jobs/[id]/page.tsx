"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Chip } from "@/components/ui";

type JobStatus = {
  id: string;
  name: string;
  status: "QUEUED" | "RUNNING" | "DONE" | "FAILED" | "CANCELLED";
  createdAt: string;
  inputRows: number;
  processed: number;
  lastLog: string;
  error?: string;
  artifactsReady?: boolean;
};

type Attr = {
  label: string;
  value: string;
  uom: string | null;
  verdict?: string;
  confidence?: number;
  quote?: string | null;
  url?: string | null;
  reviewReason?: string | null;
};

type RowResult = {
  mpn: string;
  shortDesc: string;
  longDesc: string;
  classpath: string;
  unspsc: string;
  brand: string;
  manufacturer: string;
  invoiceDesc: string;
  mobileDesc: string;
  retailDesc: string;
  flags: string[];
  triage: number;
  physics: Array<{ name: string; status: string; reason: string | null }> | null;
  retrieval: {
    mfrUrl: string | null;
    productUrl: string | null;
    refUrls: string[];
    flags: string[];
  } | null;
  assets: Record<string, string>;
  attributes: Attr[];
};

const DESCRIPTIONS: Array<[string, keyof RowResult]> = [
  ["Search title", "shortDesc"],
  ["Long description", "longDesc"],
  ["Mobile description", "mobileDesc"],
  ["Invoice description", "invoiceDesc"],
  ["Retail description", "retailDesc"],
];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard?.writeText(text).then(
          () => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          },
          () => undefined
        );
      }}
      className="font-mono text-[10px] text-ink2 underline decoration-line underline-offset-4 hover:text-ink"
    >
      {copied ? "copied" : "copy"}
    </button>
  );
}

function Url({ v, max = 80 }: { v: string; max?: number }) {
  return (
    <a
      href={v}
      target="_blank"
      rel="noreferrer"
      className="break-all text-accent underline decoration-accent/40 underline-offset-4 hover:decoration-accent"
    >
      {v.length > max ? `${v.slice(0, max)}…` : v}
    </a>
  );
}

function AssetBlock({ row }: { row: RowResult }) {
  const entries = Object.entries(row.assets);
  const extraRefs = (row.retrieval?.refUrls ?? [])
    .filter((u) => !Object.values(row.assets).includes(u))
    .slice(0, 3);
  const nothing = entries.length === 0 && extraRefs.length === 0;
  return (
    <dl className="mt-3 flex flex-col gap-1 rounded-[3px] border border-line bg-paper p-3 font-mono text-[11px]">
      {entries
        .filter(([k]) => k === "MFR URL")
        .map(([k, v]) => (
          <div key={k} className="grid grid-cols-[120px_1fr] gap-2">
            <dt className="text-ink2">{k}</dt>
            <dd className="break-all">
              <Url v={v} max={90} />
            </dd>
          </div>
        ))}
      {extraRefs.map((u) => (
        <div key={u} className="grid grid-cols-[120px_1fr] gap-2">
          <dt className="text-ink2">source doc</dt>
          <dd className="break-all">
            <Url v={u} max={80} />
          </dd>
        </div>
      ))}
      {entries
        .filter(([k]) => k !== "MFR URL")
        .map(([k, v]) => (
          <div key={k} className="grid grid-cols-[120px_1fr] gap-2">
            <dt className="text-ink2">{k}</dt>
            <dd className="break-all">
              {v.startsWith("http") ? <Url v={v} max={90} /> : v}
            </dd>
          </div>
        ))}
      {!row.assets["MFR URL"] && (
        <div className="grid grid-cols-[120px_1fr] gap-2">
          <dt className="text-ink2">MFR URL</dt>
          <dd className="text-warn">
            not found —{" "}
            {(row.retrieval?.flags ?? []).join(", ") ||
              "no manufacturer page located for this part"}
          </dd>
        </div>
      )}
      {nothing && null}
    </dl>
  );
}

function RecordCard({ row }: { row: RowResult }) {
  const [open, setOpen] = useState(false);

  return (
    <li className="rounded-[3px] border border-line bg-panel">
      <div className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-mono text-sm font-semibold">{row.mpn}</span>
          <div className="flex items-center gap-2">
            {row.flags.includes("PHYSICS_VIOLATION") && (
              <Chip tone="bad">physics fail</Chip>
            )}
            <Chip tone={row.triage >= 0.5 ? "warn" : "ok"}>
              triage {row.triage.toFixed(2)}
            </Chip>
          </div>
        </div>
        {row.shortDesc && <p className="mt-1.5 text-sm">{row.shortDesc}</p>}
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] text-ink2">
          {row.brand && <span>brand {row.brand}</span>}
          {row.manufacturer && <span>mfr {row.manufacturer}</span>}
          {row.classpath && (
            <span className="max-w-md truncate">{row.classpath}</span>
          )}
          {row.unspsc && <span>UNSPSC {row.unspsc}</span>}
        </div>

        <AssetBlock row={row} />

        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="mt-3 font-mono text-[11px] text-accent underline decoration-accent/40 underline-offset-4 hover:decoration-accent"
        >
          {open
            ? "▲ hide full record"
            : "▼ full record — descriptions, attributes, provenance, physics"}
        </button>

        {open && (
          <div className="mt-3 border-t border-line pt-3">
            <h4 className="font-mono text-[10px] uppercase tracking-wider text-ink2">
              Five descriptions
            </h4>
            <div className="mt-1.5 flex flex-col gap-1.5">
              {DESCRIPTIONS.map(([label, key]) => {
                const value = String(row[key] ?? "");
                return (
                  <div
                    key={label}
                    className="grid grid-cols-[130px_1fr_auto] items-start gap-3"
                  >
                    <span className="pt-0.5 font-mono text-[10px] uppercase text-ink2">
                      {label}
                    </span>
                    <span className="text-xs leading-snug">{value || "—"}</span>
                    {value && <CopyButton text={value} />}
                  </div>
                );
              })}
            </div>

            <h4 className="mt-4 font-mono text-[10px] uppercase tracking-wider text-ink2">
              Attribute ledger — every value with its proof
            </h4>
            {row.attributes.length === 0 ? (
              <p className="mt-1 text-xs text-ink2">
                No attributes could be verified for this part.
              </p>
            ) : (
              <table className="mt-1.5 w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-line font-mono text-[10px] uppercase text-ink2">
                    <th className="py-1.5 pr-3 font-medium">Attribute</th>
                    <th className="py-1.5 pr-3 font-medium">Value</th>
                    <th className="py-1.5 pr-3 font-medium">Verdict</th>
                    <th className="py-1.5 font-medium">Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {row.attributes.map((a) => (
                    <tr
                      key={a.label}
                      className="border-b border-line last:border-b-0 align-top"
                    >
                      <td className="py-1.5 pr-3 text-ink2">{a.label}</td>
                      <td className="py-1.5 pr-3 font-mono">
                        {a.value}
                        {a.uom ? ` ${a.uom}` : ""}
                      </td>
                      <td className="whitespace-nowrap py-1.5 pr-3">
                        <Chip
                          tone={
                            a.verdict === "CONFIRMED"
                              ? "ok"
                              : a.verdict === "REFUTED"
                                ? "bad"
                                : "warn"
                          }
                        >
                          {(a.verdict ?? "—").replace("_", " ")} ·{" "}
                          {(a.confidence ?? 0).toFixed(2)}
                        </Chip>
                        {a.reviewReason && (
                          <div className="mt-0.5 max-w-[220px] text-bad/80">
                            {a.reviewReason}
                          </div>
                        )}
                      </td>
                      <td className="py-1.5">
                        {a.url ? (
                          <Url v={a.url} max={60} />
                        ) : (
                          <span className="text-ink2">input row</span>
                        )}
                        {a.quote && (
                          <details className="mt-0.5">
                            <summary className="cursor-pointer select-none text-ink2 hover:text-ink">
                              quote
                            </summary>
                            <blockquote className="mt-0.5 border-l-2 border-line pl-2 text-ink2">
                              {a.quote.slice(0, 300)}
                            </blockquote>
                          </details>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {row.physics && row.physics.length > 0 && (
              <>
                <h4 className="mt-4 font-mono text-[10px] uppercase tracking-wider text-ink2">
                  Z3 physics dossier
                </h4>
                <ul className="mt-1.5 flex flex-col gap-1">
                  {row.physics.map((c) => (
                    <li key={c.name} className="flex items-start justify-between gap-3 text-xs">
                      <span className="font-mono">{c.name}</span>
                      <span className="flex items-center gap-2">
                        {c.reason && (
                          <span className="max-w-md text-bad/90">{c.reason}</span>
                        )}
                        <Chip
                          tone={
                            c.status === "SAT"
                              ? "ok"
                              : c.status === "UNSAT"
                                ? "bad"
                                : "neutral"
                          }
                        >
                          {c.status}
                        </Chip>
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

export default function JobPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [job, setJob] = useState<JobStatus | null>(null);
  const [results, setResults] = useState<RowResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let loadedResults = false;
    async function poll() {
      try {
        const res = await fetch(`/api/jobs/${id}`, { cache: "no-store" });
        if (!res.ok) {
          if (alive)
            setError(res.status === 404 ? "Job not found." : "Status unavailable.");
          return;
        }
        const data: JobStatus = await res.json();
        if (!alive) return;
        setJob(data);
        const finished = data.status === "DONE" || data.artifactsReady;
        if (finished && !loadedResults) {
          loadedResults = true;
          const fres = await fetch(`/api/jobs/${id}/results`, { cache: "no-store" });
          if (fres.ok && alive) setResults(await fres.json());
        }
      } catch {
        /* transient */
      }
    }
    void poll();
    const t = setInterval(() => {
      if (!loadedResults) void poll();
    }, 2000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [id]);

  if (error) {
    return (
      <section className="mx-auto max-w-xl border border-line bg-panel p-8">
        <h1 className="font-sans text-base font-semibold">{error}</h1>
        <Link
          href="/enrich"
          className="mt-4 inline-block font-mono text-xs text-accent underline underline-offset-4"
        >
          ← Start another enrichment
        </Link>
      </section>
    );
  }

  if (!job) {
    return <p className="font-mono text-xs text-ink2">Loading job…</p>;
  }

  const pct =
    job.inputRows > 0 ? Math.round((job.processed / job.inputRows) * 100) : 0;
  const done = job.status !== "RUNNING" && job.status !== "QUEUED";

  return (
    <section className="mx-auto max-w-3xl">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <Link
            href="/enrich"
            className="font-mono text-xs text-ink2 underline decoration-line underline-offset-4 hover:text-ink"
          >
            ← Enrich more products
          </Link>
          <h1 className="mt-2 truncate font-mono text-lg font-semibold">
            {job.name}
          </h1>
        </div>
        <span
          className={`font-mono text-sm font-semibold ${
            job.status === "RUNNING"
              ? "text-accent"
              : job.status === "DONE"
                ? "text-ok"
                : job.status === "FAILED"
                  ? "text-bad"
                  : "text-ink2"
          }`}
        >
          {job.status}
        </span>
      </div>

      <div className="mt-4 rounded-[3px] border border-line bg-panel p-4">
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-line">
          <div
            className={`h-full transition-all ${
              job.status === "RUNNING" ? "animate-pulse bg-accent" : done ? "bg-ok" : ""
            }`}
            style={{ width: `${done ? 100 : Math.max(pct, 4)}%` }}
          />
        </div>
        <div className="mt-2 flex justify-between font-mono text-[11px] text-ink2">
          <span>
            {job.processed} / {job.inputRows} rows
          </span>
          {job.lastLog && (
            <span className="max-w-[65%] truncate" title={job.lastLog}>
              {job.lastLog}
            </span>
          )}
        </div>
        {job.error && <p className="mt-2 text-sm text-bad">{job.error}</p>}
      </div>

      {done && results && results.length === 0 && (
        <p className="mt-6 rounded-[3px] border border-line bg-panel p-5 text-sm text-ink2">
          The run completed but produced no enriched records. Check the run log
          for quota or input-format issues.
        </p>
      )}

      {done && results && (
        <>
          <div className="mt-5 flex flex-wrap gap-3">
            <a
              href={`/api/download/result.csv?job=${job.id}`}
              className="rounded-[3px] bg-accent px-4 py-2 font-mono text-xs font-semibold text-white hover:bg-accent/90"
            >
              Download result.csv
            </a>
            <a
              href={`/api/download/result.xlsx?job=${job.id}`}
              className="rounded-[3px] border border-line bg-panel px-4 py-2 font-mono text-xs font-semibold hover:border-ink"
            >
              result.xlsx
            </a>
            <a
              href={`/api/download/sidecar.jsonl?job=${job.id}`}
              className="rounded-[3px] border border-line bg-panel px-4 py-2 font-mono text-xs font-semibold hover:border-ink"
            >
              sidecar.jsonl (provenance)
            </a>
          </div>

          <h2 className="mt-6 font-mono text-[10px] uppercase tracking-wider text-ink2">
            Enriched records — expand for the full verified record
          </h2>
          <ul className="mt-2 flex flex-col gap-3">
            {results.map((r) => (
              <RecordCard key={r.mpn} row={r} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
