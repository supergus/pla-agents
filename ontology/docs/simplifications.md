# Named simplifications

This is a toy. Each simplification below is deliberate, and each says what a real system would do.

1. **Overhead as % of COGS.** A finance team would object that this pushes overhead onto
   material-heavy parts that use no extra factory resources. The usual alternative: put
   factory overhead *inside* the work-center rate (absorbed per labor/machine hour) and
   apply only SG&A as a % of cost. Our `WorkCenterRate` already has a burden component,
   so the switch is: drop `OverheadRate`, raise burden.
2. **Margin by product category only.** Real margin also depends on customer, competition,
   strategic value, volume and risk. A roadmap item adds an override with a recorded reason.
3. **Library cost taken at face value.** Real estimators adjust an old cost for quantity,
   material price movement and age. We record the cost date and basis quantity and a
   confidence flag so that adjustment can be added; we do not apply one.
4. **Lot size = quantity break.** Setup is spread over the whole quantity break as one lot.
5. **Make/buy is an input.** Recorded as a decision on the BOM line, not optimized.
6. **EBOM only.** No manufacturing BOM, phantom assemblies, consumables or packaging.
7. **One currency (USD), no taxes, no payment-terms cost of money, no contingency.**
8. **Similarity is computed outside the ontology** and recorded as a `SimilarityMatch`.
9. **PROV-O terms are declared locally** (same IRIs) instead of importing the full PROV-O
   ontology, to keep CI offline and the toy small.
10. **Dates are `xsd:dateTime`** at midnight, because `xsd:date` is not in the OWL 2
    datatype map and would take the ontology out of OWL 2 DL.

Deliberately not modelled: multi-plant routing alternatives, learning curves, outside
processing (subcontract) steps, inventory/WIP, taxes, warranty reserves, make-vs-buy optimization.
