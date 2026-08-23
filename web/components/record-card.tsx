"use client";

import { Chip } from "@/components/ui";
import { useState } from "react";

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

export type JobResultRow = {
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

const DESCRIPTIONS: Array<[string, keyof JobResultRow]> = [
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
      className="font-mono text-[10px] text-fg-dim underline decoration-line underline-offset-4 transition-colors duration-150 ease-out hover:text-fg focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
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
      className="break-all text-accent underline decoration-accent/40 underline-offset-4 transition-colors duration-150 ease-out hover:decoration-accent focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
    >
      {v.length > max ? `${v.slice(0, max)}…` : v}
    </a>
  );
}

function AssetBlock({ row }: { row: JobResultRow }) {
  const entries = Object.entries(row.assets);
  const extraRefs = (row.retrieval?.refUrls ?? [])
    .filter((u) => !Object.values(row.assets).includes(u))
    .slice(0, 3);
  return (
    <dl className="mt-3 flex flex-col gap-1 rounded-md border border-line bg-surface-2 p-3 font-mono text-[11px]">
      {entries
        .filter(([k]) => k === "MFR URL")
        .map(([k, v]) => (
          <div key={k} className="grid grid-cols-[120px_1fr] gap-2">
            <dt className="text-fg-dim">{k}</dt>
            <dd className="break-all">
              <Url v={v} max={90} />
            </dd>
          </div>
        ))}
      {extraRefs.map((u) => (
        <div key={u} className="grid grid-cols-[120px_1fr] gap-2">
          <dt className="text-fg-dim">source doc</dt>
          <dd className="break-all">
            <Url v={u} max={80} />
          </dd>
        </div>
      ))}
      {entries
        .filter(([k]) => k !== "MFR URL")
        .map(([k, v]) => (
          <div key={k} className="grid grid-cols-[120px_1fr] gap-2">
            <dt className="text-fg-dim">{k}</dt>
            <dd className="break-all">
              {v.startsWith("http") ? <Url v={v} max={90} /> : v}
            </dd>
          </div>
        ))}
      {!row.assets["MFR URL"] && (
        <div className="grid grid-cols-[120px_1fr] gap-2">
          <dt className="text-fg-dim">MFR URL</dt>
          <dd className="text-warn">
            Not found.{" "}
            {(row.retrieval?.flags ?? []).join(", ") ||
              "No manufacturer page located for this part."}
          </dd>
        </div>
      )}
    </dl>
  );
}

function RecordCard({ row }: { row: JobResultRow }) {
  const [open, setOpen] = useState(false);

  return (
    <li className="rounded-xl border border-line bg-surface">
      <div className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-mono text-sm font-semibold text-fg">{row.mpn}</span>
          <div className="flex items-center gap-2">
            {row.flags.includes("PHYSICS_VIOLATION") && (
              <Chip tone="bad">physics fail</Chip>
            )}
            <Chip tone={row.triage >= 0.5 ? "warn" : "ok"}>
              triage {row.triage.toFixed(2)}
            </Chip>
          </div>
        </div>
        {row.shortDesc && <p className="mt-1.5 text-sm text-fg">{row.shortDesc}</p>}
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] text-fg-dim">
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
          className="mt-3 font-mono text-[11px] text-accent underline decoration-accent/40 underline-offset-4 transition-colors duration-150 ease-out hover:decoration-accent focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
        >
          {open
            ? "Hide full record"
            : "Show full record: descriptions, attributes, provenance, physics"}
        </button>

        {open && (
          <div className="mt-3 border-t border-line pt-3">
            <h4 className="text-sm font-semibold text-fg">Five descriptions</h4>
            <div className="mt-1.5 flex flex-col gap-1.5">
              {DESCRIPTIONS.map(([label, key]) => {
                const value = String(row[key] ?? "");
                return (
                  <div
                    key={label}
                    className="grid grid-cols-[130px_1fr_auto] items-start gap-3"
                  >
                    <span className="pt-0.5 text-xs text-fg-faint">
                      {label}
                    </span>
                    <span className="font-mono text-xs leading-snug text-fg">{value || "none"}</span>
                    {value && <CopyButton text={value} />}
                  </div>
                );
              })}
            </div>

            <h4 className="mt-4 text-sm font-semibold text-fg">
              Attribute ledger. Every value with its proof.
            </h4>
            {row.attributes.length === 0 ? (
              <p className="mt-1 text-xs text-fg-dim">
                No attributes could be verified for this part.
              </p>
            ) : (
              <div className="mt-1.5 overflow-x-auto">
                <table className="w-full min-w-[600px] text-left text-xs">
                  <thead>
                    <tr className="border-b border-line text-xs text-fg-faint">
                      <th className="py-1.5 pr-3 font-medium">Attribute</th>
                      <th className="py-1.5 pr-3 font-medium">Value</th>
                      <th className="py-1.5 pr-3 font-medium">Verdict</th>
                      <th className="py-1.5 font-medium">Evidence</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {row.attributes.map((a) => (
                      <tr key={a.label} className="align-top">
                        <td className="py-1.5 pr-3 text-fg-dim">{a.label}</td>
                        <td className="py-1.5 pr-3 font-mono text-fg">
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
                            {(a.verdict ?? "none").replace("_", " ")} ·{" "}
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
                            <span className="text-fg-dim">input row</span>
                          )}
                          {a.quote && (
                            <details className="mt-0.5 rounded-md border border-line bg-surface-2 open:pb-1.5">
                              <summary className="cursor-pointer select-none px-2 py-1 text-fg-dim transition-colors duration-150 ease-out hover:text-fg">
                                quote
                              </summary>
                              <blockquote className="mx-2 border-l-2 border-line pl-2 text-fg-dim">
                                {a.quote.slice(0, 300)}
                              </blockquote>
                            </details>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {row.physics && row.physics.length > 0 && (
              <>
                <h4 className="mt-4 text-sm font-semibold text-fg">Z3 physics dossier</h4>
                <ul className="mt-1.5 flex flex-col gap-1.5">
                  {row.physics.map((c) => (
                    <li
                      key={c.name}
                      className={`rounded-md border-l-4 bg-surface-2 px-3 py-1.5 text-xs ${
                        c.status === "UNSAT"
                          ? "border-bad"
                          : c.status === "SAT"
                            ? "border-ok"
                            : "border-line-2"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-mono">{c.name}</span>
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
                      </div>
                      {c.reason && (
                        <p className="mt-1 text-fg-dim">{c.reason}</p>
                      )}
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


export { CopyButton };

export { RecordCard };
