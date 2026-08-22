"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

type JobStatus = {
  id: string;
  name: string;
  status: "QUEUED" | "RUNNING" | "DONE" | "FAILED" | "CANCELLED";
  kind: string;
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
};

type RowResult = {
  mpn: string;
  shortDesc: string;
  longDesc: string;
  classpath: string;
  brand: string;
  attributes: Attr[];
};

const STATUS_TONE: Record<string, string> = {
  RUNNING: "text-accent",
  DONE: "text-ok",
  FAILED: "text-bad",
  CANCELLED: "text-ink2",
  QUEUED: "text-ink2",
};

export default function JobPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [job, setJob] = useState<JobStatus | null>(null);
  const [results, setResults] = useState<RowResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openRow, setOpenRow] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function poll() {
      try {
        const res = await fetch(`/api/jobs/${id}`, { cache: "no-store" });
        if (!res.ok) {
          if (alive) setError(res.status === 404 ? "Job not found." : "Status unavailable.");
          return;
        }
        const data: JobStatus = await res.json();
        if (!alive) return;
        setJob(data);
        if ((data.status === "DONE" || data.artifactsReady) && results === null) {
          const rres = await fetch(`/api/jobs/${id}`, { cache: "no-store" });
          // results come from the page's server component normally; here we
          // fetch through the same endpoint and then load results via API
          void rres;
          const fres = await fetch(`/api/jobs/${id}/results`, { cache: "no-store" });
          if (fres.ok && alive) setResults(await fres.json());
        }
      } catch {
        /* transient */
      }
    }
    void poll();
    const t = setInterval(() => {
      if (!job || job.status === "RUNNING") void poll();
    }, 2000);
    return () => {
      alive = false;
      clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (error) {
    return (
      <section className="mx-auto max-w-xl border border-line bg-panel p-8">
        <h1 className="font-sans text-base font-semibold">{error}</h1>
        <Link href="/enrich" className="mt-4 inline-block font-mono text-xs text-accent underline underline-offset-4">
          ← Start another enrichment
        </Link>
      </section>
    );
  }

  if (!job) {
    return <p className="font-mono text-xs text-ink2">Loading job…</p>;
  }

  const pct = job.inputRows > 0 ? Math.round((job.processed / job.inputRows) * 100) : 0;
  const done = job.status !== "RUNNING" && job.status !== "QUEUED";

  return (
    <section className="mx-auto max-w-3xl">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <Link href="/enrich" className="font-mono text-xs text-ink2 underline decoration-line underline-offset-4 hover:text-ink">
            ← Enrich more products
          </Link>
          <h1 className="mt-2 truncate font-mono text-lg font-semibold">{job.name}</h1>
        </div>
        <span className={`font-mono text-sm font-semibold ${STATUS_TONE[job.status] ?? ""}`}>
          {job.status}
        </span>
      </div>

      <div className="mt-4 rounded-[3px] border border-line bg-panel p-4">
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-line">
          <div
            className={`h-full transition-all ${job.status === "RUNNING" ? "bg-accent animate-pulse" : done ? "bg-ok" : "bg-line"}`}
            style={{ width: `${done || pct > 0 ? Math.max(pct, done ? 100 : pct) : 4}%` }}
          />
        </div>
        <div className="mt-2 flex justify-between font-mono text-[11px] text-ink2">
          <span>{job.processed} / {job.inputRows} rows</span>
          {job.lastLog && <span className="max-w-[70%] truncate" title={job.lastLog}>{job.lastLog}</span>}
        </div>
        {job.error && <p className="mt-2 text-sm text-bad">{job.error}</p>}
      </div>

      {done && (
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
            Enriched records
          </h2>
          {!results && (
            <p className="mt-2 font-mono text-xs text-ink2">Preparing preview…</p>
          )}
          <ul className="mt-2 flex flex-col gap-3">
            {(results ?? []).map((r) => (
              <li key={r.mpn} className="rounded-[3px] border border-line bg-panel">
                <button
                  type="button"
                  onClick={() => setOpenRow(openRow === r.mpn ? null : r.mpn)}
                  className="flex w-full flex-col items-start gap-1 p-4 text-left"
                >
                  <span className="font-mono text-sm font-semibold">{r.mpn}</span>
                  <span className="text-sm text-ink2">{r.shortDesc || "—"}</span>
                  {r.classpath && (
                    <span className="font-mono text-[10px] uppercase tracking-wide text-ink2">
                      {r.classpath}
                    </span>
                  )}
                </button>
                {openRow === r.mpn && (
                  <div className="border-t border-line px-4 py-3">
                    <p className="text-sm leading-snug">{r.longDesc || "Long description pending."}</p>
                    {r.attributes.length > 0 && (
                      <table className="mt-3 w-full text-left text-xs">
                        <thead>
                          <tr className="border-b border-line font-mono text-[10px] uppercase text-ink2">
                            <th className="py-1.5 pr-3 font-medium">Attribute</th>
                            <th className="py-1.5 pr-3 font-medium">Value</th>
                            <th className="py-1.5 font-medium">Provenance</th>
                          </tr>
                        </thead>
                        <tbody>
                          {r.attributes.map((a) => (
                            <tr key={a.label} className="border-b border-line last:border-b-0 align-top">
                              <td className="py-1.5 pr-3 text-ink2">{a.label}</td>
                              <td className="py-1.5 pr-3 font-mono">
                                {a.value}{a.uom ? ` ${a.uom}` : ""}
                              </td>
                              <td className="py-1.5 font-mono text-[10px] text-ink2">
                                [{(a.verdict ?? "—").replace("_", " ")} · {(a.confidence ?? 0).toFixed(2)}]
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
