# pla-agents

The **PLA (Program Lifecycle Agent)** and its tools for the RFQ-to-quote process.

The PLA runs one quote program end to end: intake → validate → match → cost → **human approval** → send.
It keeps the program's state (stage, tasks, issues, every tool run) as an RDF graph in the vocabulary of
the in-repo [ontology](ontology/) (`rfq-pla` module), picks the next tool by its
declared contract, retries transient failures with backoff, and checkpoints after every step so a crash resumes
where it stopped.

The shared vocabulary (OWL ontology, SHACL shapes, SPARQL competency queries, cost calculator) lives in
[`ontology/`](ontology/), folded in from the former `supergus/rfq-ontology` repo with its history (see
[Ontology](#ontology)).

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest                          # 30 tests, offline (canned LLM)

# RFQ-1002 is incomplete: the PLA stops with two blocker issues
python -m pla_agents run --rfq data/rfq-1002-incomplete.ttl --run-id demo --quote-date 2026-10-27 \
       --inject-failure match_library_part:1
# the estimator supplies the missing Incoterm and material spec; the PLA re-validates, matches
# (the injected timeout is retried), costs, and stops at the approval gate
python -m pla_agents run --resume demo --fix data/fixes/rfq-1002-fix.ttl
# a person approves; only now does render_quote run (sending is simulated: a Markdown file)
python -m pla_agents run --resume demo --approve --by chris
python -m pla_agents status demo
```

The BRK-100 worked example (`data/rfq-1001.ttl` in the ontology) prices at **$60.86 / $58.01 / $57.72** per unit and
**$8,016.00 / $60,660.00 / $587,050.00** total for 100 / 1,000 / 10,000, identical to the ontology's
`docs/worked-example.md`, because `cost_quote` calls the ontology's own `ontology/scripts/quote.py`.

### CLI

```
python -m pla_agents run --rfq PATH [--run-id ID] [--quote-date YYYY-MM-DD] [--inject-failure TOOL[:N|:fatal|:crash]] [--llm canned|workers-ai]
python -m pla_agents run --resume RUN_ID [--fix FILE.ttl] [--resolve ISS-ID] [--retry] [--approve|--reject --by NAME]
python -m pla_agents status RUN_ID [--json]
python -m pla_agents list
```

`--rfq` takes Turtle (structured intake) or text such as an RFQ email (`data/rfq-1003-email.txt`, parsed by the
LLM). Paths resolve against the cwd, then `ontology/`, then this repo. Runs are stored in
`$PLA_AGENTS_DB` (default `runs/pla.sqlite`). Exit codes: 0 ok/waiting, 1 usage error, 2 failed, 3 injected crash.

## Layout

```
pla_agents/
  pla.py            PLA loop: state graph, ToolRuns, Issues, approval gate, resume
  planner.py        Planner interface; DeterministicPlanner; LLMPlanner (chooses only among eligible tools)
  store.py          SQLite run store (WAL, one transaction per checkpoint)
  retry.py          backoff + jitter, retryable vs fatal, idempotency keys, failure injection
  llm.py            LLMClient interface; CannedLLMClient; WorkersAIClient (Llama 3.3 70B)
  schema.py         small JSON-schema validator for LLM output
  contracts.py      loads contracts/tools.ttl
  contracts/tools.ttl   tool contracts as data (match the ontology's Tool individuals)
  shapes/agent-output-shapes.ttl   SHACL gate for agentic proposals
  tools/            deterministic.py (validate_rfq, explode_bom, cost_quote, run_competency_queries,
                    render_quote) and agentic.py (parse_rfq_document, match_library_part, explain_quote)
data/               sample RFQ email and the RFQ-1002 human fix
ontology/           OWL modules, data, SHACL shapes, SPARQL queries, quote.py, ontology tests and docs
tests/              pytest
docs/architecture.md
```

## Ontology

`ontology/` is the ontology tree (formerly `supergus/rfq-ontology`, now archived). The PLA loads it from there; set
`PLA_ONTOLOGY_DIR` to use another checkout. CI (workflow **tests**) runs the ontology checks first (Turtle parsing,
OWL 2 DL profile, HermiT reasoning, ROBOT report, pySHACL, SPARQL competency queries, worked-example numbers) and then
the agents' tests, so a vocabulary change and the agent code that depends on it land in one reviewed PR.
See [ontology/README.md](ontology/README.md) and the project write-up [ontology/docs/PROJECT.md](ontology/docs/PROJECT.md).
OWL IRIs keep their historical `https://supergus.github.io/rfq-ontology/…` namespace.

## LLM providers

Agentic tools call an `LLMClient`. Default is `canned` (offline, deterministic: tests, CI and demos).
`--llm workers-ai` uses Cloudflare Workers AI, model `@cf/meta/llama-3.3-70b-instruct-fp8-fast`
(override with `PLA_AGENTS_MODEL`), with credentials **only** from `CLOUDFLARE_ACCOUNT_ID` and
`CLOUDFLARE_API_TOKEN` in the environment. Never commit a token. Model output is untrusted: it is checked
against a JSON schema and SHACL before it is written, and low-confidence fields become Issues.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the PR process and [docs/architecture.md](docs/architecture.md) for the design.

## Related repositories
- This repo (`pla-agents`) — PLA orchestrator and tools, plus the tutorial OWL ontology in [`ontology/`](ontology/).
- [supergus/pla-demo](https://github.com/supergus/pla-demo) — live PLA management console / quote demo at https://pla.chriscouch.net.
- [supergus/rfq-ontology](https://github.com/supergus/rfq-ontology) — archived; its contents now live in `ontology/` here.
- Leaf Tender is a separate ontology management project hosted at https://leaftender.chriscouch.net (not part of the PLA demo).
