"""Deterministic tools: plain code, same input -> same output."""
from __future__ import annotations

from decimal import Decimal

from pyshacl import validate as shacl_validate
from rdflib import RDF, RDFS, Graph, Literal, URIRef
from rdflib.namespace import OWL, XSD

from ..ontology import EX, PLA, PROV, RFQ, bind, load_files, queries, quote_module, shapes_path
from ..retry import FatalError
from .base import IssueSpec, ToolContext, ToolResult, tool


def rfq_lines(g: Graph, rfq: URIRef) -> list[URIRef]:
    return sorted(g.objects(rfq, RFQ.hasLine))


@tool("validate_rfq", agentic=False)
def validate_rfq(ctx: ToolContext) -> ToolResult:
    g = ctx.view()
    rfq = ctx.rfq
    if rfq is None or (rfq, RDF.type, RFQ.RFQPackage) not in g:
        raise FatalError("no RFQ package in the program graph")
    shapes = load_files(shapes_path("rfq-completeness.ttl"))
    conforms, report, _ = shacl_validate(g, shacl_graph=shapes, inference="none", advanced=True)
    SH = "http://www.w3.org/ns/shacl#"
    scope = {rfq, *rfq_lines(g, rfq)}
    msgs = sorted({str(report.value(r, URIRef(SH + "resultMessage")))
                   for r in report.subjects(RDF.type, URIRef(SH + "ValidationResult"))
                   if report.value(r, URIRef(SH + "focusNode")) in scope})
    rid = str(g.value(rfq, RFQ.identifier) or rfq.split("#")[-1])
    issues = [IssueSpec(f"shacl:{m}", f"{rid}: {m.replace('MISSING', 'missing')}") for m in msgs]
    return ToolResult(outputs={"conforms": not msgs, "violations": msgs}, inputs=[rfq], issues=issues,
                      resolves_prefix="shacl:", state={"validation_ok": not msgs})


@tool("run_competency_queries", agentic=False)
def run_competency_queries(ctx: ToolContext) -> ToolResult:
    g = ctx.view()
    counts, open_issues = {}, []
    for q in queries():
        rows = list(g.query(q.read_text()))
        counts[q.stem] = len(rows)
        if q.stem.startswith("cq9-"):
            prog = URIRef(ctx.state["program_iri"])
            open_issues = [str(r[1]).split("#")[-1] for r in rows if r[0] == prog]
    return ToolResult(outputs={"row_counts": counts, "open_issues_in_program": open_issues},
                      inputs=[URIRef(ctx.state["program_iri"])])


@tool("explode_bom", agentic=False)
def explode_bom(ctx: ToolContext) -> ToolResult:
    g = ctx.view()
    lines_out, issues = [], []
    for line in rfq_lines(g, ctx.rfq):
        product = g.value(line, RFQ.forProduct)
        if product is None:
            raise FatalError(f"{line.split('#')[-1]} has no matched product; run match_library_part first")
        bom = g.value(product, RFQ.hasBOM)
        if bom is None:
            raise FatalError(f"{product.split('#')[-1]} has no BOM")
        rows = []
        for bl in sorted(g.objects(bom, RFQ.hasBOMLine)):
            match = g.value(bl, RFQ.hasSimilarityMatch) or g.value(None, RFQ.forBOMLine, bl)
            if match is None:
                issues.append(IssueSpec(f"bom:{bl}", f"BOM line {bl.split('#')[-1]} has no library match or manual cost"))
            rows.append({"bom_line": bl.split("#")[-1], "component": str(g.value(g.value(bl, RFQ.ofComponent), RDFS.label)),
                         "qty_per": float(g.value(bl, RFQ.quantityPer)),
                         "make_buy": str(g.value(bl, RFQ.sourcingDecision)).split("#")[-1],
                         "match": match.split("#")[-1] if match else None})
        lines_out.append({"line": line.split("#")[-1], "product": product.split("#")[-1], "bom": rows})
    return ToolResult(outputs={"lines": lines_out}, inputs=rfq_lines(g, ctx.rfq), issues=issues,
                      resolves_prefix="bom:", state={"bom_ok": not issues})


