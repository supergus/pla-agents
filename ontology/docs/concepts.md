# Concepts: the model, module by module

| Module | File | Main terms |
|---|---|---|
| core | `rfq-core.ttl` | `Customer`, `UnitOfMeasure` (+ each, hour, USD), `revision`, `supersedes` (transitive) / `isSupersededBy`, `identifier` |
| provenance | `rfq-provenance.ttl` | reused W3C PROV-O `prov:Entity`, `prov:Activity`, `prov:wasDerivedFrom`, `prov:wasGeneratedBy`, `prov:used`; `CostRollup` |
| package | `rfq-package.ttl` | `RFQPackage`, `RFQLine`, `QuantityBreak`, `CommercialTerms`, `DeliveryTerms`, `Incoterm` (EXW, FCA, FOB, CIF, DAP, DDP with `sellerPaysFreight`, `riskTransferPoint`), `TechnicalRequirement` > `Drawing`, `MaterialSpec`, `FinishSpec`; defined class `CompleteRFQ` |
| bom | `rfq-bom.ttl` | `Product`, `ProductCategory`, `EngineeringBOM`, `BOMLine` (`quantityPer`, `scrapRate`, `sourcingDecision`), `Component`, `SourcingDecision` = {`Make`, `Buy`} |
| library | `rfq-library.ttl` | `ComponentLibraryEntry` (`libraryUnitCost`, `costDate`, `costBasisQuantity`), `SimilarityMatch` (`similarityScore`, `similarityMethod`, `confidence`, `manualOverride`, `overrideUnitCost`), `Routing`, `ProcessStep` (`setupHours`, `runHours`, `stepSequence`), `WorkCenter` |
| costing | `rfq-costing.ttl` | `RateAssumption` > `WorkCenterRate`, `OverheadRate`, `SGARate`, `MarginTarget`, `FreightRate` (all with `effectiveDate`, `rateSource`); `Quote` (`quoteDate`, `validUntil`), `QuotePriceBreak`, `CostEstimate` > `MaterialCost`, `ConversionCost`, `COGS`, `LoadedCost`, `NRECost`, `FreightCost` |

## Key design decisions

- **Similarity is a recorded fact, not a computation.** A `SimilarityMatch` links a BOM
  line to a library entry with a score, the method that produced it, a confidence flag and
  an optional manual override. The library entry carries the date and quantity its cost was
  based on, so a reviewer can judge whether the old cost still applies.
- **Every estimate belongs to an (RFQ line, quantity break).** Unit cost falls with volume
  because setup is spread over a bigger lot.
- **Make/buy is a decision on the BOM line**, not a permanent subclass of `Component`. A
  bought part can later be made; the same component can be make in one product and buy in
  another.
- **Rates are versioned rows** with effective date and source. A newer row `supersedes`
  the old one; estimates link to the exact row they used via `prov:wasDerivedFrom`, so
  "which quotes used a stale rate?" is a query (CQ6).
- **Incoterms do real work**: `sellerPaysFreight` decides whether a freight line appears.
- **Quotes and RFQs have revisions** and a validity date; `supersedes` is transitive.
- **Arithmetic is in Python** (`scripts/quote.py`), not OWL. OWL is for classification and
  consistency; it has no practical arithmetic.

## OWL features used (and why)

- Class hierarchy and `rdfs:domain`/`rdfs:range` on every property.
- `owl:FunctionalProperty` where the business allows one value (one Incoterm per delivery
  terms, one sourcing decision per BOM line).
- `owl:inverseOf` (`hasLine`/`lineOf`, `supersedes`/`isSupersededBy`, `forBOMLine`/`hasSimilarityMatch`).
- `owl:TransitiveProperty` on `supersedes` only (revision chains are genuinely transitive).
- Disjointness: drawings vs material vs finish specs; the rate-table classes; the cost-estimate classes; PROV entities vs activities.
- An enumerated class (`SourcingDecision` = `oneOf(Make, Buy)`) with `owl:AllDifferent`.
- A defined class `CompleteRFQ` (`owl:equivalentClass` intersection of existential restrictions).

## The open-world gotcha

OWL assumes that a missing fact is **unknown**, not false. If RFQ-1002 has no Incoterm,
the reasoner does not conclude "RFQ-1002 is incomplete"; it concludes nothing. The reasoner
can *prove* RFQ-1001 is a `CompleteRFQ` (CI checks this), but it will never flag RFQ-1002.

To report what is missing we need a **closed-world** check: SHACL
(`shapes/rfq-completeness.ttl`) says "an RFQPackage MUST have at least one Incoterm" and
reports exactly which element is absent. CQ1 does the same in SPARQL with `FILTER NOT EXISTS`.
Rule of thumb: OWL for meaning and inference, SHACL for data validation.

## EBOM, not MBOM

We quote from the **engineering BOM** derived from the customer's drawing. The
manufacturing BOM (phantom assemblies, fasteners added by manufacturing, consumables,
packaging) is deliberately out of scope.

## Standard cost vs quote cost

A quote uses the expected cost at current prices and rates effective on the quote date.
That can differ from the ERP standard cost used for inventory valuation. This ontology
models quote cost only.
