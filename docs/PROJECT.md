# RFQ Ontology Tutorial: Project Write-up

*HAPP Research · Chris Couch · repos: `supergus/rfq-ontology`, `supergus/rfq-agents`, `supergus/rfq-demo` · live demo: pla.chriscouch.net · Nov 4, 2026*

## 1. Goal: demonstrate a managed ontology

This project shows, at toy scale, what it takes to run an ontology the way we run software.

**Ontology.** An ontology is a shared, machine-readable vocabulary for a domain. It names the *things* (RFQ, BOM line, work center, quote), the *relationships* between them (a BOM line *has a similarity match* to a library entry), and the *rules* they must obey (a delivery-terms record has exactly one Incoterm). People and programs both read it, so "quote", "COGS" and "quantity break" mean the same thing everywhere. Here the ontology is written in **OWL 2** (the W3C Web Ontology Language), kept inside the OWL 2 DL profile, and stored as Turtle text files.

**Managed.** A managed ontology is not a diagram on a wiki. It is:
- **Version-controlled in git.** Every term lives in a text file with full history.
- **Changed through pull requests with review.** Nobody pushes to `main`. Changes are reviewed as diffs.
- **Tested in CI** on every PR:
  - the Turtle parses;
  - the OWL is in the OWL 2 DL profile, and the HermiT reasoner finds it consistent, with no unsatisfiable classes;
  - SHACL shapes validate the sample data;
  - SPARQL **competency questions** (the business questions the model must answer) return the expected answers;
  - the worked-example quote numbers match to the cent.
- **Provenance-aware.** Computed results link back to the exact inputs and rate rows that produced them (W3C PROV-O). Asking "why is this price what it is?" becomes a query.

**Why it matters.** This is a stepping stone. The bigger aim is ontologies as the **shared vocabulary for orchestrated agentic systems**: agents that ingest, check, cost and price need a common, testable language for handing off work. The toy proves the tooling and the process. Real-world ontology work, which means mapping messy enterprise data sources (ERP, PLM, spreadsheets) onto that vocabulary, is expected to be the long pole.

## 2. The toy use case: manufacturing RFQ to quote

A customer sends a **request for quotation (RFQ)** for a part. We decide whether we can quote it, estimate the cost, and price it at several volumes.

### The 9-step process

1. Receive an **RFQ package** from a customer: commercial terms, delivery terms and Incoterm, and technical requirements.
2. **Check completeness**: does it contain every critical element we need to quote?
3. Build the **engineering BOM** and record **make vs buy** on each line.
4. **Bought** components: estimate cost from the most similar entry in our **component library**.
5. **Made** components: take the similar entry's **routing**, cost each step at **work-center rates** (setup per lot plus run per unit), and sum.
6. **COGS** = material (with scrap) + conversion.
7. Add **overhead** and **SG&A** as % of COGS from the current rate table.
8. Add the **target margin on price** for the product category.
9. Price each **quantity break**, then add one-time **NRE** and **freight** (freight only if the Incoterm makes us pay it).

The worked example is **RFQ-1001 rev B** from Northwind Agricultural Equipment: product **BRK-100**, a welded mounting bracket, with quantity breaks 100 / 1,000 / 10,000, Incoterm **DAP**, and quote **Q-1001-B** dated 2026-10-27, valid until 2026-11-26.

### Realism changes adopted after MBA Bot's critique

- **Similarity match is a recorded fact**, not a calculation inside the ontology. A `SimilarityMatch` stores the score, the method (for example "attribute-weighted v1" or "part-number exact"), a confidence flag, and an optional manual override with its own unit cost.
- **Quantity breaks.** Every estimate belongs to one (RFQ line, quantity break), so unit cost falls with volume as setup is spread over a bigger lot.
- **Versioned work-center rates.** Rates are rows with an effective date and a source. The FY2026 weld rate ($75/h) supersedes FY2025 ($70/h). Estimates point to the exact row they used, so stale quotes can be found.
- **Setup vs run hours** on each routing step.
- **Scrap rate** on each BOM line.
- **Make/buy** recorded as a decision on the BOM line, not a fixed subclass.
- **NRE** (tooling, first-article inspection) as a separate one-time line, not spread into unit price.
- **Incoterms and freight.** Six Incoterms (EXW, FCA, FOB, CIF, DAP, DDP) as individuals with `sellerPaysFreight`, which decides whether a freight line appears.
- **Revisions** on RFQs and quotes (`supersedes` is transitive).
- **Quote validity** (`validUntil`).
- **Margin on price**, not markup on cost: `price = cost / (1 − m)`. 25% margin is a 33.3% markup.

