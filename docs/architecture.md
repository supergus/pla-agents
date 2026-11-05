# Architecture

## The loop

```mermaid
flowchart TD
    start([start: --rfq]) --> plan{Planner.next}
    plan -- call tool --> exec[execute with RetryPolicy]
    exec --> rec[record ToolRun<br/>running -> succeeded / failed]
    rec -- retryable and attempts left --> backoff[backoff + jitter] --> exec
    rec -- exhausted or fatal --> blk[blocker Issue<br/>status = failed] --> stop
    rec -- succeeded --> gate1[schema + SHACL gate<br/>for agentic output] --> write[write triples,<br/>raise/resolve Issues]
    write --> ckpt[(checkpoint:<br/>state JSON + graph TTL<br/>one SQLite transaction)] --> plan
    plan -- open blocker issues --> wh([waiting_human]) --> fix[--fix / --resolve] --> plan
    plan -- quote explained --> og[open ApprovalGate<br/>quote 'awaiting approval'] --> wa([waiting_approval])
    wa -- --approve --> render[render_quote] --> done([done: quote 'sent'])
    wa -- --reject --> rej([rejected])
```

## Program state

Everything the PLA knows is in two artifacts saved together after every step:

| Artifact | Contents |
|---|---|
| Program graph (Turtle) | `rfq:Program`, its `Task`s (intake, validate, match, cost, send), `Issue`s, `ToolRun`s (tool, task, program, attempt, status, `prov:startedAtTime`/`endedAtTime`, `toolRunInput`/`toolRunOutput`, `retryOf`, `idempotencyKey`, `outputSummary`/`runError`), the `ApprovalGate` (`approvedBy`/`rejectedBy`), `HumanFix`es, and the RFQ and quote facts the tools wrote |
| State JSON | status, stage, RFQ data version, idempotency ledger (`done`), attempt counters, the in-flight step, issue index, event log |

The graph is checked against the ontology's `shapes/pla-shapes.ttl` after every successful step (every run has
one tool, a valid status, an attempt ≥ 1, a program; a retry has attempt ≥ 2; a quote is "sent" only with an
approved gate). Read-only context (ontology modules, reference rates, the product catalog, tool contracts) is
loaded from the pinned ontology and is not copied into the run.

## Tools and contracts

| Tool | Kind | Stage | Requires → produces |
|---|---|---|---|
| `parse_rfq_document` | agentic | intake | rfq_document → rfq_graph |
| `validate_rfq` | deterministic | validate | rfq_graph → validation_report |
| `run_competency_queries` | deterministic | validate | program_graph → query_results |
| `match_library_part` | agentic | match | validation_report → product_match |
| `explode_bom` | deterministic | match | product_match → bom |
| `cost_quote` | deterministic | cost | bom → quote |
| `explain_quote` | agentic | cost | quote → quote_summary |
| `render_quote` | deterministic, **requires approval** | send | approved_quote → quote_document |

Contracts are data in `pla_agents/contracts/tools.ttl`. Their `rfq:` triples (IRIs, labels, `isAgentic`,
`requiresApproval`, contract input/output text) must equal the Tool individuals in the ontology's
`data/pla-run-1002.ttl`; `tests/test_contracts.py` also checks the code registry has exactly these tools.

## Planners

`DeterministicPlanner` picks the first eligible tool (contract order) whose required artifact exists and whose step
is not yet in the idempotency ledger. With open blocker issues only re-check tools run (`validate_rfq`,
`match_library_part`, `explode_bom`); otherwise the PLA waits for a person. `render_quote` is never eligible
before the gate is approved. `LLMPlanner` asks a model to choose **among the eligible tools only** and falls back to
the rules on any error, so a model can reorder work but cannot skip a gate. A conversational agent can later sit on
top of the CLI/API without changing this loop.

## Durability and retries

- **Checkpoints:** before a tool call (`start tool#n`, with the step recorded as in-flight) and after it
  (`done tool` / `failed tool#n`), each a single SQLite transaction (WAL, `synchronous=FULL`).
- **Crash recovery:** on resume, an in-flight step is recorded as a failed attempt ("interrupted") with a warning
  Issue, and the next attempt is a new ToolRun with `retryOf` pointing at it. Completed steps are never repeated.
- **Idempotency:** each step key is the tool plus the RFQ data version (a human fix bumps the version so exactly
  the dependent steps re-run). Each ToolRun also stores `run:step:hash(inputs)` as its idempotency key, ready to pass to
  external side-effecting calls.
- **Retries:** `RetryPolicy` (default 3 attempts, exponential backoff 0.5 s → 8 s cap, full jitter).
  Retryable: timeouts, connection errors, HTTP 429/5xx, model output that fails schema/SHACL. Fatal: bad input,
  contract violations, unexpected exceptions. Each failed attempt raises a warning Issue that is resolved when a
  retry succeeds; exhaustion or a fatal error raises a blocker Issue for `human:operator` and marks the run
  `failed` (resume with `--retry`).
- **Failure injection:** `--inject-failure TOOL[:N]` (N transient failures), `TOOL:fatal`, `TOOL:crash`
  (crash right after the step is checkpointed). Tests also use `crash_before` (crash mid-step).

## Agentic output gates

1. JSON schema (`pla_agents/schema.py`), e.g. Incoterm must be one of EXW/FCA/FOB/CIF/DAP/DDP, quantities ≥ 1.
2. Domain checks: the matched product must be one of the candidates; `explain_quote` may only use numbers that
   appear in the computed quote.
3. SHACL (`pla_agents/shapes/agent-output-shapes.ttl`) on context + program + proposal.
4. Confidence: parsed fields below 0.7 are not written and become Issues; a part match scoring below 0.8 is not
   written and becomes a blocker Issue for the estimator.

Part matching is recorded as an `rfq:SimilarityMatch` for the RFQ line (`forRFQLine`, `matchedProduct`,
`similarityScore`, `similarityMethod`, `confidence`, `manualOverride false`), the same class the ontology uses for
BOM-line matches. Every term the PLA writes is declared in the in-repo ontology (`ontology/`); the `pla:` namespace holds only
planner metadata in `contracts/tools.ttl` (stage, order, requires, produces).

## Not yet built

- The Cloudflare Worker `rfq-pla` (Workers AI binding, Durable Object/Workflow run state, $20/day budget) that will
  host this loop for the live demo; this repo's `WorkersAIClient` calls the same model over the REST API.
- PDF intake (text/email only today).
