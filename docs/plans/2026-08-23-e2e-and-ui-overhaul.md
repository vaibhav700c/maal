# Maal: end-to-end verification + UI overhaul — orchestration plan

Constraint: cohesive design voice + correctness, cost-routed. Orchestrator holds
the design contract (docs/design-brief.md) and verification; agents implement.
No GEMINI_API_KEY on this machine, so live-LLM E2E is impossible here: offline
end-to-end = pytest (69 mocked-LLM tests) + eval scorer + web build + browser
verification of every route with real artifacts where producible.

Failure modes: agent breaks the Next build -> caught by `npm run build` gate each
agent must pass plus orchestrator re-verify; plausible-but-wrong claims about the
pipeline -> caught by Haiku audit actually running pytest/build; design drift
between page agents -> prevented by the pinned brief + shared components landing
before page agents start; file conflicts -> disjoint file ownership per agent.

Ledger:
- repo audit, tests, build, artifact bootstrap -> Haiku (cheap verification)
- design foundation: globals.css, layout.tsx, ui.tsx -> Sonnet A
- pages: dashboard, enrich, about -> Sonnet B (after A)
- pages: catalog, jobs/[id], row/[mpn], compare, corrections-form, run-panel -> Sonnet C (after A)
- integration verify (build + browser routes + brief compliance), fix dispatch -> orchestrator

Stages: 1) Haiku audit + Sonnet A in parallel. 2) Sonnet B + C in parallel.
3) Orchestrator verification loop; fixes dispatched back by SendMessage.