### Out of scope

Named simplifications (`docs/simplifications.md`):
1. Overhead as % of COGS. Real alternative: absorb it into the work-center burden rate.
2. Margin by product category only.
3. Library costs taken at face value. Cost date and basis quantity are recorded, but no adjustment is applied.
4. Lot size = quantity break.
5. Make/buy is an input, not optimized.
6. Engineering BOM only. No manufacturing BOM.
7. One currency (USD). No taxes, payment-terms cost or contingency.
8. Similarity computed outside the ontology.
9. PROV-O terms declared locally (same IRIs) to keep CI offline.
10. Dates as `xsd:dateTime`, because `xsd:date` would break OWL 2 DL.

Not modelled: multi-plant routing alternatives, learning curves, subcontract steps, inventory/WIP, warranty reserves.

Roadmap (`docs/roadmap.md`): risk/contingency %, payment-terms cost of money, currency/FX, lead time, cost source per line, margin override with reason, overhead inside rates, source mappings from spreadsheets/ERP (YAML or R2RML) with drift checks, docs publishing (pyLODE/Widoco to GitHub Pages), and agent use.

## 3. How we're building

### Architecture: three layers

| Layer | What it holds | Files |
|---|---|---|
| **1. Ontology** | The vocabulary: classes, properties, axioms (OWL 2 DL) | `ontology/*.ttl` |
| **2. Data + shapes** | Instance data (library, rates, RFQs) and SHACL completeness rules | `data/*.ttl`, `shapes/*.ttl` |
| **3. Tools** | Code that computes, queries and orchestrates | `scripts/`, `queries/`, `tests/`; the PLA and its tools live in `supergus/rfq-agents` |

Rule: OWL describes meaning, SHACL checks data, SPARQL asks questions, and Python does arithmetic.

### Cost formulas (`docs/formulas.md`)

```
unit_material   = Σ lines  quantityPer × unit_cost × (1 + scrapRate)
unit_conversion = Σ make lines Σ steps (setupHours / Q + runHours × quantityPer) × rate(work center)
COGS            = unit_material + unit_conversion
loaded          = COGS × (1 + overhead% + SG&A%)
unit_price      = round_to_cent( loaded / (1 − targetMarginOnPrice) )
total           = unit_price × Q + NRE + freight      (freight only if Incoterm.sellerPaysFreight)
```

Order matters. Overhead and SG&A are applied to COGS first, then margin is applied to the loaded cost. Doing it the other way gives a wrong price.

### Worked example (RFQ-1001, quote Q-1001-B, DAP)

Inputs: unit material $9.8146, setup $195.00 per lot, run cost $25.65 per bracket, overhead 12%, SG&A 10%, margin 25%, freight $0.80 per unit, NRE $1,850.

| Qty | Unit COGS | Unit price | Extended | NRE | Freight | **Quote total** |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 37.4146 | $60.86 | $6,086.00 | $1,850.00 | $80.00 | **$8,016.00** |
| 1,000 | 35.6596 | $58.01 | $58,010.00 | $1,850.00 | $800.00 | **$60,660.00** |
| 10,000 | 35.4841 | $57.72 | $577,200.00 | $1,850.00 | $8,000.00 | **$587,050.00** |

Biggest cost driver: weld op 30 on the base plate, $11.25 per bracket. `tests/test_quote.py` asserts these numbers exactly.

### Toolset

