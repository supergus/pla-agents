"""The PLA's cost_quote reproduces the BRK-100 worked example exactly."""
from decimal import Decimal

from conftest import QUOTE_DATE, open_issues, runs_of

EXPECTED = {100: ("60.86", "8016.00"), 1000: ("58.01", "60660.00"), 10000: ("57.72", "587050.00")}


def test_rfq_1001_worked_example_numbers(make_pla):
    pla = make_pla()
    rid = pla.start("data/rfq-1001.ttl", run_id="1001-we", quote_date=QUOTE_DATE)
    state = pla.run(rid)
    assert state["status"] == "waiting_approval", state["status"]
    assert not open_issues(state)
    got = {b["quantity"]: (b["unit_price"], b["total"]) for b in state["breaks"]}
    assert {q: (Decimal(u), Decimal(t)) for q, (u, t) in got.items()} == \
           {q: (Decimal(u), Decimal(t)) for q, (u, t) in EXPECTED.items()}
    assert state["quote_iri"].endswith("Q-1001-B")  # existing un-priced revision B is reused
    assert len(runs_of(state, "render_quote")) == 0  # gate holds


def test_worked_example_written_to_graph(make_pla):
    from rfq_agents.ontology import RFQ
    pla = make_pla()
    rid = pla.start("data/rfq-1001.ttl", run_id="1001-g", quote_date=QUOTE_DATE)
    pla.run(rid)
    _, g = pla.store.load(rid)
    prices = sorted(str(o) for o in g.objects(None, RFQ.unitPrice))
    assert prices == ["57.72", "58.01", "60.86"]
