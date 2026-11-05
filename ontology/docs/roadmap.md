# Roadmap: optional extensions (not modelled yet)

- **Risk/contingency %** line, raised automatically when a similarity match is low-confidence or a spec is unclear.
- **Payment terms cost of money** (e.g. Net 60 adds ~0.5-1%).
- **Currency**: a single quote currency plus one FX rate and rate date (no hedging).
- **Lead time** estimate with the "long pole" component identified.
- **QuoteSource** on each cost: library estimate / supplier quote / manual.
- **Margin override** with a recorded reason (customer, competition, strategic).
- **Overhead in the work-center rate** instead of % of COGS (see simplifications.md #1).
- **Source mappings**: load the library and rate tables from spreadsheets/ERP exports into RDF (e.g. a YAML or R2RML mapping), with CI checks for drift.
- **Docs publishing**: generate HTML with pyLODE or Widoco and publish to GitHub Pages so the namespace IRIs resolve; tag releases with version IRIs.
- **Agent use**: use these terms as the shared vocabulary for task handoffs between ingest, BOM, costing and pricing agents.

## Done / live (Nov 5, 2026)

These were roadmap items; they are live now and tracked in [PROJECT.md](PROJECT.md) §8:

- **Agent use** of these terms as the shared vocabulary for the PLA (intake → validate → match → cost → approve → send), including `SimilarityMatch` for RFQ-line matches.
- **PLA module** (`rfq-pla.ttl`), CQ9–CQ12, and the `pla_agents` orchestrator in the same repo.
- **Demo console + Worker** at pla.chriscouch.net (`pla-demo`, Worker `rfq-pla`, Workflow `rfq-pla-run`, $20/day budget, Secret? gate).

Still open: pyLODE/Widoco docs publishing, source mappings, and the optional costing extensions above.

