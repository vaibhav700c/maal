"use client";

import { useState } from "react";

type AttrOption = { label: string; value: string };

export default function CorrectionsForm({
  mpn,
  attributes,
}: {
  mpn: string;
  attributes: AttrOption[];
}) {
  const [rows, setRows] = useState<AttrOption[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function addRow() {
    setRows((r) => [...r, { label: "", value: "" }]);
    setStatus(null);
  }

  function update(i: number, patch: Partial<AttrOption>) {
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  }

  async function submit() {
    const attributes: Record<string, string> = {};
    for (const r of rows) {
      if (r.label.trim() && r.value.trim()) attributes[r.label.trim()] = r.value.trim();
    }
    if (!Object.keys(attributes).length) {
      setStatus("Nothing to send — add at least one label and value.");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/corrections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mfg_part_num: mpn, attributes }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        setStatus(body?.error ?? `Failed (${res.status})`);
        return;
      }
      setStatus("Correction queued. Rerun the pipeline to apply it.");
      setRows([]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <div>
        <div className="flex items-center justify-between">
          <span className="font-mono text-[10px] uppercase tracking-wider text-ink2">
            Correct a value
          </span>
          <button
            type="button"
            onClick={addRow}
            className="font-mono text-[11px] text-accent underline decoration-accent/40 underline-offset-4 hover:decoration-accent"
          >
            + add field
          </button>
        </div>
        {rows.length > 0 && (
          <datalist id={`attrs-${mpn}`}>
            {attributes.map((a) => (
              <option key={a.label} value={a.label} />
            ))}
          </datalist>
        )}
      </div>

      {rows.map((row, i) => (
        <div key={i} className="grid grid-cols-[1fr_1fr_auto] items-center gap-2">
          <input
            list={`attrs-${mpn}`}
            placeholder="Field label"
            value={row.label}
            onChange={(e) => update(i, { label: e.target.value })}
            className="rounded-[3px] border border-line bg-paper px-2 py-1 font-mono text-xs focus:border-accent focus:outline-none"
          />
          <input
            placeholder="Corrected value"
            value={row.value}
            onChange={(e) => update(i, { value: e.target.value })}
            className="rounded-[3px] border border-line bg-paper px-2 py-1 font-mono text-xs focus:border-accent focus:outline-none"
          />
          <button
            type="button"
            onClick={() => setRows((r) => r.filter((_, idx) => idx !== i))}
            aria-label={`Remove field ${i + 1}`}
            className="px-1 font-mono text-xs text-ink2 hover:text-bad"
          >
            ✕
          </button>
        </div>
      ))}

      <button
        type="submit"
        disabled={busy}
        className="self-start rounded-[3px] bg-accent px-3 py-1.5 font-mono text-xs font-semibold text-white hover:bg-accent/90 disabled:opacity-50"
      >
        {busy ? "Sending…" : "Send correction"}
      </button>
      {status && <p className="text-xs text-ink2">{status}</p>}
    </form>
  );
}