| Tool | Why |
|---|---|
| **OWL 2 (DL profile)** | W3C standard, decidable, works with off-the-shelf reasoners |
| **Turtle** | Readable text format that diffs cleanly in git |
| **Protégé** | Free visual editor, optional (hand editing is fine) |
| **ROBOT + HermiT** | Merge, OWL 2 DL profile check, consistency/classification, QC report (`--fail-on ERROR`) |
| **pySHACL** | Closed-world validation, which reports exactly what is missing |
| **rdflib** | Python RDF library for loading graphs, SPARQL, and the quote script |
| **SPARQL** | Competency questions as executable queries (CQ1 to CQ8) |
| **pytest** | One test suite for parsing, SHACL, queries, numbers and reasoner results |
| **GitHub Actions** | Runs the `tests` workflow on every PR and on pushes to `main` |
| **pyLODE / Widoco** (later) | Generate HTML docs so namespace IRIs resolve on GitHub Pages |
| **PROV-O** | W3C provenance vocabulary that links results to their inputs |

### Git structure

```
rfq-ontology/
├── ontology/   rfq.ttl (root, imports all) + rfq-core, rfq-provenance, rfq-package,
│               rfq-bom, rfq-library, rfq-costing (.ttl) + catalog-v001.xml
├── data/       reference.ttl (library, routings, work centers, rate tables)
│               rfq-1001.ttl (complete RFQ, worked example, quote revs A and B)
│               rfq-1002-incomplete.ttl (no Incoterm, no material/finish spec)
├── shapes/     rfq-completeness.ttl (SHACL)
├── queries/    cq1 … cq8 SPARQL competency queries
├── scripts/    quote.py, run_queries.py, reason.sh (ROBOT), rfqlib.py
├── tests/      pytest suites: ontology, SHACL, queries, quote, reasoner
├── docs/       concepts, formulas, worked example, simplifications,
│               competency questions, sessions, roadmap
├── build/      generated outputs (reasoned graph, ROBOT report, quote results), uploaded as a CI artifact
└── .github/    workflows/ci.yml (workflow "tests"), PR template
```

### Process

1. Branch from `main`.
2. Make the change and run the checks locally.
3. Open a PR from the template.
4. CI workflow **`tests`** runs: Turtle parsing, then OWL 2 DL profile + HermiT + ROBOT report, then SHACL, competency queries, worked-example numbers and reasoner inferences, then prints the quote breakdown.
5. A reviewer reads the diff. Only when the review is done and `tests` is green does the reviewer post the manual commit status **`Grok Bot QC` = success**.
6. Merge.

`main` is protected: PR required, required status `Grok Bot QC`, 0 required approvals, enforced for admins, no force pushes, no deletions. The tutorial runs as six sessions (`docs/sessions.md`), and each session ends with one such PR.

## 4. The ontology itself

Namespace: `https://supergus.github.io/rfq-ontology/ns#`. Size: **40 classes, 30 object properties, 34 datatype properties** in `rfq:`, plus 2 classes and 4 properties reused from PROV-O, and 11 individuals (6 Incoterms, 3 units of measure, Make, Buy).

### Main classes by module

| Module | Main terms |
|---|---|
| **core** | `Customer`, `UnitOfMeasure` (each, hour, USD), `revision`, `supersedes` / `isSupersededBy`, `identifier` |
| **provenance** | `prov:Entity`, `prov:Activity`, `prov:wasDerivedFrom`, `prov:wasGeneratedBy`, `prov:used`, `CostRollup` |
| **package** | `RFQPackage`, `RFQLine`, `QuantityBreak`, `CommercialTerms`, `DeliveryTerms`, `Incoterm`, `TechnicalRequirement` > `Drawing` / `MaterialSpec` / `FinishSpec`, defined class `CompleteRFQ` |
| **bom** | `Product`, `ProductCategory`, `EngineeringBOM`, `BOMLine` (`quantityPer`, `scrapRate`, `sourcingDecision`), `Component`, `SourcingDecision` = {Make, Buy} |
| **library** | `ComponentLibraryEntry` (`libraryUnitCost`, `costDate`, `costBasisQuantity`), `SimilarityMatch` (`similarityScore`, `similarityMethod`, `confidence`, `manualOverride`, `overrideUnitCost`), `Routing`, `ProcessStep` (`setupHours`, `runHours`, `stepSequence`), `WorkCenter` |
| **costing** | `RateAssumption` > `WorkCenterRate` / `OverheadRate` / `SGARate` / `MarginTarget` / `FreightRate` (with `effectiveDate`, `rateSource`); `Quote` (`quoteDate`, `validUntil`), `QuotePriceBreak`, `CostEstimate` > `MaterialCost` / `ConversionCost` / `COGS` / `LoadedCost` / `NRECost` / `FreightCost` |

