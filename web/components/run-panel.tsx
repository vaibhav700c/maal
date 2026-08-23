"use client";

import { useCallback, useEffect, useState } from "react";
import { Btn, Card } from "@/components/ui";
import { useRouter } from "next/navigation";

export default function RunPanel() {
  const router = useRouter();
  const [rows, setRows] = useState("5");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Array<{ mpn: string; brand: string; classpath: string }>>([]);

  async function run() {
    const n = parseInt(rows, 10) || 5;
    setBusy(true); setError(null); setResults([]);
    try {
      // Fetch N rows from the bundled snapshot input
      const snapshot = await fetch("/data/sample-input.csv");
      if (!snapshot.ok) throw new Error("Snapshot not available");
      const text = await snapshot.text();
      const lines = text.split("\n").filter(Boolean);
      const header = lines[0].split(",");

      // Parse first N data rows
      const selected = [];
      for (let i = 1; i <= n && i < lines.length; i++) {
        const cells = lines[i].split(",");
        if (cells.length < 2) continue;
        selected.push({
          mpn: cells[0]?.trim(),
          description: cells[1]?.trim(),
        });
      }

      if (!selected.length) throw new Error("No rows found in dataset");

      // Enrich via the live backend (batch endpoint)
      const enrichRes = await fetch("/api/enrich-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows: selected }),
      });
      const body = await enrichRes.json().catch(() => ({}));
      if (!enrichRes.ok || body.error) {
        setError(body.error ?? `Failed (${enrichRes.status})`);
        return;
      }
      setResults(body.rows ?? []);
    } catch (e: any) {
      setError(e?.message ?? "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-fg">Live enrichment</h2>
          <p className="mt-0.5 text-xs text-fg-dim">
            Re-enrich rows from the sample dataset using the full pipeline.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-fg-dim">
            Rows:
            <input
              type="number" min={1} max={10} value={rows}
              onChange={(e) => setRows(e.target.value)}
              disabled={busy}
              className="ml-1 w-16 rounded border border-line bg-paper px-2 py-1 font-mono text-xs focus:border-accent focus:outline-none"
            />
          </label>
          <Btn onClick={run} disabled={busy}>
            {busy ? "Enriching…" : "Run"}
          </Btn>
        </div>
      </div>

      {error && <p className="mt-2 text-xs text-bad">{error}</p>}

      {results.length > 0 && (
        <div className="mt-3 rounded border border-line bg-paper p-3">
          <p className="text-xs font-medium text-ok">
            ✅ {results.length} rows enriched
          </p>
          <ul className="mt-1 space-y-0.5 font-mono text-[11px] text-fg-dim">
            {results.map((r) => (
              <li key={r.mpn}>{r.mpn}: {r.brand || "?"} — {r.classpath?.split(">").pop()?.trim() || "?"}</li>
            ))}
          </ul>
          <p className="mt-1.5 text-[11px] text-fg-dim">
            Refresh the page to see these in the catalog.
          </p>
        </div>
      )}
    </Card>
  );
}
