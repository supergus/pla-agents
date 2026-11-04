# Competency questions

Each question is a SPARQL file in `queries/` and an assertion in `tests/test_queries.py`.

| # | Question | Query | Expected answer on the sample data |
|---|---|---|---|
| CQ1 | Does this RFQ have everything we need to quote? What is missing? | `cq1-rfq-completeness.rq` | RFQ-1002: Incoterm; material or finish spec. RFQ-1001: nothing missing |
| CQ2 | Which BOM lines are make vs buy? | `cq2-make-vs-buy.rq` | BL-1, BL-2 make; BL-3, BL-4, BL-5 buy |
| CQ3 | Which library entry estimated each line, how similar, by what method? | `cq3-similarity-used.rq` | e.g. BL-1 → PLT-210, 0.92, attribute-weighted v1; BL-5 manual override |
| CQ4 | What are unit COGS and price at each quantity break? | `cq4-cogs-by-break.rq` | 60.86 / 58.01 / 57.72 per unit |
| CQ5 | Which routing steps drive conversion cost? | `cq5-conversion-drivers.rq` | Weld op 30 on the base plate, 11.25 per bracket |
| CQ6 | Which quotes used an out-of-date rate? | `cq6-stale-rates.rq` | Q-1001 rev A used WCR-WELD-2025 |
| CQ7 | Which BOM lines need manual estimating review? | `cq7-manual-review.rq` | BL-5 label (no library match) |
| CQ8 | Does the quote need a freight line? | `cq8-freight-by-incoterm.rq` | RFQ-1001, DAP, seller pays freight |

CQ4 and CQ6 run over the computed results in `build/quote-results.ttl` (written by `scripts/quote.py`).
