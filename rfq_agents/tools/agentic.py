"""Agentic tools: LLM-backed, behind the LLMClient interface. Every proposal is gated by
(1) a JSON schema, (2) SHACL (shapes/agent-output-shapes.ttl) before it touches the program graph,
and (3) confidence thresholds: low-confidence fields become Issues instead of facts."""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pyshacl import validate as shacl_validate
from rdflib import RDF, RDFS, Graph, Literal, URIRef
from rdflib.namespace import OWL, XSD

from ..ontology import EX, RFQ, REPO_ROOT, bind, load_files, resolve_input
from ..retry import FatalError, RetryableError
from ..schema import SchemaError, validate as schema_validate
from .base import IssueSpec, ToolContext, ToolResult, tool

FIELD_CONFIDENCE_MIN = 0.7
MATCH_SCORE_MIN = 0.8
INCOTERMS = ["EXW", "FCA", "FOB", "CIF", "DAP", "DDP"]
AGENT_SHAPES = REPO_ROOT / "rfq_agents" / "shapes" / "agent-output-shapes.ttl"


def shacl_gate(ctx: ToolContext, add: Graph) -> None:
    """SHACL-check a proposal against the union of context + program + proposal. Raises SchemaError."""
    g = ctx.view() + add
    ok, _, text = shacl_validate(g, shacl_graph=load_files(AGENT_SHAPES), inference="none")
    if not ok:
        raise SchemaError("agent output failed SHACL:\n" + text)


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]+", "-", s).strip("-") or "X"


# ---------------------------------------------------------------- parse_rfq_document
PARSE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["rfq_id", "lines", "confidence"],
    "properties": {
        "rfq_id": {"type": "string", "minLength": 1}, "revision": {"type": ["string", "null"]},
        "customer": {"type": ["string", "null"]}, "payment_terms": {"type": ["string", "null"]},
        "incoterm": {"type": ["string", "null"], "enum": INCOTERMS + [None]},
        "delivery_date": {"type": ["string", "null"]}, "drawing": {"type": ["string", "null"]},
        "material_spec": {"type": ["string", "null"]}, "finish_spec": {"type": ["string", "null"]},
        "lines": {"type": "array", "minItems": 1, "items": {
            "type": "object", "required": ["part", "quantities"], "properties": {
                "part": {"type": "string", "minLength": 1}, "description": {"type": ["string", "null"]},
                "quantities": {"type": "array", "minItems": 1, "items": {"type": "integer", "minimum": 1}}}}},
        "confidence": {"type": "object"},
    },
}
PARSE_SYSTEM = ("You extract a manufacturing RFQ (request for quote) into JSON. Use null for anything not "
                "stated. Never guess. For each field give a confidence 0..1 in `confidence`.")


def _structured_intake(ctx: ToolContext, path: Path) -> ToolResult:
    g = bind(Graph())
    g.parse(path, format="turtle")
    for s in list(g.subjects(RDF.type, OWL.Ontology)):
        g.remove((s, None, None))
    rfqs = sorted(g.subjects(RDF.type, RFQ.RFQPackage))
    if len(rfqs) != 1:
        raise FatalError(f"{path.name}: expected exactly one RFQPackage, found {len(rfqs)}")
    return ToolResult(outputs={"mode": "structured (Turtle input; no LLM call)", "rfq": rfqs[0].split("#")[-1],
                               "triples": len(g)},
                      add=g, output_nodes=[rfqs[0]], state={"rfq_iri": str(rfqs[0])})


