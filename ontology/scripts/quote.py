"""Compute the quote for an RFQ line from the graph and print a reproducible breakdown.

Order of operations (see docs/formulas.md):
  unit_material   = sum(qty_per x unit_cost x (1 + scrap))
  unit_conversion = sum over make lines, steps of (setup_h / lot + run_h x qty_per) x rate
  COGS            = unit_material + unit_conversion
  loaded          = COGS x (1 + overhead + SG&A)
  unit_price      = round_half_up(loaded / (1 - target_margin_on_price), 0.01)
  total           = unit_price x qty + NRE + freight (only if Incoterm sellerPaysFreight)

Usage: python scripts/quote.py [--line ex:RFQ-1001-L1] [--quote ex:Q-1001-B] [--ttl build/quote-results.ttl]
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from rdflib import RDF, RDFS, Graph, Literal, URIRef
from rdflib.namespace import OWL, XSD

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rfqlib import EX, PROV, RFQ, all_data  # noqa: E402

CENT = Decimal("0.01")


def D(lit) -> Decimal:
    return Decimal(str(lit))


def one(g: Graph, s, p, required=True):
    vals = list(g.objects(s, p))
    if len(vals) > 1:
        raise ValueError(f"{s} has {len(vals)} values for {p}")
    if not vals:
        if required:
            raise ValueError(f"{s} has no value for {p}")
        return None
    return vals[0]


def current_rate(g: Graph, rate_class, on: dt.date, key_prop=None, key=None):
    """Latest row of a rate table effective on `on` (optionally filtered by key)."""
    best = None
    for r in g.subjects(RDF.type, rate_class):
        if key_prop is not None and (r, key_prop, key) not in g:
            continue
        eff = one(g, r, RFQ.effectiveDate).toPython()
        if eff <= on and (best is None or eff > best[0]):
            best = (eff, r)
    if best is None:
        raise ValueError(f"no {rate_class} effective on {on} for {key}")
    return best[1]


def wc_rate(g: Graph, rate) -> Decimal:
    return D(one(g, rate, RFQ.laborRatePerHour)) + D(one(g, rate, RFQ.machineRatePerHour)) + D(one(g, rate, RFQ.burdenRatePerHour))


@dataclass
class PriceBreak:
    quantity: int
    material: Decimal
    conversion: Decimal
    cogs: Decimal
    overhead: Decimal
    sga: Decimal
    loaded: Decimal
    unit_price: Decimal
    extended: Decimal
    nre: Decimal
    freight: Decimal
    total: Decimal
    derived_from: dict = field(default_factory=dict)
    qb: URIRef | None = None


def compute(g: Graph, line: URIRef, quote: URIRef) -> list[PriceBreak]:
    on = one(g, quote, RFQ.quoteDate).toPython()
    rfq = one(g, line, RFQ.lineOf, required=False) or next(g.subjects(RFQ.hasLine, line))
    product = one(g, line, RFQ.forProduct)
    bom = one(g, product, RFQ.hasBOM)
    category = one(g, product, RFQ.inCategory)

    # Material (independent of quantity) and conversion components
    material = Decimal(0)
    mat_src, conv_src = set(), set()
    run_cost = Decimal(0)        # per assembly
    setup_cost_per_lot = Decimal(0)
    for bl in sorted(g.objects(bom, RFQ.hasBOMLine)):
        qty_per = D(one(g, bl, RFQ.quantityPer))
        scrap = D(one(g, bl, RFQ.scrapRate, required=False) or 0)
        match = one(g, bl, RFQ.hasSimilarityMatch, required=False) or next(g.subjects(RFQ.forBOMLine, bl))
        entry = one(g, match, RFQ.matchedEntry, required=False)
        if bool(one(g, match, RFQ.manualOverride, required=False)):
            unit_cost = D(one(g, match, RFQ.overrideUnitCost))
            mat_src.add(match)
        else:
            unit_cost = D(one(g, entry, RFQ.libraryUnitCost))
            mat_src.add(entry)
        material += qty_per * unit_cost * (1 + scrap)
        if one(g, bl, RFQ.sourcingDecision) == RFQ.Make:
            routing = one(g, entry, RFQ.hasRouting)
            for step in g.objects(routing, RFQ.hasStep):
                wc = one(g, step, RFQ.atWorkCenter)
                rate_row = current_rate(g, RFQ.WorkCenterRate, on, RFQ.forWorkCenter, wc)
                conv_src.add(rate_row)
                rate = wc_rate(g, rate_row)
                setup_cost_per_lot += D(one(g, step, RFQ.setupHours)) * rate
                run_cost += D(one(g, step, RFQ.runHours)) * qty_per * rate

    oh_row = current_rate(g, RFQ.OverheadRate, on)
    sga_row = current_rate(g, RFQ.SGARate, on)
    mt_row = current_rate(g, RFQ.MarginTarget, on, RFQ.forCategory, category)
    oh, sga = D(one(g, oh_row, RFQ.fractionOfCOGS)), D(one(g, sga_row, RFQ.fractionOfCOGS))
    margin = D(one(g, mt_row, RFQ.targetMarginOnPrice))

    incoterm = one(g, one(g, rfq, RFQ.hasDeliveryTerms), RFQ.hasIncoterm)
    seller_pays = bool(one(g, incoterm, RFQ.sellerPaysFreight).toPython())
    fr_row = current_rate(g, RFQ.FreightRate, on) if seller_pays else None
    nre = sum((D(one(g, n, RFQ.amountUSD)) for n in g.objects(line, RFQ.hasNRE)), Decimal(0))

    out = []
    for qb in g.objects(line, RFQ.hasQuantityBreak):
        q = int(one(g, qb, RFQ.quantity))
        conversion = setup_cost_per_lot / q + run_cost
        cogs = material + conversion
        overhead, sga_amt = cogs * oh, cogs * sga
        loaded = cogs + overhead + sga_amt
        unit_price = (loaded / (1 - margin)).quantize(CENT, rounding=ROUND_HALF_UP)
        extended = unit_price * q
        freight = (D(one(g, fr_row, RFQ.freightPerUnit)) * q) if seller_pays else Decimal(0)
        total = (extended + nre + freight).quantize(CENT)
        out.append(PriceBreak(q, material, conversion, cogs, overhead, sga_amt, loaded, unit_price,
                              extended, nre, freight, total,
                              {"material": mat_src, "conversion": conv_src, "overhead": {oh_row},
                               "sga": {sga_row}, "margin": {mt_row}, "freight": {fr_row} if fr_row else set()},
                              qb))
    return sorted(out, key=lambda p: p.quantity)


def results_graph(g: Graph, quote: URIRef, breaks: list[PriceBreak]) -> Graph:
    """Record the computed price breaks and estimates as RDF with PROV links."""
    r = Graph()
    r.bind("rfq", RFQ); r.bind("ex", EX); r.bind("prov", PROV)
    base = "https://supergus.github.io/rfq-ontology/"
    hdr = URIRef(base + "data/quote-results")
    r.add((hdr, RDF.type, OWL.Ontology))
    r.add((hdr, RDFS.label, Literal("Computed quote results (generated by scripts/quote.py)")))
    r.add((hdr, OWL.imports, URIRef(base + "data/rfq-1001")))
    qid = str(quote).rsplit("#", 1)[1]
    act = EX[f"{qid}-ROLLUP"]
    r.add((act, RDF.type, RFQ.CostRollup))
    r.add((act, RDFS.label, Literal(f"Cost rollup for {qid}")))
    for pb in breaks:
        node = EX[f"{qid}-PB-{pb.quantity}"]
        r.add((quote, RFQ.hasPriceBreak, node))
        r.add((node, RDF.type, RFQ.QuotePriceBreak))
        r.add((node, RDFS.label, Literal(f"{qid}, qty {pb.quantity:,}")))
        r.add((node, RFQ.forQuantityBreak, pb.qb))
        r.add((node, RFQ.unitPrice, Literal(pb.unit_price, datatype=XSD.decimal)))
        r.add((node, RFQ.totalPrice, Literal(pb.total, datatype=XSD.decimal)))
        for kind, cls, amt in [("material", RFQ.MaterialCost, pb.material), ("conversion", RFQ.ConversionCost, pb.conversion),
                               ("cogs", RFQ.COGS, pb.cogs), ("loaded", RFQ.LoadedCost, pb.loaded),
                               ("freight", RFQ.FreightCost, pb.freight)]:
            if kind == "freight" and not pb.derived_from["freight"]:
                continue
            est = EX[f"{qid}-{kind.upper()}-{pb.quantity}"]
            r.add((node, RFQ.hasCostEstimate, est))
            r.add((est, RDF.type, cls))
            r.add((est, RDFS.label, Literal(f"{qid} {kind}, qty {pb.quantity:,}")))
            r.add((est, RFQ.forQuantityBreak, pb.qb))
            r.add((est, RFQ.amountUSD, Literal(amt.quantize(Decimal("0.000001")), datatype=XSD.decimal)))
            r.add((est, PROV.wasGeneratedBy, act))
            for src in pb.derived_from.get(kind, set()):
                r.add((est, PROV.wasDerivedFrom, src))
            if kind == "loaded":
                r.add((est, PROV.wasDerivedFrom, EX[f"{qid}-COGS-{pb.quantity}"]))
                for src in pb.derived_from["overhead"] | pb.derived_from["sga"]:
                    r.add((est, PROV.wasDerivedFrom, src))
            if kind == "cogs":
                r.add((est, PROV.wasDerivedFrom, EX[f"{qid}-MATERIAL-{pb.quantity}"]))
                r.add((est, PROV.wasDerivedFrom, EX[f"{qid}-CONVERSION-{pb.quantity}"]))
    return r


def fmt(x: Decimal, places=4) -> str:
    return f"{x:,.{places}f}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--line", default="RFQ-1001-L1")
    ap.add_argument("--quote", default="Q-1001-B")
    ap.add_argument("--ttl", help="write results (price breaks, estimates, PROV links) to this Turtle file")
    a = ap.parse_args(argv)
    g = all_data()
    line, quote = EX[a.line.removeprefix("ex:")], EX[a.quote.removeprefix("ex:")]
    breaks = compute(g, line, quote)
    print(f"Quote {a.quote} for {a.line}  (USD; unit price rounded half-up to the cent)")
    hdr = ["qty", "material", "conversion", "COGS", "overhead", "SG&A", "loaded", "unit price", "extended", "NRE", "freight", "TOTAL"]
    print(" | ".join(f"{h:>12}" for h in hdr))
    for p in breaks:
        row = [f"{p.quantity:,}", fmt(p.material), fmt(p.conversion), fmt(p.cogs), fmt(p.overhead), fmt(p.sga),
               fmt(p.loaded), fmt(p.unit_price, 2), fmt(p.extended, 2), fmt(p.nre, 2), fmt(p.freight, 2), fmt(p.total, 2)]
        print(" | ".join(f"{c:>12}" for c in row))
    if a.ttl:
        Path(a.ttl).parent.mkdir(parents=True, exist_ok=True)
        results_graph(g, quote, breaks).serialize(a.ttl, format="turtle")
        print(f"wrote {a.ttl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