### Key relationships

- RFQ package → lines (`hasLine` / `lineOf`) → quantity breaks, product, and delivery terms → one Incoterm (functional).
- Product → engineering BOM → BOM lines → component, plus one sourcing decision (functional).
- BOM line ↔ `SimilarityMatch` (`hasSimilarityMatch` / `forBOMLine`) → library entry → routing → process steps → work center.
- Cost estimate → `prov:wasDerivedFrom` → the exact rate rows and matches used, and `prov:wasGeneratedBy` → a `CostRollup` activity.
- Quote rev B `supersedes` rev A. Newer rate rows supersede older ones (transitive).

### Design principles

- **OWL for structure and classification.** Hierarchy, domains/ranges, functional properties, inverses, disjointness, the enumerated `SourcingDecision`, and the defined class `CompleteRFQ`.
- **SHACL for completeness.** OWL is *open-world*: a missing Incoterm is "unknown", not "absent", so a reasoner never flags an incomplete RFQ. SHACL is closed-world and reports exactly what is missing.
- **SPARQL for questions.** Eight competency questions (completeness, make/buy, similarity used, COGS by break, conversion drivers, stale rates, manual review, freight by Incoterm).
- **Python for arithmetic.** OWL has no practical arithmetic. `scripts/quote.py` computes and writes results back with PROV links.

### RFQ-1001 vs RFQ-1002

- **RFQ-1001** is complete. HermiT *proves* it is a `CompleteRFQ` (CI checks this), SHACL passes, and it is fully quoted.
- **RFQ-1002** is missing an Incoterm and a material/finish spec. The reasoner concludes nothing (open world). SHACL and CQ1 report exactly those two gaps.

This contrast is the core teaching moment: meaning in OWL, validation in SHACL.

Other built-in stories: CQ6 flags quote rev A for using the superseded FY2025 weld rate, and CQ7 flags BL-5 (serial label) for manual review because it has no library match.

## 5. Build summary: what was delivered

