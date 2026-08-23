import Link from "next/link";
import { listRows } from "@/lib/artifacts";
import {
  Btn,
  Card,
  Chip,
  Empty,
  PageTitle,
  TriageMeter,
  flagTone,
  physicsSummary,
} from "@/components/ui";
import RunPanel from "@/components/run-panel";

const FILTERS = [
  { key: "all", label: "All rows" },
  { key: "review", label: "Needs review", match: (f: string[]) => f.includes("NEEDS_REVIEW") },
  { key: "physics", label: "Physics failed", match: (f: string[]) => f.includes("PHYSICS_VIOLATION") },
  { key: "dupes", label: "Duplicate suspects", match: (f: string[]) => f.includes("DUPLICATE_SUSPECT") },
] as const;

export default async function CatalogPage({
  searchParams,
}: {
  searchParams: Promise<{ filter?: string }>;
}) {
  const { filter = "all" } = await searchParams;
  const rows = listRows();

  if (!rows.length) {
    return (
      <section className="mx-auto flex max-w-2xl flex-col gap-6">
        <PageTitle
          title="Catalog"
          sub="The dense review queue for every enriched row, ranked by triage risk."
        />
        <Empty
          title="No enriched rows yet"
          hint="Run an enrichment job to populate the catalog. Send one product or a spreadsheet from Enrich, and rows will appear here as they finish."
          action={<Btn href="/enrich">Enrich products</Btn>}
        />
        <Card>
          <RunPanel />
        </Card>
      </section>
    );
  }

  const counts = FILTERS.map((f) => ({
    ...f,
    count:
      "match" in f ? rows.filter((r) => f.match(r.flags)).length : rows.length,
  }));
  const active = FILTERS.find((f) => f.key === filter) ?? FILTERS[0];
  const visible =
    active.key === "all"
      ? rows
      : rows.filter((r) =>
          "match" in active ? active.match(r.flags) : true
        );

  return (
    <section className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <PageTitle
          title="Catalog"
          sub="Dense review queue, sorted by triage score. Highest review risk first."
        />
        <div className="flex flex-wrap gap-2">
          <Btn href="/api/download/result.csv">result.csv</Btn>
          <Btn variant="ghost" href="/api/download/result.xlsx">result.xlsx</Btn>
          <Btn variant="ghost" href="/api/download/sidecar.jsonl">sidecar.jsonl</Btn>
        </div>
      </div>

      <Card>
        <RunPanel />
      </Card>

      <div className="sticky top-[60px] z-10 -mx-4 flex flex-wrap items-center gap-2 border-y border-line bg-ink/95 px-4 py-3 backdrop-blur">
        {counts.map((f) => {
          const isActive = f.key === active.key;
          return (
            <Link
              key={f.key}
              href={f.key === "all" ? "/catalog" : `/catalog?filter=${f.key}`}
              className={`rounded-full border px-3 py-1 font-mono text-[11px] transition-colors duration-150 ease-out focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2 ${
                isActive
                  ? "border-accent/50 bg-accent/10 text-accent"
                  : "border-line bg-surface text-fg-dim hover:border-line-2 hover:text-fg"
              }`}
            >
              {f.label} · {f.count}
            </Link>
          );
        })}
      </div>

      <div className="overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead>
            <tr className="border-b border-line text-xs text-fg-faint">
              <th className="w-10 px-3 py-2 font-medium" aria-label="triage" />
              <th className="px-3 py-2 font-medium">Part number</th>
              <th className="px-3 py-2 font-medium">Classpath</th>
              <th className="px-3 py-2 font-medium">Physics</th>
              <th className="w-28 px-3 py-2 font-medium">Confidence</th>
              <th className="px-3 py-2 font-medium">Product link</th>
              <th className="px-3 py-2 font-medium">Flags</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {visible.map((row) => {
              const phys = physicsSummary(row);
              return (
                <tr
                  key={row.mpn}
                  className="transition-colors duration-150 ease-out hover:bg-surface-2"
                >
                  <td className="py-2 px-3 align-middle">
                    <div className="flex justify-center">
                      <TriageMeter score={row.triage} />
                    </div>
                  </td>
                  <td className="py-2 px-3">
                    <Link
                      href={`/row/${encodeURIComponent(row.mpn)}`}
                      className="font-mono text-[13px] text-fg underline decoration-line underline-offset-4 transition-colors duration-150 ease-out hover:text-accent hover:decoration-accent focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
                    >
                      {row.mpn}
                    </Link>
                  </td>
                  <td className="max-w-md truncate py-2 px-3 text-fg-dim">
                    {row.classpath || "not classified"}
                  </td>
                  <td className="py-2 px-3">
                    <Chip tone={phys.tone}>{phys.label}</Chip>
                  </td>
                  <td className="py-2 px-3 font-mono text-[13px] text-fg">
                    {row.meanConfidence.toFixed(2)}
                  </td>
                  <td className="py-2 px-3">
                    {(row.productUrl || row.mfrUrl) ? (
                      <a
                        href={(row.productUrl || row.mfrUrl)!}
                        target="_blank"
                        rel="noreferrer"
                        title={(row.productUrl || row.mfrUrl)!}
                        className="font-mono text-[12px] text-accent underline decoration-accent/40 underline-offset-4 transition-colors duration-150 ease-out hover:decoration-accent"
                      >
                        {row.productUrl
                          ? "product ↗"
                          : `maker ↗${row.refCount ? ` ·${row.refCount}` : ""}`}
                      </a>
                    ) : (
                      <span className="text-fg-dim">—</span>
                    )}
                  </td>
                  <td className="py-2 px-3">
                    <div className="flex flex-wrap gap-1">
                      {row.flags.length === 0 && <Chip tone="ok">CLEAN</Chip>}
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
      <p className="font-mono text-[11px] text-fg-faint">
        Sorted by triage score, highest review risk first.
      </p>
    </section>
  );
}
