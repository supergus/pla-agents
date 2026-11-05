## What changed

<!-- One or two sentences. Area: pla / planner / store / retry / llm / tools / contracts / ontology / docs -->

## Why

<!-- The program-lifecycle behaviour or issue this serves. -->

## Checklist

- [ ] `python -m pytest` passes locally (ontology fetched at the pinned commit)
- [ ] New or changed tools: contract in `contracts/tools.ttl` matches the ontology's `rfq:Tool` individual
- [ ] Agentic output is schema- and SHACL-validated; low confidence becomes an Issue
- [ ] If costing changed: worked-example numbers still 60.86 / 58.01 / 57.72
- [ ] No secrets or tokens committed
- [ ] `tests` workflow green before the **Grok Bot QC** status is posted
