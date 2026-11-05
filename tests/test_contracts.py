"""Tool contracts (data) == ontology Tool individuals == code registry."""
from rdflib import RDF, RDFS, Graph

from pla_agents.contracts import load_contracts
from pla_agents.ontology import RFQ, ontology_dir
from pla_agents.tools import REGISTRY


def ontology_tools():
    g = Graph().parse(ontology_dir() / "data" / "pla-run-1002.ttl")
    return {str(g.value(t, RDFS.label)): (t, g) for t in g.subjects(RDF.type, RFQ.Tool)}


def test_contract_names_match_ontology_and_registry():
    assert set(load_contracts()) == set(ontology_tools()) == set(REGISTRY)
    assert len(REGISTRY) == 8


def test_contract_fields_match_ontology():
    onto = ontology_tools()
    for name, c in load_contracts().items():
        t, g = onto[name]
        assert c.iri == t
        assert c.agentic == g.value(t, RFQ.isAgentic).toPython()
        assert c.requires_approval == g.value(t, RFQ.requiresApproval).toPython()
        assert c.input == str(g.value(t, RFQ.toolContractInput))
        assert c.output == str(g.value(t, RFQ.toolContractOutput))


def test_registry_kind_matches_contract():
    for name, c in load_contracts().items():
        assert REGISTRY[name].agentic == c.agentic, name
    assert [n for n, c in load_contracts().items() if c.requires_approval] == ["render_quote"]
