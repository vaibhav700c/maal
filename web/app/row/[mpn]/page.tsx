import Link from "next/link";
import { getRow } from "@/lib/artifacts";
import {
  Btn,
  Card,
  Chip,
  ConfidenceStamp,
  Empty,
  flagTone,
  verdictTone,
} from "@/components/ui";
import CorrectionsForm from "@/components/corrections-form";

const DESC_FIELDS = [
  ["SHORT_DESC", "Search title", 120],
  ["LONG_DESC1", "Long description", null],
  ["MOBILE_DESC", "Mobile description", 80],
  ["INVOICE_DESC", "Invoice description", 40],
  ["RETAIL_DESC", "Retail description", 160],
] as const;

const IDENTITY_FIELDS = [
  "MANUFACTURER_NAME",
  "BRAND_NAME",
  "TRADE_NAME",
  "MANUFACTURER_PART_NUMBER",
  "Classpath",
  "UNSPSC",
] as const;

function SectionHead({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="border-b border-line px-4 py-3 font-display text-xl font-semibold tracking-tight text-fg">
      {children}
    </h2>
  );
}

export default async function RowPage({
  params,
}: {
  params: Promise<{ mpn: string }>;
}) {
  const { mpn: raw } = await params;
  const mpn = decodeURIComponent(raw);
  const data = getRow(mpn);

  if (!data) {
    return (
      <section className="mx-auto flex max-w-xl flex-col gap-6">
        <Empty
          title="No sidecar record"
          hint={`There is no enriched record for ${mpn} yet. Run it through Enrich to generate one.`}
          action={<Btn href="/enrich">Enrich this row</Btn>}
        />
        <Link
          href="/catalog"
          className="font-mono text-xs text-fg-dim underline decoration-line underline-offset-4 transition-colors duration-150 ease-out hover:text-fg focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
        >
          ← Back to catalog
        </Link>
      </section>
    );
  }

  const { record, csvRow } = data;
  const fields = record.fields ?? {};
  const checks = record.physics?.checks ?? [];
  const retrieval = record.retrieval;
  const attrOptions = Object.keys(fields).map((label) => ({
    label,
    value: fields[label].value ?? "",
  }));

  return (
    <section className="flex flex-col gap-6">
      <div>
        <Link
          href="/catalog"
          className="font-mono text-xs text-fg-dim underline decoration-line underline-offset-4 transition-colors duration-150 ease-out hover:text-fg focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
        >
          ← Review queue
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-2xl font-semibold tracking-tight text-fg">
            {record.mfg_part_num}
          </h1>
          {record.physics &&
            !checks.every((c) => c.status !== "UNSAT") && (
              <Chip tone="bad">PHYSICS FAIL</Chip>
            )}
          {(record.flags ?? []).map((flag) => (
            <Chip key={flag} tone={flagTone(flag)}>
              {flag.replace(/_/g, " ")}
            </Chip>
          ))}
          {(!record.flags || record.flags.length === 0) && (
            <Chip tone="ok">CLEAN</Chip>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-6">
          {/* Identity */}
          <Card className="p-0">
            <SectionHead>Identity and classification</SectionHead>
            <dl className="grid grid-cols-[180px_1fr] gap-y-1.5 px-4 py-3 text-sm">
              {IDENTITY_FIELDS.map((key) => {
                const value =
                  key in csvRow ? csvRow[key] : (record.classification as unknown as Record<string, string>)?.[key] ?? "";
                if (!value) return null;
                return (
                  <div key={key} className="contents">
                    <dt className="py-0.5 text-xs text-fg-faint">{key}</dt>
                    <dd className={`py-0.5 text-fg ${key.includes("PART_NUMBER") ? "font-mono" : ""}`}>
                      {value}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </Card>

          {/* Descriptions */}
          <Card className="p-0">
            <SectionHead>Descriptions</SectionHead>
            <div className="flex flex-col divide-y divide-line px-4">
              {DESC_FIELDS.map(([key, label, limit]) => {
                const value = csvRow[key] ?? "";
                return (
                  <div key={key} className="py-3">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-xs text-fg-faint">{label}</span>
                      <span className="font-mono text-[11px] text-fg-faint">
                        {value.length}
                        {limit ? `/${limit}` : ""}
                      </span>
                    </div>
                    <div className="mt-1.5 rounded-md border border-line bg-surface-2 px-3 py-2 font-mono text-[13px] leading-snug text-fg">
                      {value || <span className="text-fg-faint">Not generated.</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>

          {/* Attribute ledger */}
          <Card className="p-0">
            <SectionHead>Attribute ledger</SectionHead>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-xs text-fg-faint">
                    <th className="px-4 py-2 font-medium">Attribute</th>
                    <th className="px-4 py-2 font-medium">Value</th>
                    <th className="px-4 py-2 font-medium">QC stamp</th>
                    <th className="px-4 py-2 font-medium" colSpan={2}>Source</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {Object.entries(fields).map(([label, f]) => (
                    <tr key={label} className="align-top">
                      <td className="px-4 py-2 text-fg-dim">{label}</td>
                      <td className="px-4 py-2 font-mono text-[13px] text-fg">
                        {f.value}
                        {f.uom ? ` ${f.uom}` : ""}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2">
                        <Chip tone={verdictTone(f.verdict ?? "")}>{(f.verdict ?? "none").replace("_", " ")}</Chip>{" "}
                        <ConfidenceStamp tier={f.tier} verdict={f.verdict} confidence={f.confidence} />
                      </td>
                      <td colSpan={2} className="px-4 pb-2 pt-2 text-xs">
                        {f.source_url ? (
                          <a
                            href={f.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="break-all font-mono text-[11px] text-accent underline decoration-accent/40 underline-offset-4 transition-colors duration-150 ease-out hover:decoration-accent focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
                          >
                            {f.source_url.length > 48 ? `${f.source_url.slice(0, 48)}…` : f.source_url}
                          </a>
                        ) : (
                          <span className="font-mono text-[11px] text-fg-faint">no external source</span>
                        )}
                        {f.quote && (
                          <details className="mt-1.5 rounded-md border border-line bg-surface-2 open:pb-2">
                            <summary className="cursor-pointer select-none px-2 py-1 font-mono text-[11px] text-fg-dim transition-colors duration-150 ease-out hover:text-fg">
                              evidence quote
                            </summary>
                            <blockquote className="mx-2 mb-1 border-l-2 border-line pl-3 text-fg-dim">
                              {f.quote.slice(0, 400)}
                            </blockquote>
                          </details>
                        )}
                        {f.review_reason && (
                          <p className="mt-1.5 text-bad">{f.review_reason}</p>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        {/* Right rail */}
        <div className="flex flex-col gap-6 lg:sticky lg:top-6 lg:self-start">
          <Card className="p-0">
            <SectionHead>Z3 physics dossier</SectionHead>
            <ul className="flex flex-col gap-2 p-4">
              {checks.length === 0 && (
                <li className="text-sm text-fg-dim">No checks recorded.</li>
              )}
              {checks.map((c) => (
                <li
                  key={c.name}
                  className={`rounded-md border-l-4 bg-surface-2 px-3 py-2 text-sm ${
                    c.status === "UNSAT"
                      ? "border-bad"
                      : c.status === "SAT"
                        ? "border-ok"
                        : "border-line-2"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs text-fg">{c.name}</span>
                    <Chip
                      tone={
                        c.status === "SAT" ? "ok" : c.status === "UNSAT" ? "bad" : "neutral"
                      }
                    >
                      {c.status}
                    </Chip>
                  </div>
                  {c.reason && <p className="mt-1 text-xs text-fg-dim">{c.reason}</p>}
                </li>
              ))}
            </ul>
          </Card>

          <Card className="p-0">
            <SectionHead>Sourcing</SectionHead>
            <dl className="px-4 py-3 text-sm">
              <dt className="text-xs text-fg-faint">Manufacturer domain</dt>
              <dd className="pb-2 break-all font-mono text-xs text-fg">
                {retrieval?.mfr_url ?? "not resolved"}
              </dd>
              <dt className="text-xs text-fg-faint">Reference documents</dt>
              <dd className="font-mono text-xs text-fg">
                {retrieval?.ref_urls?.length ?? 0} on-domain docs
              </dd>
              {(retrieval?.flags ?? []).length > 0 && (
                <dd className="pt-2">
                  {retrieval!.flags!.map((f) => (
                    <Chip key={f} tone="warn">
                      {f.replace(/_/g, " ")}
                    </Chip>
                  ))}
                </dd>
              )}
            </dl>
          </Card>

          <Card>
            <h2 className="mb-3 text-sm font-semibold text-fg">Assets and documents</h2>
            <dl className="flex flex-col gap-2 font-mono text-[11px]">
              {[
                ["MFR URL", csvRow["MFR URL"]],
                ["Product Image", csvRow["Product Image"]],
                ["Specification Sheet", csvRow["Specification Sheet"]],
                ["Actual Image", csvRow["Actual Image (Yes/No)"]],
                ["Ref URL 1", csvRow["Ref URL 1"]],
                ["Ref URL 2", csvRow["Ref URL 2"]],
                ["Ref URL 3", csvRow["Ref URL 3"]],
              ]
                .filter(([, v]) => v)
                .map(([k, v]) => (
                  <div key={k as string} className="grid grid-cols-[110px_1fr] gap-2">
                    <dt className="text-fg-dim">{k}</dt>
                    <dd className="break-all text-fg">
                      {String(v).startsWith("http") ? (
                        <a
                          href={String(v)}
                          target="_blank"
                          rel="noreferrer"
                          className="text-accent underline decoration-accent/40 underline-offset-4 transition-colors duration-150 ease-out hover:decoration-accent focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
                        >
                          {String(v).length > 52 ? `${String(v).slice(0, 52)}…` : v}
                        </a>
                      ) : (
                        v
                      )}
                    </dd>
                  </div>
                ))}
            </dl>
          </Card>

          <Card>
            <CorrectionsForm mpn={record.mfg_part_num} attributes={attrOptions} />
          </Card>
        </div>
      </div>
    </section>
  );
}
