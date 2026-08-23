"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Btn } from "@/components/ui";

type RunStatus = {
  running: boolean;
  pid: number | null;
  startedAt: string | null;
  finishedAt: string | null;
  args: { limit: number; resume: boolean };
  processed: number;
  total: number;
  lastLog: string;
};

export default function RunPanel() {
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [limit, setLimit] = useState("10");
  const [resume, setResume] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/run", { cache: "no-store" });
      if (res.ok) setStatus(await res.json());
    } catch {
      /* server restarting; ignore */
    }
  }, []);

  useEffect(() => {
    void refresh();
    timer.current = setInterval(refresh, 2500);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [refresh]);

  async function control(method: "POST" | "DELETE") {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/run", {
        method,
        headers: { "Content-Type": "application/json" },
        body: method === "POST" ? JSON.stringify({ limit: Number(limit), resume }) : undefined,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        setError(body?.error ?? `Failed (${res.status})`);
      }
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  const running = status?.running ?? false;
  const pct =
    status && status.total > 0
      ? Math.min(100, Math.round((status.processed / status.total) * 100))
      : 0;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-fg">Run pipeline</h2>
          <p className="mt-1 text-xs text-fg-dim">
            Enrich rows from the input dataset. Progress checkpoints every row,
            safe to stop and resume.
          </p>
        </div>
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void control("POST");
          }}
        >
          <label className="flex items-center gap-2 font-mono text-[11px] text-fg-dim">
            rows
            <input
              type="number"
              min={1}
              max={10000}
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              disabled={running || busy}
              className="w-20 rounded-md border border-line bg-surface-2 px-2 py-1 font-mono text-xs text-fg focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
            />
          </label>
          <label className="flex items-center gap-1.5 font-mono text-[11px] text-fg-dim">
            <input
              type="checkbox"
              checked={resume}
              onChange={(e) => setResume(e.target.checked)}
              disabled={running || busy}
              className="accent-accent"
            />
            resume
          </label>
          {running ? (
            <button
              type="button"
              onClick={() => void control("DELETE")}
              disabled={busy}
              className="rounded-full border border-bad/50 bg-bad/5 px-4 py-2 font-mono text-xs font-semibold text-bad transition-colors duration-150 ease-out hover:bg-bad/10 disabled:pointer-events-none disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
            >
              Stop run
            </button>
          ) : (
            <Btn type="submit" disabled={busy}>
              {busy ? "Starting…" : "Run"}
            </Btn>
          )}
        </form>
      </div>

      {(running || (status?.processed ?? 0) > 0) && (
        <div className="mt-3">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-line">
            <div
              className={`h-full transition-[width] duration-500 ease-out ${running ? "bg-accent" : "bg-ok"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="mt-1.5 flex flex-wrap justify-between gap-2 font-mono text-[10px] text-fg-dim">
            <span className="inline-flex items-center gap-1.5">
              {running && (
                <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
              )}
              {running ? "RUNNING" : status?.finishedAt ? "FINISHED" : "IDLE"} ·{" "}
              {status?.processed ?? 0} / {status?.total ?? 0} rows ({pct}%)
            </span>
            {status?.pid && running && <span>pid {status.pid}</span>}
          </div>
          {status?.lastLog && (
            <p className="mt-1 truncate font-mono text-[10px] text-fg-faint" title={status.lastLog}>
              {status.lastLog}
            </p>
          )}
        </div>
      )}
      {error && <p className="mt-2 text-xs text-bad">{error}</p>}
    </div>
  );
}
