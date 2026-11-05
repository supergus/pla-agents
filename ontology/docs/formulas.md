# Formulas and order of operations

All money in USD. Computed by `scripts/quote.py` from the graph, with `Decimal` arithmetic.
For each RFQ line and each quantity break `Q` (the lot size in this toy):

```
unit_material   = Σ_lines  quantityPer × unit_cost × (1 + scrapRate)
                  unit_cost = overrideUnitCost if manualOverride else matchedEntry.libraryUnitCost
                  (for made parts, library unit cost = raw material cost)

rate(wc)        = labor + machine + burden per hour, from the WorkCenterRate row for wc
                  with the latest effectiveDate on or before the quote date

unit_conversion = Σ_make lines Σ_steps ( setupHours / Q + runHours × quantityPer ) × rate(wc)

COGS            = unit_material + unit_conversion
loaded          = COGS × (1 + overhead_fraction + SGA_fraction)
unit_price      = round_half_up( loaded / (1 − targetMarginOnPrice), 0.01 )
extended        = unit_price × Q
freight         = freightPerUnit × Q   if Incoterm.sellerPaysFreight else 0
NRE             = Σ one-time NRE items on the RFQ line (NOT spread into unit price)
total quote     = extended + NRE + freight
```

`runHours × quantityPer`: run hours are per component, and a BOM line may use 2 gussets
per bracket. When `quantityPer` = 1 this reduces to `(setup_hr / lot_size + run_hr) × rate`.

## Order of operations

1. Material and conversion → COGS.
2. Overhead and SG&A, both as % of **COGS** → loaded cost.
3. Margin applied to the **loaded** cost.
4. Round the unit price to the cent, then multiply by quantity.
5. Add NRE and freight as separate lines.

Swapping steps 2 and 3 (margin first, then overhead) gives a different, wrong price.

## Markup vs margin

`targetMarginOnPrice` is margin **on price**: `price = cost / (1 − m)`.
A 25% margin on price is a 33.3% markup on cost. A 20% markup on cost is only a 16.7% margin.
The property name says which one it is on purpose. `tests/test_quote.py` checks it.

## Overhead as % of COGS is a simplification

See [simplifications.md](simplifications.md).
