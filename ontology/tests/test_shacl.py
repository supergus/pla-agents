"""Closed-world completeness: RFQ-1001 conforms, RFQ-1002 reports exactly the two missing elements."""
from pyshacl import validate
from rdflib import Graph, Namespace

from rfqlib import REFERENCE, RFQ_1001, RFQ_1002, SHAPES, load

SH = Namespace("http://www.w3.org/ns/shacl#")


def _validate(*data):
    g = load(REFERENCE, *data)
    conforms, report, _ = validate(g, shacl_graph=Graph().parse(SHAPES), advanced=True)
    msgs = sorted(str(m) for m in report.objects(None, SH.resultMessage))
    return conforms, msgs


def test_complete_rfq_conforms():
    conforms, msgs = _validate(RFQ_1001)
    assert conforms, msgs


def test_incomplete_rfq_reports_missing_elements():
    conforms, msgs = _validate(RFQ_1002)
    assert not conforms
    assert msgs == ["MISSING Incoterm", "MISSING material or finish spec"]
