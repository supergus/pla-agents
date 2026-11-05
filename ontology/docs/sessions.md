# Tutorial sessions

> As of Nov 5, 2026 these sessions run against the ontology tree under `pla-agents/ontology/` (the former `rfq-ontology` repo). CI is the repo-root workflow **tests**.

Each session ends with a PR that passes `tests` and gets the `Grok Bot QC` status.

1. **Scope and competency questions.** Walk the RFQ-to-quote process. Write the questions
   the model must answer (docs/competency-questions.md) before writing any OWL. Decide what
   is out of scope (docs/simplifications.md).
2. **RFQ package and completeness.** `rfq-package.ttl`: RFQ, lines, quantity breaks,
   commercial and delivery terms, Incoterms as individuals, technical requirements.
   Write `CompleteRFQ` in OWL, see the reasoner classify RFQ-1001, then hit the open-world
   gotcha with RFQ-1002 and fix it with SHACL.
3. **BOM and make/buy.** `rfq-bom.ttl`: products, categories, EBOM, BOM lines with scrap,
   make/buy as a decision (and why not subclasses). EBOM vs MBOM.
4. **Library, routings, rate tables.** `rfq-library.ttl` and the rate part of
   `rfq-costing.ttl`: library entries, similarity matches as recorded facts, routings with
   setup/run, work-center rates with effective dates and sources.
5. **Cost chain and provenance.** Quotes, price breaks, estimates, PROV-O links. Implement
   the formulas in `scripts/quote.py`; discuss order of operations, markup vs margin,
   overhead simplification; trace a price back to the rate rows that produced it.
6. **Sample data, SPARQL, SHACL, CI, docs.** Load the worked example, run the competency
   queries, wire ROBOT/HermiT, pySHACL and pytest into GitHub Actions, protect `main`,
   and (roadmap) publish docs to GitHub Pages.
