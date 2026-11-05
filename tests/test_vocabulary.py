"""Every term the PLA writes into a program graph is declared in the in-repo ontology (ontology/)."""
from rdflib import OWL, RDF, URIRef

from conftest import QUOTE_DATE
from pla_agents.ontology import PLA, RFQ, load_files, ontology_files


def test_program_graph_uses_only_declared_terms(make_pla):
    pla = make_pla()
    rid = pla.start("data/rfq-1002-incomplete.ttl", run_id="vocab", quote_date=QUOTE_DATE)
    pla.run(rid)
    pla.apply_fix(rid, "data/fixes/rfq-1002-fix.ttl", by="estimator")
    pla.run(rid)
    pla.decide(rid, approve=False, by="chris")
    _, g = pla.store.load(rid)

    onto = load_files(*ontology_files())
    declared = {s for t in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty) for s in onto.subjects(RDF.type, t)}
    used = {p for p in g.predicates()} | {o for o in g.objects(None, RDF.type)}
    rfq_used = {t for t in used if isinstance(t, URIRef) and str(t).startswith(str(RFQ))}
    assert rfq_used - declared == set()
    assert {t for t in used if str(t).startswith(str(PLA))} == set()

    # The part match is an ordinary rfq:SimilarityMatch for the RFQ line.
    (m,) = list(g.subjects(RDF.type, RFQ.SimilarityMatch))
    assert str(g.value(m, RFQ.matchedProduct)).endswith("BRK-100")
    assert g.value(m, RFQ.forRFQLine) is not None and g.value(m, RFQ.similarityScore) is not None
    assert any(g.subjects(RDF.type, RFQ.HumanFix))
    assert any(g.triples((None, RFQ.rejectedBy, None)))
