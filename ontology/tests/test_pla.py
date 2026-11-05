"""PLA module: SHACL run-record checks, the approval gate rule, and tool classification."""
from pyshacl import validate
from rdflib import RDF, RDFS, Graph, Literal, Namespace

from rfqlib import EX, PLA_RUN, PLA_SHAPES, REFERENCE, RFQ, RFQ_1001, RFQ_1002, load

SH = Namespace("http://www.w3.org/ns/shacl#")
AGENTIC = {"parse_rfq_document", "match_library_part", "explain_quote"}
DETERMINISTIC = {"validate_rfq", "explode_bom", "cost_quote", "run_competency_queries", "render_quote"}


def _validate(g):
    conforms, report, _ = validate(g, shacl_graph=Graph().parse(PLA_SHAPES), advanced=True)
    return conforms, sorted(str(m) for m in report.objects(None, SH.resultMessage))


def _graph():
    return load(REFERENCE, RFQ_1001, RFQ_1002, PLA_RUN)


def test_sample_run_conforms():
    conforms, msgs = _validate(_graph())
    assert conforms, msgs


def test_tool_catalogue():
    g = _graph()
    names = {str(lbl): bool(g.value(t, RFQ.isAgentic).toPython())
             for t in g.subjects(RDF.type, RFQ.Tool) for lbl in [g.value(t, RDFS.label)]}
    assert {n for n, ai in names.items() if ai} == AGENTIC
    assert {n for n, ai in names.items() if not ai} == DETERMINISTIC


def test_retry_links_to_failed_attempt():
    g = _graph()
    prev = g.value(EX["RUN-1002-4"], RFQ.retryOf)
    assert prev == EX["RUN-1002-3"] and str(g.value(prev, RFQ.runStatus)) == "failed"
    assert g.value(EX["RUN-1002-4"], RFQ.attemptNumber).toPython() == 2


def test_quote_cannot_be_sent_without_approval():
    g = _graph()
    g.set((EX["Q-1002-A"], RFQ.quoteStatus, Literal("sent")))
    conforms, msgs = _validate(g)
    assert not conforms and msgs == ["QUOTE sent without an approved gate"]
    g.set((EX["GATE-1002"], RFQ.gateDecision, Literal("approved")))
    assert _validate(g)[0]


def test_incomplete_run_records_are_reported():
    g = _graph()
    g.remove((EX["RUN-1002-1"], RFQ.attemptNumber, None))
    g.remove((EX["ISS-1002-1"], RFQ.raisedBy, None))
    conforms, msgs = _validate(g)
    assert not conforms and msgs == ["ISSUE has no raisedBy", "TOOL RUN has no attempt number"]


def _all_shapes_validate(g):
    from rfqlib import SHAPES
    sg = Graph().parse(PLA_SHAPES); sg.parse(SHAPES)
    conforms, report, _ = validate(g, shacl_graph=sg, advanced=True)
    return conforms, sorted(str(m) for m in report.objects(None, SH.resultMessage))


def test_rfq_line_match_is_a_similarity_match():
    g = _graph()
    m = EX["SM-1002-L1"]
    assert (m, RDF.type, RFQ.SimilarityMatch) in g
    assert g.value(m, RFQ.forRFQLine) == EX["RFQ-1002-L1"] and g.value(m, RFQ.matchedProduct) == EX["BRK-100"]
    assert g.value(EX["RUN-1002-4"], RFQ.toolRunOutput) == m
    msgs = [x for x in _all_shapes_validate(g)[1] if "match" in x.lower()]
    assert msgs == [], msgs


def test_match_must_have_exactly_one_subject():
    g = _graph()
    g.add((EX["SM-1002-L1"], RFQ.forBOMLine, EX["BL-1"]))
    assert "match must be for exactly one BOM line or one RFQ line, not both" in _all_shapes_validate(g)[1]
    g = _graph()
    g.remove((EX["SM-1002-L1"], RFQ.forRFQLine, None))
    assert "match must be for exactly one BOM line or one RFQ line, not both" in _all_shapes_validate(g)[1]


def test_pla_run_terms():
    g = _graph()
    g.add((EX["RUN-1002-1"], RFQ.runError, Literal("boom")))
    g.add((EX["GATE-1002"], RFQ.rejectedBy, Literal("human:sales")))
    fix = EX["FIX-1"]
    g.add((fix, RDF.type, RFQ.HumanFix)); g.add((EX["PRG-1002"], RFQ.hasFix, fix))
    conforms, msgs = _validate(g)
    assert not conforms and msgs == ["FIX has no appliedBy", "FIX has no time",
                                     "GATE decider does not match its decision",
                                     "RUN ERROR recorded on a run that did not fail"], msgs