def map_parsed(d: dict) -> tuple[Graph, URIRef, list[IssueSpec]]:
    g, issues = bind(Graph()), []
    conf = d.get("confidence", {})
    rid = _slug(d["rfq_id"])
    rfq = EX[rid]

    def trusted(field: str) -> bool:
        if d.get(field) is None:
            return False
        c = conf.get(field, 1.0)
        if not isinstance(c, (int, float)) or c < FIELD_CONFIDENCE_MIN:
            issues.append(IssueSpec(f"lowconf:{field}", f"{d['rfq_id']}: low-confidence {field} "
                                    f"({d[field]!r}, confidence {c}) needs human check", "warning"))
            return False
        return True

    g.add((rfq, RDF.type, RFQ.RFQPackage)); g.add((rfq, RDFS.label, Literal(f"{d['rfq_id']} (parsed)")))
    g.add((rfq, RFQ.identifier, Literal(d["rfq_id"])))
    if d.get("revision"):
        g.add((rfq, RFQ.revision, Literal(d["revision"])))
    if trusted("customer"):
        cust = EX[f"CUST-{_slug(d['customer'])}"]
        g.add((cust, RDF.type, RFQ.Customer)); g.add((cust, RDFS.label, Literal(d["customer"])))
        g.add((rfq, RFQ.issuedBy, cust))
    ct = EX[f"{rid}-CT"]
    g.add((ct, RDF.type, RFQ.CommercialTerms)); g.add((rfq, RFQ.hasCommercialTerms, ct))
    if trusted("payment_terms"):
        g.add((ct, RFQ.paymentTerms, Literal(d["payment_terms"])))
    dt_ = EX[f"{rid}-DT"]
    g.add((dt_, RDF.type, RFQ.DeliveryTerms)); g.add((rfq, RFQ.hasDeliveryTerms, dt_))
    if trusted("incoterm"):
        g.add((dt_, RFQ.hasIncoterm, RFQ[d["incoterm"]]))
    if trusted("delivery_date"):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["delivery_date"]):
            raise SchemaError("delivery_date must be YYYY-MM-DD")
        g.add((dt_, RFQ.requestedDeliveryDate, Literal(d["delivery_date"] + "T00:00:00", datatype=XSD.dateTime)))
    for field, cls in (("drawing", RFQ.Drawing), ("material_spec", RFQ.MaterialSpec), ("finish_spec", RFQ.FinishSpec)):
        if trusted(field):
            n = EX[f"{rid}-{field.upper().replace('_', '-')}"]
            g.add((n, RDF.type, cls)); g.add((n, RDFS.label, Literal(d[field])))
            g.add((rfq, RFQ.hasTechnicalRequirement, n))
    if conf.get("lines", 1.0) < FIELD_CONFIDENCE_MIN:
        issues.append(IssueSpec("lowconf:lines", f"{d['rfq_id']}: low-confidence line items need human check", "blocker"))
    for i, ln in enumerate(d["lines"], 1):
        line = EX[f"{rid}-L{i}"]
        g.add((line, RDF.type, RFQ.RFQLine)); g.add((rfq, RFQ.hasLine, line))
        g.add((line, RDFS.label, Literal(f"{d['rfq_id']} line {i}: {ln['part']} {ln.get('description') or ''}".strip())))
        for q in ln["quantities"]:
            qb = EX[f"{rid}-L{i}-QB-{q}"]
            g.add((qb, RDF.type, RFQ.QuantityBreak)); g.add((qb, RFQ.quantity, Literal(q, datatype=XSD.integer)))
            g.add((line, RFQ.hasQuantityBreak, qb))
    return g, rfq, issues


@tool("parse_rfq_document", agentic=True)
def parse_rfq_document(ctx: ToolContext) -> ToolResult:
    path = resolve_input(ctx.state["rfq_path"])
    if path.suffix == ".ttl":
        return _structured_intake(ctx, path)
    text = path.read_text(errors="replace")[:20000]
    d = ctx.llm.complete_json("parse_rfq_document", PARSE_SYSTEM, text, PARSE_SCHEMA)
    schema_validate(d, PARSE_SCHEMA)
    add, rfq, issues = map_parsed(d)
    shacl_gate(ctx, add)
    return ToolResult(outputs={"mode": f"llm ({ctx.llm.name})", "rfq": rfq.split("#")[-1], "proposal": d},
                      add=add, output_nodes=[rfq], issues=issues, state={"rfq_iri": str(rfq)})


# ---------------------------------------------------------------- match_library_part
MATCH_SCHEMA = {"type": "object", "required": ["product_id", "score", "method"], "properties": {
    "product_id": {"type": "string", "minLength": 1}, "score": {"type": "number", "minimum": 0, "maximum": 1},
    "method": {"type": "string", "minLength": 1}, "rationale": {"type": ["string", "null"]}}}
MATCH_SYSTEM = ("Match the requested part to the most similar known product. Choose product_id ONLY from the "
                "candidate list. Give a similarity score 0..1 and name your method.")


