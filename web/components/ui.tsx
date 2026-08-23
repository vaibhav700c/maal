import Link from "next/link";
import type { QueueRow } from "@/lib/artifacts";

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
    neutral: "border-line text-fg-dim",
    ok: "border-ok/40 text-ok bg-ok/5",
    warn: "border-warn/40 text-warn bg-warn/5",
    bad: "border-bad/40 text-bad bg-bad/5",
    accent: "border-accent/40 text-accent bg-accent/5",
  } as const;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide ${tones[tone]}`}
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
    <span className="whitespace-nowrap font-mono text-[10px] text-fg-dim">
      [{source} · {verdict ?? "none"} · {conf}]
    </span>
  );
}

export function physicsSummary(row: QueueRow): { label: string; tone: "ok" | "bad" | "neutral" } {
  return row.physicsOk
    ? { label: "PHYSICS OK", tone: "ok" }
    : { label: "PHYSICS FAIL", tone: "bad" };
}

export function Card({
  children,
  interactive = false,
  className = "",
}: {
  children: React.ReactNode;
  interactive?: boolean;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl border border-line bg-surface p-5 ${
        interactive
          ? "transition-[border-color,box-shadow] duration-150 ease-out hover:border-line-2 hover:shadow-[0_8px_30px_rgba(0,0,0,0.35)]"
          : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function Btn({
  variant = "primary",
  href,
  className = "",
  children,
  ...rest
}: {
  variant?: "primary" | "ghost";
  href?: string;
  className?: string;
  children: React.ReactNode;
} & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "className">) {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-full px-4 py-2 font-mono text-xs font-semibold transition-colors duration-150 ease-out focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2 disabled:opacity-40 disabled:pointer-events-none";
  const tones = {
    primary: "bg-accent text-accent-ink hover:bg-accent/90",
    ghost: "border border-line bg-transparent text-fg hover:border-line-2",
  } as const;
  const cls = `${base} ${tones[variant]} ${className}`;

  if (href) {
    return (
      <Link href={href} className={cls}>
        {children}
      </Link>
    );
  }
  return (
    <button type="button" className={cls} {...rest}>
      {children}
    </button>
  );
}

export function Stat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  tone?: "neutral" | "ok" | "warn" | "bad" | "accent";
}) {
  const tones = {
    neutral: "text-fg",
    ok: "text-ok",
    warn: "text-warn",
    bad: "text-bad",
    accent: "text-accent",
  } as const;
  return (
    <div>
      <div className={`font-display text-2xl font-extrabold tabular-nums ${tones[tone]}`}>
        {value}
      </div>
      <div className="mt-1 text-xs text-fg-faint">{label}</div>
    </div>
  );
}

export function Empty({
  title,
  hint,
  action,
}: {
  title: string;
  hint: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-xl border border-line bg-surface px-6 py-10">
      <p className="text-sm font-medium text-fg">{title}</p>
      <p className="max-w-md text-sm text-fg-dim">{hint}</p>
      {action}
    </div>
  );
}

export function PageTitle({ title, sub }: { title: string; sub?: string }) {
  return (
    <div>
      <h1 className="font-display text-3xl font-extrabold tracking-tight text-fg md:text-4xl">
        {title}
      </h1>
      {sub && <p className="mt-2 max-w-2xl text-sm text-fg-dim">{sub}</p>}
    </div>
  );
}