A self-contained summary of the initial build of [supergus/rfq-ontology](https://github.com/supergus/rfq-ontology) (public). Design detail is in sections 3 and 4; this section records what was actually delivered and checked.

### Ontology

- **40 classes, 30 object properties, 34 datatype properties** in the `rfq:` namespace (`https://supergus.github.io/rfq-ontology/ns#`). The IRIs won't resolve until GitHub Pages is set up.
- Reuses 2 PROV-O classes and 4 PROV-O properties, declared locally.
- **11 named individuals:** Incoterms EXW, FCA, FOB, CIF, DAP, DDP; three units; Make and Buy.
- Split into modules: core, provenance, package, BOM, library, costing (see "Main classes by module" in section 4).
- Includes sample data, SHACL shapes, 8 competency queries (`queries/`), and 6 tutorial sessions in `docs/`.
- The similarity match is a recorded fact with a score, method, confidence and manual override. Quantity breaks are modeled.

### Checks

- **32 tests pass**, including HermiT consistency and the OWL 2 DL profile check.
- ROBOT report: **0 errors, 113 warnings**, mostly `missing_definition` because we use `rdfs:comment` for definitions.
- **RFQ-1001** passes SHACL and the reasoner classifies it as `CompleteRFQ`.
- **RFQ-1002** fails SHACL with exactly two messages: a missing Incoterm and a missing material or finish spec. The reasoner draws no conclusion about it, which is the open-world gotcha (see "RFQ-1001 vs RFQ-1002" in section 4).

### Worked example

BRK-100 bracket, DAP, NRE $1,850, freight $0.80 per unit. Unit material is $9.8146 at every quantity. Full arithmetic is in `docs/worked-example.md`.

| Qty | Unit COGS | Unit price | Total quote |
|---:|---:|---:|---:|
| 100 | 37.4146 | $60.86 | $8,016.00 |
| 1,000 | 35.6596 | $58.01 | $60,660.00 |
| 10,000 | 35.4841 | $57.72 | $587,050.00 |

Setup cost spread over the lot is why the unit price drops with volume.

### Process

- `main` is protected like homebrew-llm: PR required, required status "Grok Bot QC", enforced for admins, no force pushes or deletions.
- A direct push to `main` was rejected (GH006).
- PR #1 moved CI to `setup-java@v5` and merged only after the QC status was posted once `tests` passed.
- CI runs on the GitHub Actions workflow `tests`. Note: `tests` itself is not a required check; it's enforced by QC being posted only after it passes.

### Changes from plan

- Dates are `xsd:dateTime`, because `xsd:date` isn't an OWL 2 datatype and failed the DL profile check.
- Trimmed classes to stay at 40: Party, Supplier/`preferredSupplier`, RevisedDocument, two PROV activity subclasses; OverheadCost and SGACost merged into LoadedCost.
- The conversion formula multiplies run hours by BOM line quantity (identical at quantity 1).
- Lot size equals the quantity break.
- **Not built yet:** pyLODE docs on GitHub Pages, optional extensions.
- **Not verified:** tested only on Python 3.13 locally (CI uses 3.12); not opened in Protégé.

## 6. The top-level orchestrated agent: the PLA

**Question:** *"In our example, what are we using for the top level orchestrated agent?"*

**Answer:** the **PLA, Program Lifecycle Agent** (Chris's term). It manages the overall quote program end to end. It is aware of each RFQ's status, open issues, tasks and next step, and it calls sub-tools or sub-agents to do the work.

### Design

- **Orchestrator:** a small Python tool-calling loop with no agent framework. The PLA reads the program's current state from the graph, picks the next tool by its declared contract, and SHACL-validates every result before writing it back.
- **Deterministic tools** (plain Python functions):
  - `validate_rfq`: pySHACL; gaps become `Issue` records
  - `explode_bom`
  - `cost_quote`: one quote per quantity break
  - `run_competency_queries`: SPARQL competency questions
  - `render_quote`
- **Agentic tools** (Workers AI Llama 3.3 70B with structured output):
  - `parse_rfq_document`: RFQ PDF or email to draft RFQ; low-confidence fields become Issues, not guesses; canned fallback if the model is down
  - `match_library_part`: writes a `SimilarityMatch` with score and method
  - `explain_quote`: plain-language summary of the computed numbers, never calculating them itself
- **Tools in the ontology:** each tool is a `Tool` with declared inputs and outputs, so the PLA selects by contract and does not care whether it is code or an LLM.
- **Provenance classes:** `Program`, `Issue`, `Task`, `Tool`, `ToolRun`. Each `ToolRun` records the tool, inputs, outputs, timestamps, attempt number and whether it was agentic, PROV-style, for every call.
- **Human approval gate:** the PLA stops before `render_quote` output is sent anywhere and waits for a person to approve or reject. Agents propose; people approve.
- **Durability and retries from the start:** run state is persisted after every step; failed tool calls retry with exponential backoff; each failure is logged as an `Issue`; a run resumes where it stopped after a refresh or failure.
- **Conversational layer (next):** a thin conversational agent can sit on top of the Python PLA to make it "conversant" without changing the PLA itself.

### Repo split

Agents live in a **separate repo**, `supergus/rfq-agents`, the pattern for enterprise-scale production. The ontology repo is the shared vocabulary; the agent repo consumes it as a **versioned dependency**, so vocabulary changes and agent changes are reviewed and released independently.

### Hosting

- **Cloudflare.** Public demo at **pla.chriscouch.net**, served by Cloudflare Pages from `supergus/rfq-demo` (output directory `public`).
- **"Secret?" gate:** a shared-password prompt in front of the whole site, implemented as Pages Functions middleware (`functions/_middleware.js`). The secret lives in Cloudflare encrypted secrets; success sets a signed HttpOnly cookie; every attempt is logged with IP, timestamp and result in D1; failed attempts are rate-limited; pages are `noindex`.
- **PLA Worker `rfq-pla`** (in `worker/`): calls Workers AI Llama 3.3 70B through a binding (no API key), keeps run state in a Durable Object / Workflow with retries, enforces per-IP and global rate limits, and holds a hard **$20/day** budget in code (it answers "demo is resting" when spent), backed by a Cloudflare billing alert. Sample RFQs only, no customer data.

## 7. The demo console

The demo is a **live management portal into a PLA run**, laid out like an operations dashboard.

- **Start:** the page opens on an **"Upload RFQ package"** button. Nothing is uploaded; clicking it starts a scripted PLA run on a sample package (no public file-upload risk).
- **Header:** program (e.g. RFQ-1002), current stage, overall status badge, elapsed time.
- **Pipeline strip:** intake, validate, match, cost, approve, send, each pending / running / done / failed / retrying.
- **Issues and tasks panel:** open issues with owner (PLA, tool or human) and resolve buttons for human ones, e.g. RFQ-1002's missing Incoterm and material spec; fix them and watch SHACL pass.
- **Tool-run log:** every call with a deterministic or AI badge, inputs, outputs, duration, attempt and retries, expandable to raw JSON.
- **Live graph:** the RFQ graph grows as facts are added; the similarity match appears as a node with score and method.
- **Quote build-up:** material, conversion, overhead and margin per quantity break (100 / 1,000 / 10,000), with click-through provenance to the rate row, BOM line and tool run behind each number.
- **Controls:** pause, resume, retry a step, simulate a failure (watch backoff and an Issue being logged), approve or reject at the human gate.
- **Run history:** past runs, so it reads as a managed program, not a one-off.

## 8. Build status

| Item | Status |
|---|---|
| `supergus/rfq-ontology` public, CI `tests`, protected `main` | Live |
| This write-up | Live |
| PLA classes (`Program`, `Issue`, `Task`, `Tool`, `ToolRun`) in the ontology | In progress |
| `supergus/rfq-agents` repo (PLA loop, tools, retries) | In progress |
| `rfq-demo` v1 console, Pages deploy, pla.chriscouch.net, "Secret?" gate | In progress |
| `rfq-pla` Worker (Workers AI, rate limits, $20/day cap) | In progress |
| pyLODE docs on GitHub Pages; Protégé check | Not started |

## 9. CI/CD and who manages what

### Repos

| Repo | Visibility | Contents | CI |
|---|---|---|---|
| `supergus/rfq-ontology` | Public | Ontology, data, SHACL shapes, SPARQL queries, quote calculator | GitHub Actions workflow `tests`: pytest, pySHACL, SPARQL competency queries, ROBOT + HermiT reasoner and OWL 2 DL profile check |
| `supergus/rfq-demo` | Public | Static console in `public/`, `functions/` gate, `worker/` (rfq-pla) | Cloudflare Pages build; Worker deploy Action |
| `supergus/rfq-agents` (planned name) | — | PLA orchestrator and deterministic/agentic tools; depends on a versioned rfq-ontology release | `tests` workflow, same pattern |

### Pipeline

1. Branch → PR → CI workflow `tests` runs.
2. The reviewer posts the manual commit status **`Grok Bot QC` = success** only after `tests` passes.
3. Merge.

`main` is protected on each repo: PR required, required status `Grok Bot QC`, 0 approvals, enforced for admins, no force pushes or deletions. Cloudflare Pages builds a **preview URL on every PR** and goes live on merge to `main`. The `rfq-pla` Worker is deployed by a GitHub Action on merge, like djnigiri-api.

### Who manages what

| Owner | Responsibilities |
|---|---|
| **T800 (AI Officer)** | `rfq-ontology` repo; agent and tool code (`rfq-agents`); demo front-end content in `public/`; this write-up; review, QC and merge of content PRs |
| **Cloud Manager (IT Services)** | Cloudflare side: Pages project and deploy config; pla.chriscouch.net DNS and custom domain; `functions/_middleware.js` gate and its secrets (`PLA_SECRET`, `COOKIE_KEY`, entered by Chris through a private secret form, never in the repo or chat); D1 access log; Worker deploy workflow; rate limits and billing alert; QCs and merges its own deploy/config PRs |
| **Chris** | Approvals; the shared secret value; the daily cap ($20); Cloudflare API token updates (the current token cannot yet create rate-limit rules) |

Neither bot edits the other's files: T800 puts nothing in `functions/`, and Cloud Manager leaves `public/` content and the ontology alone.
