# Maal design contract — all UI agents build against this, exactly

Read fully before touching any file. Deviations break sibling agents.

## Identity

Maal is a precision instrument for catalog trust: every value has provenance,
an adversarial audit, and a physics verdict. The UI voice is a cold, editorial
dark console — confident type, disciplined space, data set in mono. Not a
marketing site: density is a feature on review surfaces.

## Tokens — Tailwind v4 `@theme` in `web/app/globals.css` (Agent A owns this file)

```css
@theme {
  --color-ink: #0b0d10;          /* page ground */
  --color-ink-2: #0f1216;        /* raised ground / nav */
  --color-surface: #151a20;      /* cards, panels */
  --color-surface-2: #1b222b;    /* nested surfaces, hover */
  --color-line: #232b35;         /* borders */
  --color-line-2: #2f3a47;       /* strong borders, focus-adjacent */
  --color-fg: #e9ecef;           /* primary text */
  --color-fg-dim: #97a1ad;       /* secondary text */
  --color-fg-faint: #5c6672;     /* tertiary/meta */
  --color-accent: #22d3ee;       /* Maal cyan: primary actions, active nav, links */
  --color-accent-ink: #062a31;   /* text on accent fills */
  --color-ok: #34d399;           /* CONFIRMED / SAT */
  --color-warn: #fbbf24;         /* UNVERIFIED / needs review */
  --color-bad: #f87171;          /* REFUTED / UNSAT */
  --font-display: "Bricolage Grotesque", system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;
}
```

Fonts via Google Fonts `<link>` in `layout.tsx` (Bricolage Grotesque 400/600/800,
JetBrains Mono 400/500/700). Body font stays system-ui; display font ONLY on
h1/h2/nav brand/stat numbers (via a `.font-display` usage or Tailwind class).

Rules:
- Accent cyan is the ONLY brand color. ok/warn/bad are semantic verdict colors,
  never decoration. Never use warn-amber or bad-red for emphasis.
- Radius system: `rounded-xl` (12px) surfaces, `rounded-md` (6px) inputs/small
  controls, `rounded-full` chips and buttons. Nothing else.
- Borders: 1px `--color-line` everywhere; `--color-line-2` on hover/active.
- No shadows except one soft ambient on hover-raise of interactive cards:
  `shadow-[0_8px_30px_rgba(0,0,0,0.35)]`.
- Focus: `focus-visible:outline-2 outline-accent outline-offset-2` on every
  interactive element. Keyboard path is not optional.

## Type scale

- Page title: `text-3xl md:text-4xl font-display font-extrabold tracking-tight`
- Section head: `text-xl font-display font-semibold tracking-tight`
- Body: default size, `text-fg-dim` for secondary prose
- Data/values/IDs/quotes: mono, `text-[13px]`
- Meta/labels: `text-xs text-fg-faint`, sentence case. NEVER uppercase labels
  except verdict stamps (CONFIRMED / REFUTED / UNSAT), which are mono bold
  uppercase by meaning.

## Copy rules (hard)

- ZERO em or en dashes anywhere visible. Use commas, colons, periods.
- No eyebrow kickers. No "Step 1/2/3" labels. No exclamation marks.
- Empty states say what will appear and how to cause it, one sentence, plus the
  one action that causes it when applicable.
- Buttons are verbs: "Enrich this row", "Upload catalog", "Save correction".

## Motion (hard budget)

- CSS transitions only: 150ms ease-out on hover/focus/active; 250ms
  cubic-bezier(0.16,1,0.3,1) for reveals.
- Entrances: IntersectionObserver adds `.in` once; elements start
  `opacity-0 translate-y-2`. Fire once, never re-animate. Dashboard and page
  headers only; data tables never entrance-animate.
- Live/job progress: animated width transition on progress bars, subtle pulse
  (opacity 0.6..1, 1.6s) ONLY on an actively-running status dot.
- `prefers-reduced-motion: reduce`: kill entrances (visible immediately) and
  the pulse. One media query in globals.css handles it.
- No GSAP, no Lenis, no canvas, no scroll listeners, no new dependencies.

## Shared shell (Agent A owns `layout.tsx` + `components/ui.tsx`)

- Top nav, 60px, `bg-ink-2/80 backdrop-blur border-b border-line`, sticky:
  brand mark (square accent dot + "Maal" in display font) links home; links:
  Dashboard(/), Enrich(/enrich), Catalog(/catalog), Compare(/compare),
  About(/about). Active link: `text-accent` + 2px underline offset. Mobile:
  links collapse to a horizontal scroll row, no hamburger.
- Footer: one line, `text-xs text-fg-faint`, "Maal, provenance-first product
  intelligence" + link to About.
- ui.tsx keeps ALL existing exports and prop signatures (Chip, TriageMeter,
  ConfidenceStamp, verdictTone, flagTone, physicsSummary) restyled to tokens;
  add: `Card` (surface wrapper), `Btn` (variant: "primary" | "ghost"),
  `Stat` ({label, value, tone?}), `Empty` ({title, hint, action?: ReactNode}),
  `PageTitle` ({title, sub?}). Pages import these; do not redefine locally.

## Per-page directives

- **Dashboard (/)**: the one expressive surface. Full-height intro band:
  display headline "Every value earns its place.", one-line sub about
  provenance + physics + audit, primary CTA to /enrich, ghost CTA to /catalog.
  Below: live stats row (runs, rows, confirmed %, flagged) from real data via
  existing lib calls, mono numbers; recent jobs list as interactive cards.
  Entrance choreography allowed here only.
- **Enrich**: two clear modes on one page, single row vs file upload, presented
  as two Cards side by side (stack on mobile), not tabs. Drag-and-drop border
  highlight on the upload card. Field labels above inputs, mono input text.
- **Job page**: progress header (bar + counts + status dot), then result rows
  as expandable records. Keep polling logic intact.
- **Catalog**: dense review queue: sticky filter chip row under the nav,
  triage-ranked table rows, verdict stamps in mono. Density is the point:
  14px row text, 8px vertical padding, hairline dividers.
- **Row detail**: provenance ledger. Identity block, five description formats
  in labeled mono blocks with char counts, attribute table with QC stamps,
  expandable evidence quotes (native `<details>`, restyled), Z3 dossier panel:
  ok = `--color-ok` left border, unsat = `--color-bad` left border with the
  plain-language reasons. Corrections form inline, mono inputs.
- **Compare**: side-by-side diff table, changed cells tinted
  `bg-accent/8` with mono values.
- **About**: editorial page: display-type manifesto paragraphs, pipeline
  stages as an asymmetric list (not equal cards), no diagrams-as-images.

## Hard checks before an agent returns

- `npm run build` passes with zero errors from the repo's `web/` dir.
- No new npm dependencies. No inline hex colors in pages: token classes only.
- All existing data flows / API calls / props preserved: this is a reskin plus
  layout recomposition, never a data-logic change.
- Grep your changed files for em/en dashes in visible strings: must be zero.
