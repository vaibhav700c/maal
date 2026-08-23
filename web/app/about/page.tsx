import fs from "node:fs";
import path from "node:path";
import { Card, Btn, PageTitle, Stat } from "@/components/ui";
import RevealOnMount from "@/components/reveal";

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
    body: "Every product lands in a distributor taxonomy: department, class, fine level, full classpath, UNSPSC code.",
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
    body: "Five descriptions, till receipt to search title, are assembled by templates under strict character limits, unit styles and fraction rules. No free-form generation touches the record.",
  },
];

export default function AboutPage() {
  const { rows, attributes } = liveStats();

  return (
    <article className="mx-auto max-w-3xl">
      <RevealOnMount />
      <div className="reveal">
        <PageTitle
          title="Maal turns scattered product data into records a buyer can trust."
          sub={
            'Industrial catalogs arrive as fragments: "Milw 14"x.045"x1" Metal Cut Off Disc", six spellings of one manufacturer, empty fields wherever you look. Maal reads those fragments and returns complete, standardized, publish-ready product records. And it shows its work on every single value.'
          }
        />
      </div>

      <div className="mt-8 grid grid-cols-3 gap-6 border-y border-line py-6">
        <Stat label="Products enriched now" value={rows.toLocaleString()} />
        <Stat label="Evidence-backed attributes" value={attributes.toLocaleString()} />
        <Stat label="Delivery-format columns per record" value={252} />
      </div>

      <h2 className="mt-14 text-xl font-display font-semibold tracking-tight text-fg">
        How a row becomes a record
      </h2>
      <ol className="mt-4 flex flex-col divide-y divide-line border-t border-line">
        {STAGES.map((s) => (
          <li key={s.n} className="flex gap-6 py-6 md:gap-10">
            <span className="w-10 shrink-0 font-display text-3xl font-extrabold tabular-nums text-fg-faint md:w-14 md:text-4xl">
              {s.n}
            </span>
            <div className="min-w-0">
              <h3 className="font-display text-base font-semibold tracking-tight text-fg">
                {s.title}
              </h3>
              <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-fg-dim">{s.body}</p>
            </div>
          </li>
        ))}
      </ol>

      <h2 className="mt-14 text-xl font-display font-semibold tracking-tight text-fg">
        What makes a value trustworthy here
      </h2>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
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

      <div className="mt-12 flex flex-wrap gap-3 border-t border-line pt-8">
        <Btn href="/enrich">Enrich a product</Btn>
        <Btn href="/compare" variant="ghost">
          See the ground-truth check
        </Btn>
        <Btn href="/" variant="ghost">
          Open the console
        </Btn>
      </div>
    </article>
  );
}

function Principle({ title, body }: { title: string; body: string }) {
  return (
    <Card>
      <h3 className="font-display text-base font-semibold tracking-tight text-fg">{title}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-fg-dim">{body}</p>
    </Card>
  );
}
