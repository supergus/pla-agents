"""Checks on the HermiT-reasoned graph produced by ROBOT (build/reasoned.ttl; see README).
Skipped locally if ROBOT has not been run; CI sets REQUIRE_REASONER=1 so it cannot be skipped there."""
import os

import pytest
from rdflib import RDF, Graph

from rfqlib import EX, RFQ, ROOT

PATH = ROOT / "build" / "reasoned.ttl"


@pytest.fixture(scope="module")
def reasoned():
    if not PATH.exists():
        if os.environ.get("REQUIRE_REASONER"):
            pytest.fail("build/reasoned.ttl missing")
        pytest.skip("run ROBOT first (see README)")
    return Graph().parse(PATH)


def test_complete_rfq_is_classified(reasoned):
    assert (EX["RFQ-1001"], RDF.type, RFQ.CompleteRFQ) in reasoned


def test_open_world_does_not_classify_incomplete(reasoned):
    # The reasoner cannot PROVE RFQ-1002 complete, but it also never says it is incomplete.
    assert (EX["RFQ-1002"], RDF.type, RFQ.CompleteRFQ) not in reasoned
