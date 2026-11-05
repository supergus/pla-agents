# rfq-agents

The **PLA (Program Lifecycle Agent)** and its tools for the RFQ-to-quote process.

The PLA runs one quote program end to end: intake → validate → match → cost → **human approval** → send.
It keeps the program's state (stage, tasks, issues, every tool run) as an RDF graph in the vocabulary of
[supergus/rfq-ontology](https://github.com/supergus/rfq-ontology) (`rfq-pla` module), picks the next tool by its
declared contract, retries transient failures with backoff, and checkpoints after every step so a crash resumes
where it stopped.

This repo is separate from the ontology on purpose (enterprise-scale split): the ontology is the shared vocabulary
and is consumed here as a **pinned, versioned dependency** (see [Ontology dependency](#ontology-dependency)).

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python scripts/fetch_ontology.py          # checks out the commit pinned in ontology.lock into vendor/
python -m pytest                          # 30 tests, offline (canned LLM)

# RFQ-1002 is incomplete: the PLA stops with two blocker issues
python -m rfq_agents run --rfq data/rfq-1002-incomplete.ttl --run-id demo --quote-date 2026-10-27 \
       --inject-failure match_library_part:1
# the estimator supplies the missing Incoterm and material spec; the PLA re-validates, matches
# (the injected timeout is retried), costs, and stops at the approval gate
python -m rfq_agents run --resume demo --fix data/fixes/rfq-1002-fix.ttl
# a person approves; only now does render_quote run (sending is simulated: a Markdown file)
python -m rfq_agents run --resume demo --approve --by chris
python -m rfq_agents status demo
```

The BRK-100 worked example (`data/rfq-1001.ttl` in the ontology) prices at **$60.86 / $58.01 / $57.72** per unit and
**$8,016.00 / $60,660.00 / $587,050.00** total for 100 / 1,000 / 10,000, identical to the ontology's
`docs/worked-example.md`, because `cost_quote` calls the ontology's own `scripts/quote.py` at the pinned commit.

### CLI

```
python -m rfq_agents run --rfq PATH [--run-id ID] [--quote-date YYYY-MM-DD] [--inject-failure TOOL[:N|:fatal|:crash]] [--llm canned|workers-ai]
python -m rfq_agents run --resume RUN_ID [--fix FILE.ttl] [--resolve ISS-ID] [--retry] [--approve|--reject --by NAME]
python -m rfq_agents status RUN_ID [--json]
python -m rfq_agents list
```

`--rfq` takes Turtle (structured intake) or text such as an RFQ email (`data/rfq-1003-email.txt`, parsed by the
LLM). Paths resolve against the cwd, then the pinned ontology checkout, then this repo. Runs are stored in
`$RFQ_AGENTS_DB` (default `runs/pla.sqlite`). Exit codes: 0 ok/waiting, 1 usage error, 2 failed, 3 injected crash.

## Layout

```
rfq_agents/
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
scripts/fetch_ontology.py
tests/              pytest
docs/architecture.md
```

## Ontology dependency

`ontology.lock` pins `supergus/rfq-ontology` to one commit. `scripts/fetch_ontology.py` fetches exactly that commit
into `vendor/rfq-ontology` (git-ignored, idempotent); CI does the same. Set `RFQ_ONTOLOGY_DIR` to point at a local
checkout while developing both repos together.

**Upgrading** is a normal PR here that changes only the `commit` line; CI then proves the agents still work against the
new vocabulary, shapes, queries and costing formulas. Why a lock file and not a submodule: one plain text line to
review, no `--recursive` clone footguns, and the same fetch path for laptops, CI and a future container build.
When the ontology starts tagging releases (e.g. `v0.2.0`), pin the tag's commit and note the tag in the comment.

## LLM providers

Agentic tools call an `LLMClient`. Default is `canned` (offline, deterministic: tests, CI and demos).
`--llm workers-ai` uses Cloudflare Workers AI, model `@cf/meta/llama-3.3-70b-instruct-fp8-fast`
(override with `RFQ_AGENTS_MODEL`), with credentials **only** from `CLOUDFLARE_ACCOUNT_ID` and
`CLOUDFLARE_API_TOKEN` in the environment. Never commit a token. Model output is untrusted: it is checked
against a JSON schema and SHACL before it is written, and low-confidence fields become Issues.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the PR process and [docs/architecture.md](docs/architecture.md) for the design.

## Related repositories
- [supergus/rfq-ontology](https://github.com/supergus/rfq-ontology) — tutorial OWL ontology for the RFQ-to-quote process; pinned here via `ontology.lock`.
- [supergus/rfq-demo](https://github.com/supergus/rfq-demo) — live PLA management console / quote demo at https://pla.chriscouch.net.
- This repo (`rfq-agents`) — PLA orchestrator and tools.
- Leaf Tender is a separate ontology management project hosted at https://leaftender.chriscouch.net (not part of this RFQ demo trio).
