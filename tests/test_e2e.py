"""RFQ-1002: incomplete -> issues -> human fix -> pass -> match -> cost -> approval gate -> send."""
from pyshacl import validate
from rdflib import Graph, Literal, URIRef

from conftest import QUOTE_DATE, open_issues, runs_of
from rfq_agents.ontology import RFQ, bind, load_files, shapes_path


def full_view(pla, g):
    v = bind(Graph()); v += pla.context; v += g
    return v


def test_rfq_1002_end_to_end(make_pla):
    pla = make_pla()
    rid = pla.start("data/rfq-1002-incomplete.ttl", run_id="1002-e2e", quote_date=QUOTE_DATE)

    s = pla.run(rid)
    assert s["status"] == "waiting_human"
    assert sorted(i["label"] for i in open_issues(s, "blocker")) == [
        "RFQ-1002: missing Incoterm", "RFQ-1002: missing material or finish spec"]
    assert not runs_of(s, "cost_quote")

    # Re-running without a fix changes nothing (idempotent: no duplicate tool runs).
    assert len(pla.run(rid)["runs"]) == len(s["runs"])

    pla.apply_fix(rid, "data/fixes/rfq-1002-fix.ttl", by="estimator")
    s = pla.run(rid)
    assert s["status"] == "waiting_approval" and s["stage"] == "approve"
    assert not open_issues(s)
    assert [r["status"] for r in runs_of(s, "validate_rfq")] == ["succeeded", "succeeded"]
    assert len(runs_of(s, "render_quote")) == 0
    assert [(b["quantity"], b["unit_price"]) for b in s["breaks"]] == [(500, "58.32")]
    _, g = pla.store.load(rid)
    quote = URIRef(s["quote_iri"])
    assert g.value(quote, RFQ.quoteStatus) == Literal("awaiting approval")
    line = next(g.objects(URIRef(s["rfq_iri"]), RFQ.hasLine))
    assert str(g.value(line, RFQ.forProduct)).endswith("BRK-100")  # agentic match, validated

    s = pla.decide(rid, approve=True, by="chris")
    s = pla.run(rid)
    assert s["status"] == "done" and s["stage"] == "send"
    assert runs_of(s, "render_quote")[0]["status"] == "succeeded"
    _, g = pla.store.load(rid)
    assert g.value(quote, RFQ.quoteStatus) == Literal("sent")
    ok, _, text = validate(full_view(pla, g), shacl_graph=load_files(shapes_path("pla-shapes.ttl")), advanced=True)
    assert ok, text
    prg = URIRef(s["program_iri"])
    assert g.value(prg, RFQ.programForRFQ) == URIRef(s["rfq_iri"])
    assert str(g.value(prg, RFQ.programStage)) == "send"


def test_reject_stops_without_sending(make_pla):
    pla = make_pla()
    rid = pla.start("data/rfq-1001.ttl", run_id="1001-rej", quote_date=QUOTE_DATE)
    pla.run(rid)
    pla.decide(rid, approve=False, by="chris")
    s = pla.run(rid)
    assert s["status"] == "rejected"
    assert not runs_of(s, "render_quote")


def test_render_refuses_without_approval(make_pla):
    """Even if a planner asked for it, render_quote itself refuses without an approved gate."""
    import pytest
    from rfq_agents.retry import FatalError
    from rfq_agents.tools import REGISTRY, ToolContext
    pla = make_pla()
    rid = pla.start("data/rfq-1001.ttl", run_id="1001-nr", quote_date=QUOTE_DATE)
    s = pla.run(rid)
    _, g = pla.store.load(rid)
    with pytest.raises(FatalError):
        REGISTRY["render_quote"].fn(ToolContext(rid, s, g, pla.llm, pla.out_dir, pla.context))


def test_competency_queries_see_program(make_pla):
    pla = make_pla()
    rid = pla.start("data/rfq-1002-incomplete.ttl", run_id="1002-cq", quote_date=QUOTE_DATE)
    pla.run(rid)
    _, g = pla.store.load(rid)
    q = (pla.context, g)
    v = full_view(pla, g)
    from rfq_agents.ontology import queries
    cq9 = next(p for p in queries() if p.stem.startswith("cq9"))
    rows = [r for r in v.query(cq9.read_text()) if str(r[0]).endswith("PRG-1002-cq")]
    assert len(rows) == 2 and {str(r[4]) for r in rows} == {"validate_rfq"}
