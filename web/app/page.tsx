import Link from "next/link";
import { listJobs } from "@/lib/jobs";

const STATUS_TONE: Record<string, string> = {
  RUNNING: "text-accent",
  DONE: "text-ok",
  FAILED: "text-bad",
  CANCELLED: "text-ink2",
};

export default function HomePage() {
  const jobs = listJobs().slice(0, 6);

  return (
    <section className="mx-auto max-w-3xl">
      <div className="border-b border-line pb-8">
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-ink2">
          Industrial product intelligence
        </p>
        <h1 className="mt-2 max-w-xl font-sans text-2xl font-bold leading-tight">
          Turn raw part listings into verified, commerce-ready records.
        </h1>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-ink2">
          Every value arrives with its source document, an adversarial audit
          verdict, and a physics check. Nothing is invented — anything the
          pipeline cannot prove is flagged for review instead.
        </p>
        <div className="mt-5 flex gap-3">
          <Link
            href="/enrich"
            className="rounded-[3px] bg-accent px-4 py-2 font-mono text-xs font-semibold text-white hover:bg-accent/90"
          >
            Enrich products
          </Link>
          <Link
            href="/catalog"
            className="rounded-[3px] border border-line bg-panel px-4 py-2 font-mono text-xs font-semibold hover:border-ink"
          >
            Browse catalog
          </Link>
        </div>
      </div>

      <div className="pt-6">
        <div className="flex items-center justify-between">
          <h2 className="font-mono text-[10px] uppercase tracking-wider text-ink2">
            Recent enrichment runs
          </h2>
          <Link href="/enrich" className="font-mono text-xs text-accent underline decoration-accent/40 underline-offset-4 hover:decoration-accent">
            + new run
          </Link>
        </div>
        {jobs.length === 0 ? (
          <p className="mt-3 rounded-[3px] border border-line bg-panel p-5 text-sm text-ink2">
            No runs yet. Send one product or a spreadsheet from{" "}
            <Link href="/enrich" className="underline underline-offset-4">
              Enrich products
            </Link>{" "}
            and it will appear here with its results.
          </p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2">
            {jobs.map((job) => (
              <li key={job.id}>
                <Link
                  href={`/jobs/${job.id}`}
                  className="flex items-center justify-between gap-4 rounded-[3px] border border-line bg-panel px-4 py-3 hover:border-ink"
                >
                  <div className="min-w-0">
                    <span className="block truncate font-mono text-sm">{job.name}</span>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-ink2">
                      {new Date(job.createdAt).toLocaleString()} · {job.inputRows} row
                      {job.inputRows === 1 ? "" : "s"}
                    </span>
                  </div>
                  <span className={`shrink-0 font-mono text-xs font-semibold ${STATUS_TONE[job.status] ?? ""}`}>
                    {job.status}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
