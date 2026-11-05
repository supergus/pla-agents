# The PLA model (`ontology/rfq-pla.ttl`)

The Program Lifecycle Agent (PLA) runs a quote program end to end. This module is the vocabulary it reads and writes, so its state, issues and every tool call are facts in the same graph as the RFQ and the quote.

## Classes

| Class | Meaning |
|---|---|
| `Program` | One quote program, tied to an RFQ by `programForRFQ`, with a `programStage` (intake, validate, match, cost, approve, send) |
| `Issue` (a `prov:Entity`) | A problem with `issueSeverity` (blocker, warning, info), `issueStatus` (open, resolved), `raisedBy` (a tool run) and `assignedTo` |
| `Task` | A unit of work with `taskStatus`, `assignedTo`, and the tool it `usesTool` |
| `Tool` | A callable capability with `toolContractInput` / `toolContractOutput`, `isAgentic` and `requiresApproval` |
| `DeterministicTool`, `AgenticTool` | Defined classes: a `Tool` with `isAgentic false` / `true`. HermiT classifies each tool; the data only says `rfq:Tool` |
| `ToolRun` (a `prov:Activity`) | One attempt: `toolRunOf`, `forTask`, `runInProgram`, `attemptNumber`, `runStatus`, `prov:startedAtTime`, `prov:endedAtTime`, `toolRunInput` (sub-property of `prov:used`), `toolRunOutput` (inverse of `prov:wasGeneratedBy`), and `retryOf` the failed attempt |
| `ApprovalGate` | The human checkpoint: `gateForQuote`, `gateDecision` (pending, approved, rejected), `approvedBy` or `rejectedBy`, `decidedAtTime` |
| `HumanFix` (a `prov:Entity`) | A correction a person applied to the RFQ data: the program `hasFix` it, `appliedBy`, `prov:generatedAtTime` |

`Quote` gains `quoteStatus` (draft, awaiting approval, sent) and `quoteSummary` (the `explain_quote` text).

`ToolRun` also carries the audit terms the PLA writes: `idempotencyKey` (tool + inputs + RFQ version, so a replayed step is not applied twice), `outputSummary` (truncated JSON of a successful result) and `runError` (message of a failed attempt).

## Part matches: `SimilarityMatch` at two levels

The PLA's `match_library_part` tool records its result as an ordinary `rfq:SimilarityMatch` (library module), so estimator matches and agent matches are queried the same way:

| Level | Subject | Target | Written by |
|---|---|---|---|
| BOM line | `forBOMLine` → `BOMLine` | `matchedEntry` → `ComponentLibraryEntry` | estimator or a matching tool (RFQ-1001) |
| RFQ line | `forRFQLine` → `RFQLine` (inverse `hasLineMatch`) | `matchedProduct` → `Product` | PLA `match_library_part` (RFQ-1002) |

Both carry `similarityScore`, `similarityMethod`, `confidence` and optional `manualOverride`. SHACL (`shapes/rfq-completeness.ttl`) requires exactly one of `forBOMLine` / `forRFQLine` and a target (entry, product, or manual override with a unit cost); `shapes/pla-shapes.ttl` additionally requires a score and product on RFQ-line matches. CQ12 lists them.

## Example run: `data/pla-run-1002.ttl`

- Eight tools: `validate_rfq`, `explode_bom`, `cost_quote`, `run_competency_queries`, `render_quote` (deterministic; `render_quote` requires approval) and `parse_rfq_document`, `match_library_part`, `explain_quote` (agentic).
- Program `PRG-1002` for RFQ-1002, stopped at the approve stage.
- Five tool runs. `match_library_part` attempt 1 failed (timeout, logged as a resolved warning issue) and attempt 2 retried it and succeeded, writing `SM-1002-L1` (RFQ-1002-L1 → BRK-100, score 0.91; invented example values). The failed attempt carries a `runError`.
- `validate_rfq` raised two open blocker issues: missing Incoterm and missing material spec.
- Draft quote `Q-1002-A` waits at `GATE-1002` (pending). It has no price breaks; it only exercises the gate.

## Checks

- **SHACL** (`shapes/pla-shapes.ttl`): every tool run has exactly one tool, a valid status, an attempt number of at least 1 and a program; a retry has attempt 2 or more; every issue has a valid status and `raisedBy`; a quote with status "sent" must have an approved gate (SPARQL constraint); `runError` only on failed runs; a human fix has `appliedBy` and a time; `approvedBy` / `rejectedBy` must match the gate decision; an RFQ-line match names a product and a score.
- **Competency questions**: CQ9 open issues, CQ10 tool runs by kind, CQ11 unapproved quotes, CQ12 RFQ-line matches (see [competency-questions.md](competency-questions.md)).
- **Reasoner**: tools are classified as agentic or deterministic, and tool runs are `prov:Activity`.
- **Tests**: `tests/test_pla.py`, plus new cases in `test_queries.py` and `test_reasoner.py`.

The PLA loop itself (Python orchestrator, retries, Worker) lives in the root of `supergus/pla-agents`; this `ontology/` tree only holds the shared vocabulary.
