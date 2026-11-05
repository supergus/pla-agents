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
