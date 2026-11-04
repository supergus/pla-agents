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
