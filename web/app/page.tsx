import Link from "next/link";
import { listRows } from "@/lib/artifacts";
import { Chip, flagTone, physicsSummary, TriageMeter } from "@/components/ui";
import RunPanel from "@/components/run-panel";

const FILTERS = [
  { key: "all", label: "All rows" },
  { key: "review", label: "Needs review", match: (f: string[]) => f.includes("NEEDS_REVIEW") },
  { key: "physics", label: "Physics failed", match: (f: string[]) => f.includes("PHYSICS_VIOLATION") },
  { key: "dupes", label: "Duplicate suspects", match: (f: string[]) => f.includes("DUPLICATE_SUSPECT") },
] as const;

export default async function QueuePage({
  searchParams,
}: {
  searchParams: Promise<{ filter?: string }>;
}) {
  const { filter = "all" } = await searchParams;
  const rows = listRows();

  if (!rows.length) {
    return (
      <div className="mx-auto max-w-xl border border-line bg-panel p-8">
        <h1 className="font-sans text-base font-semibold">No enriched rows yet</h1>
        <p className="mt-2 text-sm text-ink2">
          Run the pipeline to populate the console. From the project root:
        </p>
        <pre className="mt-3 overflow-x-auto rounded-[3px] border border-line bg-paper p-3 font-mono text-xs">
          PYTHONPATH=src .venv/bin/python -m pipeline.run_batch --limit 10
        </pre>
      </div>
    );
  }

  const counts = FILTERS.map((f) => ({
    ...f,
    count:
      "match" in f ? rows.filter((r) => f.match(r.flags)).length : rows.length,
  }));
  const active =
    FILTERS.find((f) => f.key === filter) ?? FILTERS[0];
  const visible =
    active.key === "all"
      ? rows
      : rows.filter((r) =>
          "match" in active ? active.match(r.flags) : true
        );

  return (
    <section>
      <div className="pb-4">
        <RunPanel />
      </div>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 pb-4">
        <h1 className="font-sans text-sm font-semibold uppercase tracking-[0.14em] text-ink2">
          Review queue
        </h1>
        <nav className="flex flex-wrap items-center gap-2">
          {counts.map((f) => {
            const isActive = f.key === active.key;
            return (
              <Link
                key={f.key}
                href={f.key === "all" ? "/" : `/?filter=${f.key}`}
                className={`rounded-[3px] border px-2.5 py-1 font-mono text-[11px] ${
                  isActive
                    ? "border-accent/50 bg-accent/10 text-accent"
                    : "border-line bg-panel text-ink2 hover:border-ink2 hover:text-ink"
                }`}
              >
                {f.label} · {f.count}
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="overflow-hidden rounded-[3px] border border-line bg-panel">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-line font-mono text-[10px] uppercase tracking-wider text-ink2">
              <th className="w-10 px-3 py-2 font-medium" aria-label="triage" />
              <th className="px-3 py-2 font-medium">Part number</th>
              <th className="px-3 py-2 font-medium">Classpath</th>
              <th className="px-3 py-2 font-medium">Physics</th>
              <th className="w-28 px-3 py-2 font-medium">Confidence</th>
              <th className="px-3 py-2 font-medium">Flags</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => {
              const phys = physicsSummary(row);
              return (
                <tr
                  key={row.mpn}
                  className="border-b border-line last:border-b-0 hover:bg-paper"
                >
                  <td className="px-3 py-2 align-middle">
                    <div className="flex justify-center">
                      <TriageMeter score={row.triage} />
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <Link
                      href={`/row/${encodeURIComponent(row.mpn)}`}
                      className="font-mono text-[13px] underline decoration-line underline-offset-4 hover:decoration-accent hover:text-accent"
                    >
                      {row.mpn}
                    </Link>
                  </td>
                  <td className="max-w-md truncate px-3 py-2 text-ink2">
                    {row.classpath || "— unclassified —"}
                  </td>
                  <td className="px-3 py-2">
                    <Chip tone={phys.tone}>{phys.label}</Chip>
                  </td>
                  <td className="px-3 py-2 font-mono text-[13px]">
                    {row.meanConfidence.toFixed(2)}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {row.flags.length === 0 && (
                        <Chip tone="ok">CLEAN</Chip>
                      )}
                      {row.flags.map((flag) => (
                        <Chip key={flag} tone={flagTone(flag)}>
                          {flag.replace(/_/g, " ")}
                        </Chip>
                      ))}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="pt-3 font-mono text-[11px] text-ink2">
        Sorted by triage score — highest review risk first. Triage meters fill
        orange as risk grows.
      </p>
    </section>
  );
}
