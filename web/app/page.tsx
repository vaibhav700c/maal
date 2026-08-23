import Link from "next/link";
import { listJobs } from "@/lib/jobs";
import { listRows } from "@/lib/artifacts";
import { Card, Btn, Stat, Empty } from "@/components/ui";
import RevealOnMount from "@/components/reveal";

const STATUS_TONE: Record<string, string> = {
  RUNNING: "text-accent",
  DONE: "text-ok",
  FAILED: "text-bad",
  CANCELLED: "text-fg-faint",
};

export default function HomePage() {
  const allJobs = listJobs();
  const jobs = allJobs.slice(0, 6);

  const rows = listRows();
  const flaggedCount = rows.filter((r) => r.flags.length > 0).length;
  const confirmedCount = rows.length - flaggedCount;
  const confirmedLabel =
    rows.length === 0 ? "none yet" : `${Math.round((confirmedCount / rows.length) * 100)}%`;

  return (
    <section className="mx-auto max-w-5xl">
      <RevealOnMount />

      <div className="border-b border-line pb-10 pt-4 md:pb-14 md:pt-8">
        <h1 className="reveal font-display text-4xl font-extrabold tracking-tight text-fg md:text-5xl">
          Every value earns its place.
        </h1>
        <p
          className="reveal mt-4 max-w-xl text-sm text-fg-dim md:text-base"
          style={{ transitionDelay: "60ms" }}
        >
          Every value arrives with its source document, an adversarial audit
          verdict, and a physics check. Nothing is invented: anything the
          pipeline cannot prove is flagged for review instead.
        </p>
        <div className="reveal mt-6 flex flex-wrap gap-3" style={{ transitionDelay: "120ms" }}>
          <Btn href="/enrich">Enrich a product</Btn>
          <Btn href="/catalog" variant="ghost">
            Browse the catalog
          </Btn>
        </div>
      </div>

      <div
        className="reveal grid grid-cols-2 gap-6 border-b border-line py-8 sm:grid-cols-4 md:py-10"
        style={{ transitionDelay: "160ms" }}
      >
        <Stat label="Enrichment runs" value={allJobs.length} />
        <Stat label="Rows in catalog" value={rows.length} />
        <Stat label="Confirmed" value={confirmedLabel} tone="ok" />
        <Stat
          label="Flagged for review"
          value={flaggedCount}
          tone={flaggedCount > 0 ? "warn" : "neutral"}
        />
      </div>

      <div className="pt-8 md:pt-10">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-xl font-display font-semibold tracking-tight text-fg">
            Recent jobs
          </h2>
          <Btn href="/enrich" variant="ghost" className="px-3 py-1.5 text-[11px]">
            Start a run
          </Btn>
        </div>

        {jobs.length === 0 ? (
          <div className="mt-4">
            <Empty
              title="No runs yet."
              hint="Send one product or a spreadsheet from Enrich and it will appear here with its results."
              action={<Btn href="/enrich">Enrich a product</Btn>}
            />
          </div>
        ) : (
          <ul className="mt-4 flex flex-col gap-3">
            {jobs.map((job, i) => (
              <li
                key={job.id}
                className="reveal"
                style={{ transitionDelay: `${200 + i * 40}ms` }}
              >
                <Link
                  href={`/jobs/${job.id}`}
                  className="block rounded-xl focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
                >
                  <Card interactive className="flex items-center justify-between gap-4">
                    <div className="min-w-0">
                      <p className="truncate font-mono text-sm text-fg">{job.name}</p>
                      <p className="mt-1 text-xs text-fg-faint">
                        {new Date(job.createdAt).toLocaleString()} · {job.inputRows} row
                        {job.inputRows === 1 ? "" : "s"}
                      </p>
                    </div>
                    <span
                      className={`shrink-0 font-mono text-xs font-semibold ${
                        STATUS_TONE[job.status] ?? "text-fg-dim"
                      }`}
                    >
                      {job.status}
                    </span>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
