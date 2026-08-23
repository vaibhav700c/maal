"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Btn, Card, Chip, Empty } from "@/components/ui";
import { RecordCard } from "@/components/record-card";
import type { JobResultRow } from "@/components/record-card";

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

const STATUS_TONE: Record<JobStatus["status"], string> = {
  QUEUED: "text-fg-dim",
  RUNNING: "text-accent",
  DONE: "text-ok",
  FAILED: "text-bad",
  CANCELLED: "text-fg-dim",
};

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
      <section className="mx-auto max-w-xl">
        <Empty
          title={error}
          hint="Start a new enrichment job from Enrich."
          action={<Btn href="/enrich">Enrich products</Btn>}
        />
      </section>
    );
  }

  if (!job) {
    return <p className="font-mono text-xs text-fg-dim">Loading job…</p>;
  }

  const pct =
    job.inputRows > 0 ? Math.round((job.processed / job.inputRows) * 100) : 0;
  const done = job.status !== "RUNNING" && job.status !== "QUEUED";
  const barTone =
    job.status === "RUNNING"
      ? "bg-accent"
      : job.status === "FAILED"
        ? "bg-bad"
        : done
          ? "bg-ok"
          : "bg-line-2";

  return (
    <section className="mx-auto flex max-w-3xl flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            href="/enrich"
            className="font-mono text-xs text-fg-dim underline decoration-line underline-offset-4 transition-colors duration-150 ease-out hover:text-fg focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
          >
            ← Enrich more products
          </Link>
          <h1 className="mt-2 truncate font-display text-2xl font-extrabold tracking-tight text-fg">
            {job.name}
          </h1>
        </div>
        <span className={`inline-flex items-center gap-2 font-mono text-sm font-semibold ${STATUS_TONE[job.status]}`}>
          {job.status === "RUNNING" && (
            <span className="pulse-dot h-2 w-2 rounded-full bg-accent" aria-hidden="true" />
          )}
          {job.status}
        </span>
      </div>

      <Card>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-line">
          <div
            className={`h-full transition-[width] duration-500 ease-out ${barTone}`}
            style={{ width: `${done ? 100 : Math.max(pct, 4)}%` }}
          />
        </div>
        <div className="mt-2 flex flex-wrap justify-between gap-2 font-mono text-[11px] text-fg-dim">
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
      </Card>

      {done && results && results.length === 0 && (
        <Empty
          title="Run completed with no enriched records"
          hint="Check the run log for quota or input-format issues, then try again from Enrich."
          action={<Btn href="/enrich">Enrich products</Btn>}
        />
      )}

      {done && results && results.length > 0 && (
        <>
          <div className="flex flex-wrap gap-3">
            <Btn href={`/api/download/result.csv?job=${job.id}`}>result.csv</Btn>
            <Btn variant="ghost" href={`/api/download/result.xlsx?job=${job.id}`}>
              result.xlsx
            </Btn>
            <Btn variant="ghost" href={`/api/download/sidecar.jsonl?job=${job.id}`}>
              sidecar.jsonl (provenance)
            </Btn>
          </div>

          <div>
            <h2 className="font-display text-xl font-semibold tracking-tight text-fg">
              Enriched records
            </h2>
            <p className="mt-1 text-xs text-fg-faint">
              Expand a record for the full verified record.
            </p>
            <ul className="mt-3 flex flex-col gap-3">
              {results.map((r) => (
                <RecordCard key={r.mpn} row={r} />
              ))}
            </ul>
          </div>
        </>
      )}
    </section>
  );
}
