import fs from "node:fs";
import path from "node:path";
import Link from "next/link";

const ROOT = process.env.MAAL_ROOT ?? path.join(process.cwd(), "..");

function liveStats() {
  let rows = 0;
  let attributes = 0;
  try {
    const csv = fs.readFileSync(path.join(ROOT, "output", "result.csv"), "utf8");
    rows = Math.max(0, csv.split("\n").filter(Boolean).length - 1);
  } catch {
    /* no artifacts yet */
  }
  try {
    const sidecar = path.join(ROOT, "output", "state.jsonl");
    for (const line of fs.readFileSync(sidecar, "utf8").split("\n")) {
      if (!line.trim()) continue;
      try {
        const rec = JSON.parse(line);
        attributes += rec?.row_result?.extraction?.attributes?.length ?? 0;
      } catch {
        /* skip malformed line */
      }
    }
  } catch {
    /* none */
  }
  return { rows, attributes };
}

const STAGES = [
  {
    n: "01",
    title: "Understand the row",
    body: "Placeholder brands are stripped, supplier codes parsed, cryptic abbreviations expanded. What remains is a clean seed.",
  },
  {
    n: "02",
    title: "Classify",
    body: "Every product lands in a distributor taxonomy — department, class, fine level, full classpath, UNSPSC code.",
  },
  {
    n: "03",
    title: "Source from the maker",
    body: "The manufacturer's own domain is located and searched for the exact part. Marketplaces are refused by policy, not by luck.",
  },
  {
    n: "04",
    title: "Extract with evidence",
    body: "Attributes come back attached to verbatim quotes. A value without its source sentence does not exist.",
  },
  {
    n: "05",
    title: "Try to break it",
    body: "A second model audits every claim against its sources, hunting for refutations. Unprovable claims are marked, not kept quietly.",
  },
  {
    n: "06",
    title: "Obey physics",
    body: "A Z3 theorem prover checks the numbers the way an engineer would: watts equal volts times amps, a disc's diameter beats its arbor, units stay in plausible ranges. Failures name their fields.",
  },
  {
    n: "07",
    title: "Write like the house",
    body: "Five descriptions — till receipt to search title — are assembled by templates under strict character limits, unit styles and fraction rules. No free-form generation touches the record.",
  },
];

export default function AboutPage() {
  const { rows, attributes } = liveStats();

  return (
    <article className="mx-auto max-w-3xl">
      <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-ink2">
        About
      </p>
      <h1 className="mt-3 font-sans text-3xl font-bold leading-tight">
        Maal turns scattered product data into records a buyer can trust.
      </h1>
      <p className="mt-4 max-w-2xl text-base leading-relaxed text-ink2">
        Industrial catalogs arrive as fragments — &ldquo;Milw 14&quot;x.045&quot;x1&quot; Metal
        Cut Off Disc&rdquo;, six spellings of one manufacturer, empty fields wherever you
        look. Maal reads those fragments and returns complete, standardized,
        publish-ready product records. And it shows its work on every single value.
      </p>

      <div className="mt-8 grid grid-cols-3 gap-3">
        <div className="rounded-[3px] border border-line bg-panel px-4 py-3">
          <div className="font-mono text-xl font-semibold tabular-nums">
            {rows.toLocaleString()}
          </div>
          <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wide text-ink2">
            Products enriched now
          </div>
        </div>
        <div className="rounded-[3px] border border-line bg-panel px-4 py-3">
          <div className="font-mono text-xl font-semibold tabular-nums">
            {attributes.toLocaleString()}
          </div>
          <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wide text-ink2">
            Evidence-backed attributes
          </div>
        </div>
        <div className="rounded-[3px] border border-line bg-panel px-4 py-3">
          <div className="font-mono text-xl font-semibold">252</div>
          <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wide text-ink2">
            Delivery-format columns per record
          </div>
        </div>
      </div>

      <h2 className="mt-12 font-sans text-lg font-bold">How a row becomes a record</h2>
      <ol className="mt-4 flex flex-col border-l border-line pl-6">
        {STAGES.map((s) => (
          <li key={s.n} className="relative pb-6 last:pb-0">
            <span className="absolute -left-[31px] top-1 flex h-2 w-2 rounded-full bg-accent" />
            <span className="font-mono text-[10px] uppercase tracking-wider text-accent">
              {s.n}
            </span>
            <h3 className="mt-0.5 font-sans text-sm font-semibold">{s.title}</h3>
            <p className="mt-1 max-w-2xl text-sm leading-relaxed text-ink2">{s.body}</p>
          </li>
        ))}
      </ol>

      <h2 className="mt-10 font-sans text-lg font-bold">
        What makes a value trustworthy here
      </h2>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <Principle
          title="Provenance or nothing"
          body="Each attribute carries its source URL and the exact sentence behind it. Click any value in the ledger and read why it is true."
        />
        <Principle
          title="Adversarial, not confident"
          body="A second model is paid to disagree with the first. Confirmed claims pass; unsupported ones wear an amber badge until a human settles them."
        />
        <Principle
          title="Physics as referee"
          body="Constraints are checked symbolically, so impossible products cannot ship silently. When volts, amps and watts disagree, the unsat core names the guilty fields in plain language."
        />
        <Principle
          title="Blank over invented"
          body="When nothing can be verified, the field stays empty with a review reason. A missing value costs a lookup; a wrong one costs a customer."
        />
      </div>

      <div className="mt-10 flex flex-wrap gap-3 border-t border-line pt-6">
        <Link
          href="/enrich"
          className="rounded-[3px] bg-accent px-4 py-2 font-mono text-xs font-semibold text-white hover:bg-accent/90"
        >
          Try it — enrich a product
        </Link>
        <Link
          href="/compare"
          className="rounded-[3px] border border-line bg-panel px-4 py-2 font-mono text-xs font-semibold hover:border-ink"
        >
          See the ground-truth check
        </Link>
        <Link
          href="/"
          className="rounded-[3px] border border-line bg-panel px-4 py-2 font-mono text-xs font-semibold hover:border-ink"
        >
          Open the console
        </Link>
      </div>
    </article>
  );
}

function Principle({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-[3px] border border-line bg-panel p-4">
      <h3 className="font-sans text-sm font-semibold">{title}</h3>
      <p className="mt-1 text-sm leading-relaxed text-ink2">{body}</p>
    </div>
  );
}