def _quote_for(g: Graph, ctx: ToolContext) -> tuple[URIRef, Graph]:
    """An existing un-priced Quote for this RFQ with a quote date (e.g. Q-1001-B), else a new one."""
    add = bind(Graph())
    for q in sorted(g.subjects(RFQ.respondsTo, ctx.rfq)):
        if g.value(q, RFQ.quoteDate) is not None and g.value(q, RFQ.hasPriceBreak) is None:
            return q, add
    rid = str(g.value(ctx.rfq, RFQ.identifier) or ctx.rfq.split("#")[-1]).removeprefix("RFQ-")
    q = EX[f"Q-{rid}-PLA"]
    add.add((q, RDF.type, RFQ.Quote)); add.add((q, RDFS.label, Literal(f"Quote Q-{rid} (PLA draft)")))
    add.add((q, RFQ.identifier, Literal(f"Q-{rid}"))); add.add((q, RFQ.revision, Literal("A")))
    add.add((q, RFQ.respondsTo, ctx.rfq))
    add.add((q, RFQ.quoteDate, Literal(f"{ctx.state['quote_date']}T00:00:00", datatype=XSD.dateTime)))
    return q, add


@tool("cost_quote", agentic=False)
def cost_quote(ctx: ToolContext) -> ToolResult:
    """Costs every RFQ line with the ontology repo's own scripts/quote.py (pinned), so the formulas
    and rounding are exactly those of docs/formulas.md and the worked example."""
    qm = quote_module()
    g = ctx.view()
    quote, add = _quote_for(g, ctx)
    work = g + add
    breaks_out = []
    for line in rfq_lines(work, ctx.rfq):
        try:
            breaks = qm.compute(work, line, quote)
        except (ValueError, StopIteration) as e:
            raise FatalError(f"cannot cost {line.split('#')[-1]}: {e}") from e
        res = qm.results_graph(work, quote, breaks)
        for s in list(res.subjects(RDF.type, OWL.Ontology)):
            res.remove((s, None, None))
        add += res
        for pb in breaks:
            breaks_out.append({"line": line.split("#")[-1], "quantity": pb.quantity,
                               "material": str(pb.material.quantize(Decimal("0.0001"))),
                               "conversion": str(pb.conversion.quantize(Decimal("0.0001"))),
                               "cogs": str(pb.cogs.quantize(Decimal("0.0001"))),
                               "loaded": str(pb.loaded.quantize(Decimal("0.0001"))),
                               "unit_price": str(pb.unit_price), "nre": str(pb.nre.quantize(Decimal("0.01"))),
                               "freight": str(pb.freight.quantize(Decimal("0.01"))), "total": str(pb.total)})
    add.add((quote, RFQ.quoteStatus, Literal("draft")))
    return ToolResult(outputs={"quote": quote.split("#")[-1], "breaks": breaks_out}, add=add,
                      remove=[(quote, RFQ.quoteStatus, None)], inputs=[ctx.rfq], output_nodes=[quote],
                      state={"quote_iri": str(quote), "breaks": breaks_out})


@tool("render_quote", agentic=False)
def render_quote(ctx: ToolContext) -> ToolResult:
    g = ctx.view()
    quote = URIRef(ctx.state["quote_iri"])
    gate = g.value(None, RFQ.gateForQuote, quote)
    if gate is None or str(g.value(gate, RFQ.gateDecision)) != "approved":
        raise FatalError("render_quote requires an approved ApprovalGate (agents propose, people approve)")
    qid = str(g.value(quote, RFQ.identifier)); rev = str(g.value(quote, RFQ.revision) or "")
    lines = [f"# Quotation {qid} rev {rev}", "",
             f"In response to {g.value(ctx.rfq, RFQ.identifier)}. Approved by {g.value(gate, RFQ.approvedBy)}.", "",
             "| Line | Quantity | Unit price (USD) | Total (USD) |", "|---|---:|---:|---:|"]
    for b in ctx.state.get("breaks", []):
        lines.append(f"| {b['line']} | {b['quantity']:,} | {Decimal(b['unit_price']):,.2f} | {Decimal(b['total']):,.2f} |")
    if ctx.state.get("quote_summary"):
        lines += ["", ctx.state["quote_summary"]]
    lines += ["", "Totals include NRE and, where the Incoterm requires it, freight."]
    out = ctx.out_dir / ctx.run_id / f"{qid}-{rev}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n"); tmp.replace(out)
    add = bind(Graph())
    add.add((quote, RFQ.quoteStatus, Literal("sent")))
    return ToolResult(outputs={"document": str(out), "sent": "simulated (written to disk; nothing leaves the box)"},
                      add=add, remove=[(quote, RFQ.quoteStatus, None)], inputs=[quote], output_nodes=[quote])