@tool("match_library_part", agentic=True)
def match_library_part(ctx: ToolContext) -> ToolResult:
    g = ctx.view()
    add, issues, out, inputs = bind(Graph()), [], [], []
    candidates = {p.split("#")[-1]: str(g.value(p, RDFS.label)) for p in g.subjects(RDF.type, RFQ.Product)
                  if g.value(p, RFQ.hasBOM) is not None}
    for line in sorted(g.objects(ctx.rfq, RFQ.hasLine)):
        inputs.append(line)
        existing = g.value(line, RFQ.forProduct)
        if existing is not None:
            out.append({"line": line.split("#")[-1], "product": existing.split("#")[-1], "method": "given in RFQ"})
            continue
        reqs = [str(g.value(r, RDFS.label)) for r in g.objects(ctx.rfq, RFQ.hasTechnicalRequirement)]
        user = json.dumps({"line": str(g.value(line, RDFS.label)), "requirements": reqs, "candidates": candidates})
        d = ctx.llm.complete_json("match_library_part", MATCH_SYSTEM, user, MATCH_SCHEMA)
        schema_validate(d, MATCH_SCHEMA)
        if d["product_id"] not in candidates:
            raise SchemaError(f"model proposed unknown product {d['product_id']!r}")
        lm = EX[f"SM-{line.split('#')[-1]}"]
        rec = {"line": line.split("#")[-1], "product": d["product_id"], "score": d["score"], "method": d["method"]}
        if d["score"] < MATCH_SCORE_MIN:
            issues.append(IssueSpec(f"match:{line}", f"{line.split('#')[-1]}: best match {d['product_id']} scored "
                                    f"{d['score']} (< {MATCH_SCORE_MIN}); estimator must confirm"))
            rec["written"] = False
        else:
            add.add((line, RFQ.forProduct, EX[d["product_id"]]))
            add.add((lm, RDF.type, RFQ.SimilarityMatch)); add.add((lm, RDFS.label, Literal(f"Match {line.split('#')[-1]} to {d['product_id']}")))
            add.add((lm, RFQ.forRFQLine, line)); add.add((lm, RFQ.matchedProduct, EX[d["product_id"]]))
            add.add((lm, RFQ.similarityScore, Literal(Decimal(str(d["score"])), datatype=XSD.decimal)))
            add.add((lm, RFQ.similarityMethod, Literal(d["method"])))
            add.add((lm, RFQ.confidence, Literal("high" if d["score"] >= 0.85 else "medium")))
            add.add((lm, RFQ.manualOverride, Literal(False)))
            rec["written"] = True
        out.append(rec)
    if len(add):
        shacl_gate(ctx, add)
    return ToolResult(outputs={"matches": out}, add=add, inputs=inputs,
                      output_nodes=sorted(set(add.subjects(RDF.type, RFQ.SimilarityMatch))), issues=issues,
                      resolves_prefix="match:", state={"match_ok": not issues})


# ---------------------------------------------------------------- explain_quote
EXPLAIN_SCHEMA = {"type": "object", "required": ["summary"], "properties": {"summary": {"type": "string", "minLength": 10}}}
EXPLAIN_SYSTEM = ("Write a 2-3 sentence plain-language summary of this quote for a customer. Use ONLY numbers "
                  "that appear in the input; never calculate new ones.")
_NUM = re.compile(r"(?<![\w.,-])\$?(\d[\d,]*(?:\.\d+)?)")


def _norm(x: str) -> Decimal | None:
    try:
        return Decimal(x.replace(",", "")).normalize()
    except InvalidOperation:
        return None


@tool("explain_quote", agentic=True)
def explain_quote(ctx: ToolContext) -> ToolResult:
    breaks = ctx.state.get("breaks") or []
    quote = ctx.state.get("quote_iri", "").split("#")[-1]
    payload = {"quote": quote, "breaks": [{k: b[k] for k in ("line", "quantity", "unit_price", "nre", "freight", "total")}
                                          for b in breaks]}
    d = ctx.llm.complete_json("explain_quote", EXPLAIN_SYSTEM, json.dumps(payload), EXPLAIN_SCHEMA)
    schema_validate(d, EXPLAIN_SCHEMA)
    allowed = {_norm(str(v)) for b in payload["breaks"] for v in b.values()} | {_norm(n) for n in re.findall(r"\d+", quote)}
    invented = [n for n in _NUM.findall(d["summary"]) if _norm(n) not in allowed]
    if invented:
        raise SchemaError(f"summary contains numbers not in the computed quote: {invented}")
    add = bind(Graph())
    add.add((URIRef(ctx.state["quote_iri"]), RFQ.quoteSummary, Literal(d["summary"])))
    return ToolResult(outputs={"summary": d["summary"]}, add=add, inputs=[URIRef(ctx.state["quote_iri"])],
                      state={"quote_summary": d["summary"]})
