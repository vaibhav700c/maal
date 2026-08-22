import Link from "next/link";
import { getRow } from "@/lib/artifacts";
import { Chip, ConfidenceStamp, flagTone, verdictTone } from "@/components/ui";
import CorrectionsForm from "@/components/corrections-form";

const DESC_FIELDS = [
  ["SHORT_DESC", "Search title"],
  ["LONG_DESC1", "Long description"],
  ["MOBILE_DESC", "Mobile description"],
  ["INVOICE_DESC", "Invoice description"],
  ["RETAIL_DESC", "Retail description"],
] as const;

const IDENTITY_FIELDS = [
  "MANUFACTURER_NAME",
  "BRAND_NAME",
  "TRADE_NAME",
  "MANUFACTURER_PART_NUMBER",
  "Classpath",
  "UNSPSC",
] as const;

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
      <div className="mx-auto max-w-xl border border-line bg-panel p-8">
        <h1 className="text-base font-semibold">Row not found</h1>
        <p className="mt-2 text-sm text-ink2">
          No sidecar record for <span className="font-mono">{mpn}</span>.
        </p>
        <Link href="/" className="mt-4 inline-block font-mono text-xs text-accent underline underline-offset-4">
          ← Back to queue
        </Link>
      </div>
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
          href="/"
          className="font-mono text-xs text-ink2 underline decoration-line underline-offset-4 hover:text-ink"
        >
          ← Review queue
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-xl font-semibold">{record.mfg_part_num}</h1>
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
          <div className="rounded-[3px] border border-line bg-panel">
            <h2 className="border-b border-line px-4 py-2 font-mono text-[10px] uppercase tracking-wider text-ink2">
              Identity & classification
            </h2>
            <dl className="grid grid-cols-[180px_1fr] gap-y-1 px-4 py-3 text-sm">
              {IDENTITY_FIELDS.map((key) => {
                const value =
                  key in csvRow ? csvRow[key] : (record.classification as unknown as Record<string, string>)?.[key] ?? "";
                if (!value) return null;
                return (
                  <div key={key} className="contents">
                    <dt className="py-0.5 font-mono text-[11px] text-ink2">{key}</dt>
                    <dd className={`py-0.5 ${key.includes("PART_NUMBER") ? "font-mono" : ""}`}>
                      {value}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </div>

          {/* Descriptions */}
          <div className="rounded-[3px] border border-line bg-panel">
            <h2 className="border-b border-line px-4 py-2 font-mono text-[10px] uppercase tracking-wider text-ink2">
              Descriptions — five formats from verified attributes
            </h2>
            <dl className="px-4 py-3">
              {DESC_FIELDS.map(([key, label]) => {
                const value = csvRow[key];
                return (
                  <div key={key} className="grid grid-cols-[150px_1fr] gap-x-4 border-b border-line py-2 last:border-b-0">
                    <dt className="font-mono text-[11px] uppercase text-ink2">{label}</dt>
                    <dd className="text-sm leading-snug">
                      {value || <span className="text-ink2">— not generated —</span>}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </div>

          {/* Attribute ledger */}
          <div className="rounded-[3px] border border-line bg-panel">
            <h2 className="border-b border-line px-4 py-2 font-mono text-[10px] uppercase tracking-wider text-ink2">
              Attribute ledger — provenance per value
            </h2>
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-line font-mono text-[10px] uppercase tracking-wider text-ink2">
                  <th className="px-4 py-2 font-medium">Attribute</th>
                  <th className="px-4 py-2 font-medium">Value</th>
                  <th className="px-4 py-2 font-medium">Provenance</th>
                  <th className="px-4 py-2 font-medium" colSpan={2}>Source</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(fields).map(([label, f]) => (
                  <tr key={label} className="border-b border-line last:border-b-0 align-top">
                    <td className="px-4 py-2 text-ink2">{label}</td>
                    <td className="px-4 py-2 font-mono text-[13px]">
                      {f.value}
                      {f.uom ? ` ${f.uom}` : ""}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2">
                      <Chip tone={verdictTone(f.verdict ?? "")}>{(f.verdict ?? "—").replace("_", " ")}</Chip>{" "}
                      <ConfidenceStamp tier={f.tier} verdict={f.verdict} confidence={f.confidence} />
                    </td>
                    <td colSpan={2} className="px-4 pb-2 pt-2 text-xs">
                      {f.source_url ? (
                        <>
                          <a
                            href={f.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="break-all font-mono text-[11px] text-accent underline decoration-accent/40 underline-offset-4 hover:decoration-accent"
                          >
                            {f.source_url.length > 48 ? `${f.source_url.slice(0, 48)}…` : f.source_url}
                          </a>
                        </>
                      ) : (
                        <span className="font-mono text-[11px] text-ink2">no external source</span>
                      )}
                      {f.quote && (
                        <details className="mt-1">
                          <summary className="cursor-pointer select-none font-mono text-[11px] text-ink2 hover:text-ink">
                            evidence quote
                          </summary>
                          <blockquote className="mt-1 border-l-2 border-line pl-3 text-ink2">
                            {f.quote.slice(0, 400)}
                          </blockquote>
                        </details>
                      )}
                      {f.review_reason && (
                        <p className="mt-1 text-bad/90">⚠ {f.review_reason}</p>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right rail */}
        <div className="flex flex-col gap-6 lg:sticky lg:top-6 lg:self-start">
          <div className="rounded-[3px] border border-line bg-panel">
            <h2 className="border-b border-line px-4 py-2 font-mono text-[10px] uppercase tracking-wider text-ink2">
              Physics dossier — Z3 solver
            </h2>
            <ul className="divide-y divide-line px-4">
              {checks.length === 0 && (
                <li className="py-2 text-sm text-ink2">No checks recorded.</li>
              )}
              {checks.map((c) => (
                <li key={c.name} className="py-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs">{c.name}</span>
                    <Chip
                      tone={
                        c.status === "SAT" ? "ok" : c.status === "UNSAT" ? "bad" : "neutral"
                      }
                    >
                      {c.status}
                    </Chip>
                  </div>
                  {c.reason && <p className="mt-1 text-xs text-bad/90">{c.reason}</p>}
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-[3px] border border-line bg-panel">
            <h2 className="border-b border-line px-4 py-2 font-mono text-[10px] uppercase tracking-wider text-ink2">
              Sourcing
            </h2>
            <dl className="px-4 py-3 text-sm">
              <dt className="font-mono text-[11px] text-ink2">Manufacturer domain</dt>
              <dd className="pb-2 font-mono text-xs break-all">
                {retrieval?.mfr_url ?? "not resolved"}
              </dd>
              <dt className="font-mono text-[11px] text-ink2">Reference documents</dt>
              <dd className="font-mono text-xs">
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
          </div>

          <div className="rounded-[3px] border border-line bg-panel p-4">
            <CorrectionsForm mpn={record.mfg_part_num} attributes={attrOptions} />
          </div>
        </div>
      </div>
    </section>
  );
}
