# Worked example: BRK-100 welded mounting bracket

RFQ-1001 rev B from Northwind Agricultural Equipment, line 1: product BRK-100 (category
*Structural brackets*), quantity breaks 100 / 1,000 / 10,000, Incoterm **DAP**, quote
Q-1001-B dated 2026-10-27, valid until 2026-11-26. Data: `data/reference.ttl`, `data/rfq-1001.ttl`.
Reproduce with `python scripts/quote.py`; asserted by `tests/test_quote.py`.

## Inputs

### EBOM and similarity matches

| Line | Component | Make/Buy | Qty per | Scrap | Matched library entry (score, method, confidence) | Unit cost |
|---|---|---|---:|---:|---|---:|
| BL-1 | Base plate | Make | 1 | 5% | PLT-210 (0.92, attribute-weighted v1, high) | 4.00 raw material |
| BL-2 | Gusset | Make | 2 | 5% | GUS-033 (0.88, attribute-weighted v1, high) | 1.50 raw material |
| BL-3 | Hex bolt M8 x 25 | Buy | 4 | 2% | BLT-M8x25 (0.99, part-number exact, high) | 0.12 |
| BL-4 | Bushing 12 mm | Buy | 2 | 0% | BSH-12 (0.71, attribute-weighted v1, medium) | 0.85 |
| BL-5 | Serial number label | Buy | 1 | 10% | none: manual override, confidence low | 0.25 |

### Work-center rates (FY2026, effective 2026-01-01, "FY2026 standard cost study")

| Work center | Labor | Machine | Burden | Rate/h |
|---|---:|---:|---:|---:|
| WC-LASER | 45 | 60 | 15 | **120** |
| WC-BRAKE | 40 | 35 | 15 | **90** |
| WC-WELD | 42 | 18 | 15 | **75** (supersedes FY2025 row at 70) |

### Routings (from the matched library entries)

| Line | Op | Work center | Setup h (per lot) | Run h (per part) |
|---|---|---|---:|---:|
| BL-1 | 10 laser cut | LASER | 0.50 | 0.05 |
| BL-1 | 20 bend | BRAKE | 0.75 | 0.04 |
| BL-1 | 30 weld gussets | WELD | 0.50 | 0.15 |
| BL-2 | 10 laser cut | LASER | 0.25 | 0.02 |

### Other rates

Overhead 12% of COGS, SG&A 10% of COGS, target margin on price 25% (brackets),
freight 0.80 per unit (seller pays under DAP), NRE: weld fixture 1,500 + first-article inspection 350 = **1,850**.

## Step 1: unit material (same for every quantity)

```
BL-1  1 × 4.00 × 1.05 = 4.2000
BL-2  2 × 1.50 × 1.05 = 3.1500
BL-3  4 × 0.12 × 1.02 = 0.4896
BL-4  2 × 0.85 × 1.00 = 1.7000
BL-5  1 × 0.25 × 1.10 = 0.2750
                        -------
unit_material         = 9.8146
```

## Step 2: unit conversion

Run cost per bracket (does not depend on quantity):
```
BL-1 op10  0.05 × 1 × 120 =  6.00
BL-1 op20  0.04 × 1 ×  90 =  3.60
BL-1 op30  0.15 × 1 ×  75 = 11.25   <- biggest driver (CQ5)
BL-2 op10  0.02 × 2 × 120 =  4.80
                            -----
run cost per bracket       = 25.65
```
Setup cost per lot:
```
0.50×120 + 0.75×90 + 0.50×75 + 0.25×120 = 60 + 67.5 + 37.5 + 30 = 195.00
```
| Q | setup / Q | + run | = unit_conversion |
|---:|---:|---:|---:|
| 100 | 1.9500 | 25.65 | **27.6000** |
| 1,000 | 0.1950 | 25.65 | **25.8450** |
| 10,000 | 0.0195 | 25.65 | **25.6695** |

## Step 3: COGS, loaded cost, price

| Q | COGS = 9.8146 + conv | loaded = COGS × 1.22 | loaded / 0.75 | unit price (to cent) |
|---:|---:|---:|---:|---:|
| 100 | 37.4146 | 45.645812 | 60.861083 | **60.86** |
| 1,000 | 35.6596 | 43.504712 | 58.006283 | **58.01** |
| 10,000 | 35.4841 | 43.290602 | 57.720803 | **57.72** |

## Step 4: quote totals

| Q | unit price × Q | + NRE | + freight (0.80 × Q) | **total** |
|---:|---:|---:|---:|---:|
| 100 | 6,086.00 | 1,850.00 | 80.00 | **8,016.00** |
| 1,000 | 58,010.00 | 1,850.00 | 800.00 | **60,660.00** |
| 10,000 | 577,200.00 | 1,850.00 | 8,000.00 | **587,050.00** |

Check on margin (Q = 1,000): (58.01 − 43.5047) / 58.01 = 25.0% of price.

## The stale-rate story

Quote rev A (2025-12-10) was priced with the FY2025 weld rate (70/h); its qty 1,000
conversion cost was 24.90 run + 192.50 / 1,000 setup = 25.0925. The FY2025 row is now
`isSupersededBy` the FY2026 row, so CQ6 flags Q-1001-A. Rev B `supersedes` rev A.
