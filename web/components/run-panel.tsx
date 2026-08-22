"use client";

import { useCallback, useEffect, useRef, useState } from "react";

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
    <div className="rounded-[3px] border border-line bg-panel p-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="font-mono text-[10px] uppercase tracking-wider text-ink2">
            Run pipeline
          </h2>
          <p className="mt-1 text-xs text-ink2">
            Enrich rows from the input dataset. Progress checkpoints every row —
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
          <label className="flex items-center gap-2 font-mono text-[11px] text-ink2">
            rows
            <input
              type="number"
              min={1}
              max={10000}
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              disabled={running || busy}
              className="w-20 rounded-[3px] border border-line bg-paper px-2 py-1 font-mono text-xs focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex items-center gap-1.5 font-mono text-[11px] text-ink2">
            <input
              type="checkbox"
              checked={resume}
              onChange={(e) => setResume(e.target.checked)}
              disabled={running || busy}
              className="accent-[#e8590c]"
            />
            resume
          </label>
          {running ? (
            <button
              type="button"
              onClick={() => void control("DELETE")}
              disabled={busy}
              className="rounded-[3px] border border-bad/50 bg-bad/5 px-3 py-1.5 font-mono text-xs font-semibold text-bad hover:bg-bad/10 disabled:opacity-50"
            >
              Stop run
            </button>
          ) : (
            <button
              type="submit"
              disabled={busy}
              className="rounded-[3px] bg-accent px-3 py-1.5 font-mono text-xs font-semibold text-white hover:bg-accent/90 disabled:opacity-50"
            >
              {busy ? "Starting…" : "Run"}
            </button>
          )}
        </form>
      </div>

      {(running || (status?.processed ?? 0) > 0) && (
        <div className="mt-3">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-line">
            <div
              className={`h-full transition-all ${running ? "bg-accent" : "bg-ok"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="mt-1.5 flex justify-between font-mono text-[10px] text-ink2">
            <span>
              {running ? "RUNNING" : status?.finishedAt ? "FINISHED" : "IDLE"} ·{" "}
              {status?.processed ?? 0} / {status?.total ?? 0} rows ({pct}%)
            </span>
            {status?.pid && running && <span>pid {status.pid}</span>}
          </div>
          {status?.lastLog && (
            <p className="mt-1 truncate font-mono text-[10px] text-ink2" title={status.lastLog}>
              {status.lastLog}
            </p>
          )}
        </div>
      )}
      {error && <p className="mt-2 text-xs text-bad">{error}</p>}
    </div>
  );
}
