"use client";

import { useState } from "react";
import { Btn } from "@/components/ui";

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
    const attrs: Record<string, string> = {};
    for (const r of rows) {
      if (r.label.trim() && r.value.trim()) attrs[r.label.trim()] = r.value.trim();
    }
    if (!Object.keys(attrs).length) {
      setStatus("Nothing to send. Add at least one label and value.");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/corrections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mfg_part_num: mpn, attributes: attrs }),
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
          <span className="text-xs text-fg-faint">Correct a value</span>
          <button
            type="button"
            onClick={addRow}
            className="font-mono text-[11px] text-accent underline decoration-accent/40 underline-offset-4 transition-colors duration-150 ease-out hover:decoration-accent focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
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
            className="rounded-md border border-line bg-surface-2 px-2 py-1.5 font-mono text-xs text-fg focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
          />
          <input
            placeholder="Corrected value"
            value={row.value}
            onChange={(e) => update(i, { value: e.target.value })}
            className="rounded-md border border-line bg-surface-2 px-2 py-1.5 font-mono text-xs text-fg focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
          />
          <button
            type="button"
            onClick={() => setRows((r) => r.filter((_, idx) => idx !== i))}
            aria-label={`Remove field ${i + 1}`}
            className="px-1 font-mono text-xs text-fg-faint transition-colors duration-150 ease-out hover:text-bad focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
          >
            ✕
          </button>
        </div>
      ))}

      <Btn type="submit" disabled={busy} className="self-start">
        {busy ? "Saving…" : "Save correction"}
      </Btn>
      {status && <p className="text-xs text-fg-dim">{status}</p>}
    </form>
  );
}
