# Repo guide: pla-agents

A map of this repository for auditors (CS IT) and new contributors. Last checked against `main` on 2026-11-09.

> **Demo status.** This is an **early proof-of-concept** of the agentic RFQ-to-quote workflow that preceded the production **CS Agent Orchestration Suite**. It may be retired once the suite is in production. **Inference (flagged):** the PLA orchestrator / tool-contract idea here roughly became **Agent Orchard** (orchestration) and **Agent Buffet** (quote-instance runs with tools); the tutorial OWL work under `ontology/` informed (and was partly superseded by) **Leaf Tender**'s domain graphs. This repo is **not** part of the production suite (`leaf-tender`, `agent-orchard`, `agent-buffet`, `suite-landing`).

**Names used here.** The **CS Agent Orchestration Suite** is the production software in those four repos. **CS** is the company the suite is being built for; **CS IT** is that company's IT organisation.

## Purpose

`pla-agents` is a **Python** Program Lifecycle Agent (PLA): it runs one quote program end to end (intake → validate → match → cost → human approval → send), keeps program state as an RDF graph, picks the next tool from declared contracts, retries transient failures, and checkpoints after every step.

The shared tutorial vocabulary (OWL, SHACL, SPARQL competency queries, cost calculator) lives in **`ontology/`**, folded in from the archived `supergus/rfq-ontology` repo (history preserved). The live browser console that demos a PLA run is [`pla-demo`](https://github.com/supergus/pla-demo) at https://pla.chriscouch.net.

This repo does **not** deploy a Cloudflare Worker or Pages site by itself. It is a library + CLI; optional live LLM calls use Cloudflare Workers AI credentials from the **environment only**.

## Where it runs

| Item | Value |
|---|---|
| Runtime | Local / CI Python 3.12 (pytest + CLI) |
| Hosted service | none in this repo |
| Default LLM | `canned` (offline, deterministic) |
| Optional LLM | Cloudflare Workers AI via env (`--llm workers-ai`) |
| Secrets (names only, env) | `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` (only when using Workers AI) |
| Optional env | `PLA_AGENTS_DB` (SQLite path, default `runs/pla.sqlite`), `PLA_ONTOLOGY_DIR`, `PLA_AGENTS_MODEL` |
| Data policy | Tutorial / sample RFQs only (`RFQ-1001`, `RFQ-1002`, fictional email). No customer workbooks |

## Folder tree

```
pla-agents/
├── .github/workflows/   CI (ontology checks then agent tests)
├── data/                sample RFQ email + human fix for RFQ-1002
├── docs/                architecture note
├── ontology/            full tutorial ontology tree (ex-rfq-ontology)
│   ├── data/            sample RFQs, reference library, sample PLA run
│   ├── docs/            concepts, formulas, worked example, roadmap, …
│   ├── ontology/        OWL Turtle modules
│   ├── queries/         CQ1–CQ12 SPARQL
│   ├── scripts/         quote.py, reason.sh, …
│   ├── shapes/          SHACL
│   └── tests/           ontology pytest suite
├── pla_agents/          Python package (PLA loop, tools, LLM, store)
└── tests/               agent pytest suite
```

## Every tracked file

### Root
| File | What it is for |
|---|---|
| `.github/pull_request_template.md` | PR checklist. |
| `.github/workflows/ci.yml` | Workflow **tests**: ontology ROBOT/HermiT/SHACL/SPARQL/quote checks, then agent pytest + CLI smoke run. |
| `.gitignore` | Ignores `.venv/`, `runs/`, build artifacts, etc. |
| `CONTRIBUTING.md` | Protected `main`, PR + Grok Bot QC process. |
| `README.md` | Quick start, CLI, layout, ontology note, LLM providers, related repos. |
| `REPO-GUIDE.md` | This file. |
| `pytest.ini` | Pytest config. |
| `requirements.txt` | `rdflib`, `pyshacl`, `pytest`. |

### data/
| File | What it is for |
|---|---|
| `data/fixes/rfq-1002-fix.ttl` | Human estimator fix (Incoterm + material) for the incomplete sample RFQ. |
| `data/rfq-1003-email.txt` | Fictional RFQ-as-email sample for the parse tool (`@northwind.example`). |

### docs/
| File | What it is for |
|---|---|
| `docs/architecture.md` | Design of the PLA loop, planner, tools, durability. |

### pla_agents/
| File | What it is for |
|---|---|
| `pla_agents/__init__.py` | Package marker. |
| `pla_agents/__main__.py` | CLI entry (`python -m pla_agents`). |
| `pla_agents/pla.py` | PLA loop: state graph, ToolRuns, Issues, approval gate, resume. |
| `pla_agents/planner.py` | Planner interface; deterministic and LLM planners. |
| `pla_agents/store.py` | SQLite run store (WAL, one transaction per checkpoint). |
| `pla_agents/retry.py` | Backoff, retryable vs fatal, idempotency, failure injection. |
| `pla_agents/llm.py` | LLM client interface; canned + Workers AI clients. |
| `pla_agents/schema.py` | Small JSON-schema check for LLM output. |
| `pla_agents/contracts.py` | Loads `contracts/tools.ttl`. |
| `pla_agents/contracts/tools.ttl` | Tool contracts as RDF (aligned with ontology Tool individuals). |
| `pla_agents/ontology.py` | Resolves and loads the `ontology/` tree. |
| `pla_agents/canned.py` | Deterministic canned LLM replies for demos / CI. |
| `pla_agents/shapes/agent-output-shapes.ttl` | SHACL gate for agentic proposals before they are written. |
| `pla_agents/tools/__init__.py` | Tool registry. |
| `pla_agents/tools/base.py` | Shared tool helpers. |
| `pla_agents/tools/deterministic.py` | `validate_rfq`, `explode_bom`, `cost_quote`, competency queries, `render_quote`. |
| `pla_agents/tools/agentic.py` | `parse_rfq_document`, `match_library_part`, `explain_quote`. |

### ontology/ (ex-rfq-ontology tree)
| File | What it is for |
|---|---|
| `ontology/README.md` | Ontology project readme (same content lineage as archived `rfq-ontology`). |
| `ontology/CONTRIBUTING.md` | Ontology contribution notes. |
| `ontology/.gitignore` | Ignores `build/`, jars, etc. |
| `ontology/requirements.txt` | Ontology Python deps (same stack). |
| `ontology/ontology/rfq.ttl` | Root OWL module. |
| `ontology/ontology/rfq-core.ttl` | Core vocabulary. |
| `ontology/ontology/rfq-provenance.ttl` | Provenance vocabulary. |
| `ontology/ontology/rfq-package.ttl` | RFQ package vocabulary. |
| `ontology/ontology/rfq-bom.ttl` | BOM / make-vs-buy. |
| `ontology/ontology/rfq-library.ttl` | Component library. |
| `ontology/ontology/rfq-costing.ttl` | Costing / rates. |
| `ontology/ontology/rfq-pla.ttl` | PLA / tools / issues vocabulary. |
| `ontology/ontology/catalog-v001.xml` | Protégé catalog (IRI → local file). |
| `ontology/data/reference.ttl` | Sample library, routings, work centers, rates. |
| `ontology/data/rfq-1001.ttl` | Complete sample RFQ (worked example). |
| `ontology/data/rfq-1002-incomplete.ttl` | Incomplete sample RFQ. |
| `ontology/data/pla-run-1002.ttl` | Sample PLA run graph. |
| `ontology/shapes/rfq-completeness.ttl` | SHACL completeness + data quality. |
| `ontology/shapes/pla-shapes.ttl` | SHACL for PLA state. |
| `ontology/queries/cq1-*.rq` … `cq12-*.rq` | Twelve competency SPARQL queries. |
| `ontology/scripts/quote.py` | Computes the worked-example quote from the graph. |
| `ontology/scripts/run_queries.py` | Prints every competency query answer. |
| `ontology/scripts/reason.sh` | ROBOT / HermiT OWL checks. |
| `ontology/scripts/rfqlib.py` | Shared helpers for scripts / tests. |
| `ontology/docs/*.md` | Concepts, formulas, worked example, competency questions, PLA model, sample LLM prompts, sessions, simplifications, roadmap, PROJECT. |
| `ontology/tests/*` | Ontology pytest: parse, SHACL, queries, quote numbers, reasoner, PLA vocabulary. |

### tests/ (agents)
| File | What it is for |
|---|---|
| `tests/conftest.py` | Shared fixtures. |
| `tests/test_agentic.py` | Agentic tools with canned LLM. |
| `tests/test_cli.py` | CLI parsing / exit codes. |
| `tests/test_contracts.py` | Tool contracts load and match. |
| `tests/test_durability.py` | Checkpoint / resume behaviour. |
| `tests/test_e2e.py` | End-to-end PLA run (incomplete → fix → approve). |
| `tests/test_retry.py` | Retry / failure injection. |
| `tests/test_vocabulary.py` | PLA vocabulary expectations. |
| `tests/test_worked_example.py` | Quote numbers match the ontology worked example. |

## Run tests

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest                          # agents (canned LLM)
# Full CI also runs ontology/ checks (needs Java + ROBOT) — see .github/workflows/ci.yml
```

No deploy from this repo. `main` is protected: PR + `tests` workflow + **Grok Bot QC** status.

## Where to look (audit topics)

| Topic | Look here |
|---|---|
| Orchestration / approval gate | `pla_agents/pla.py`, `docs/architecture.md` |
| Tool contracts | `pla_agents/contracts/tools.ttl`, `pla_agents/tools/` |
| LLM calls | `pla_agents/llm.py` — credentials only from env; default is canned |
| Ontology / SHACL / SPARQL | `ontology/` |
| Persistence | `pla_agents/store.py` (local SQLite under `runs/`, gitignored) |
| Secrets | README "LLM providers"; never commit tokens |
| Customer data | None; sample RFQs and fictional email only |

## Findings

| Kind | Where | Notes |
|---|---|---|
| Person first name in CLI example | `README.md` (`--by` example) | Pre-existing in the public readme; not a credential. Consider replacing with a role placeholder in a later cleanup. |
| No secret values or real customer PII found in tracked files | — | Sample email uses an `example` domain. |
