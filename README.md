# rfq-ontology

A tutorial-grade, OWL 2 DL toy ontology for a manufacturing **RFQ-to-quote** process,
managed in GitHub with a PR process and CI. It is a teaching project on data ontology
for orchestrated agentic systems: agents that ingest an RFQ, check it, build a BOM,
estimate costs and price a quote need a shared, testable vocabulary. This repo is that
vocabulary for one small business process.

## The process being modelled

1. Receive an **RFQ package** from a customer (commercial terms, delivery terms + Incoterm, technical requirements).
2. **Check completeness**: does it contain every critical element we need to quote?
3. Build the **engineering BOM** and record **make vs buy** on each line.
4. **Bought** components: estimate cost from the most similar entry in our **component library**.
5. **Made** components: take the similar entry's **routing**, cost each step at **work-center rates** (setup per lot + run per unit), and sum.
6. **COGS** = material (with scrap) + conversion.
7. Add **overhead** and **SG&A** as % of COGS from the current rate table.
8. Add the **target margin on price** for the product category.
9. Price each **quantity break**; add one-time **NRE** and **freight** (only if the Incoterm makes us pay it).

## What is in the repo

```
ontology/   rfq.ttl (root, owl:imports all modules) + rfq-core, rfq-provenance, rfq-package,
            rfq-bom, rfq-library, rfq-costing, rfq-pla (.ttl) + catalog-v001.xml (import IRIs -> local files)
data/       reference.ttl (library, routings, work centers, rate tables)
            rfq-1001.ttl (COMPLETE RFQ, bracket BRK-100, worked example, quote revs A and B)
            rfq-1002-incomplete.ttl (INCOMPLETE RFQ: no Incoterm, no material/finish spec)
shapes/     rfq-completeness.ttl (SHACL, closed-world completeness + BOM/match data quality)
queries/    cq1..cq12 SPARQL competency queries
scripts/    quote.py (computes the quote from the graph), run_queries.py, reason.sh (ROBOT), rfqlib.py
tests/      pytest: parsing, labels, SHACL, competency queries, exact worked-example numbers, reasoner
docs/       concepts, formulas, worked example, simplifications, competency questions, sessions, roadmap
```

Project write-up (goals, design, PLA, demo, CI/CD): [docs/PROJECT.md](docs/PROJECT.md).
PLA vocabulary (programs, issues, tools, tool runs, approval gate): [docs/pla-model.md](docs/pla-model.md).
Sample LLM prompts (what the system sends to Llama for each AI step): [docs/sample-llm-prompts.md](docs/sample-llm-prompts.md).

Ontology size: 49 classes, 47 object properties, 55 datatype properties in the `rfq:`
namespace (plus 2 classes and 5 properties reused from W3C PROV-O), and 11 individuals
(6 Incoterms, 3 units of measure, Make, Buy). Namespace:
`https://supergus.github.io/rfq-ontology/ns#` (planned GitHub Pages location; not yet published).

## Run the checks

Python 3.10+ and, for the OWL reasoning step, Java 11+ and [ROBOT](https://robot.obolibrary.org).

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# Python-only checks (parsing, SHACL, SPARQL competency queries, worked-example numbers)
python -m pytest -q

# Compute and print the quote breakdown (also writes build/quote-results.ttl with PROV links)
python scripts/quote.py --ttl build/quote-results.ttl

# Print every competency query's answer
python scripts/run_queries.py

# OWL checks: OWL 2 DL profile, HermiT consistency + unsatisfiable classes, ROBOT report,
# HermiT over ontology + data (classifies RFQ-1001 as CompleteRFQ)
curl -fsSL -o robot.jar https://github.com/ontodev/robot/releases/download/v1.9.11/robot.jar
ROBOT_JAR=robot.jar scripts/reason.sh
REQUIRE_REASONER=1 python -m pytest -q   # now also runs the reasoner assertions
```

CI (`.github/workflows/ci.yml`, workflow **tests**) runs all of the above on every PR and on
pushes to `main`; the `build/` folder (reasoned graph, ROBOT report, profile reports, quote
results) is uploaded as a workflow artifact.

## Worked example result (RFQ-1001, quote Q-1001-B, Incoterm DAP)

| Qty | Unit COGS | Unit price | Extended | NRE | Freight | **Quote total** |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 37.4146 | 60.86 | 6,086.00 | 1,850.00 | 80.00 | **8,016.00** |
| 1,000 | 35.6596 | 58.01 | 58,010.00 | 1,850.00 | 800.00 | **60,660.00** |
| 10,000 | 35.4841 | 57.72 | 577,200.00 | 1,850.00 | 8,000.00 | **587,050.00** |

Full arithmetic: [docs/worked-example.md](docs/worked-example.md).

## Tutorial sessions

See [docs/sessions.md](docs/sessions.md): 1 scope + competency questions; 2 RFQ package +
completeness; 3 BOM + make/buy; 4 library, routings, rate tables; 5 cost chain + provenance;
6 sample data, SPARQL, SHACL, CI, docs publishing.


## Related repositories
- This repo (`rfq-ontology`) — tutorial OWL ontology for the RFQ-to-quote process.
- [supergus/rfq-agents](https://github.com/supergus/rfq-agents) — PLA orchestrator and tools; pins this ontology via `ontology.lock`.
- [supergus/rfq-demo](https://github.com/supergus/rfq-demo) — live PLA management console / quote demo at https://pla.chriscouch.net.
- Leaf Tender is a separate ontology management project hosted at https://leaftender.chriscouch.net (not part of this RFQ demo trio).

## Process

`main` is protected; all changes go through a PR, the `tests` workflow, and a manual
`Grok Bot QC` commit status. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Tooling choices

- **Turtle** for every file (diffs cleanly). Edit in Protégé or by hand.
- **ROBOT + HermiT** for merge, OWL 2 DL profile validation, reasoning and the QC report. ROBOT's
  report runs with `--fail-on ERROR`; its ~110 WARN items are mostly `missing_definition`
  (we use `rdfs:comment` instead of the OBO `IAO:0000115` definition property).
- **pySHACL** for closed-world validation, **rdflib** for SPARQL and the quote script, **pytest** for tests.
- Docs generation (pyLODE to GitHub Pages) is on the [roadmap](docs/roadmap.md), not built yet.
