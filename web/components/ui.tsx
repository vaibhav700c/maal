import { listRows, QueueRow } from "@/lib/artifacts";

export type Verdict = "CONFIRMED" | "UNVERIFIED" | "UNSUPPORTED" | "REFUTED" | string;

export function verdictTone(v: Verdict): "ok" | "warn" | "bad" {
  if (v === "CONFIRMED") return "ok";
  if (v === "REFUTED") return "bad";
  return "warn";
}

export function Chip({
  tone,
  children,
}: {
  tone: "neutral" | "ok" | "warn" | "bad" | "accent";
  children: React.ReactNode;
}) {
  const tones = {
    neutral: "border-line text-ink2",
    ok: "border-ok/40 text-ok bg-ok/5",
    warn: "border-warn/40 text-warn bg-warn/5",
    bad: "border-bad/40 text-bad bg-bad/5",
    accent: "border-accent/40 text-accent bg-accent/5",
  } as const;
  return (
    <span
      className={`inline-flex items-center rounded-[3px] border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function flagTone(flag: string): "neutral" | "warn" | "bad" | "accent" {
  if (flag.includes("PHYSICS_VIOLATION")) return "bad";
  if (flag === "DUPLICATE_SUSPECT") return "accent";
  return "warn";
}

export function TriageMeter({ score }: { score: number }) {
  const pct = Math.round(Math.min(1, Math.max(0, score)) * 100);
  const color = pct >= 66 ? "bg-bad" : pct >= 33 ? "bg-warn" : "bg-ok";
  return (
    <div
      className="relative h-6 w-1.5 overflow-hidden rounded-full bg-line"
      title={`triage ${score.toFixed(2)}`}
    >
      <div
        className={`absolute bottom-0 left-0 w-full ${color}`}
        style={{ height: `${pct}%` }}
      />
    </div>
  );
}

export function ConfidenceStamp({
  tier,
  verdict,
  confidence,
}: {
  tier: number | null | undefined;
  verdict: string | undefined;
  confidence: number | undefined;
}) {
  const source =
    tier == null ? "INPUT" : tier >= 1 ? "MFR SITE" : tier >= 0.9 ? "MFR DOC" : "DERIVED";
  const conf = (confidence ?? 0).toFixed(2);
  return (
    <span className="whitespace-nowrap font-mono text-[10px] text-ink2">
      [{source} · {verdict ?? "—"} · {conf}]
    </span>
  );
}

export function physicsSummary(row: QueueRow): { label: string; tone: "ok" | "bad" | "neutral" } {
  return row.physicsOk
    ? { label: "PHYSICS OK", tone: "ok" }
    : { label: "PHYSICS FAIL", tone: "bad" };
}
