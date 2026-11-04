"""Tool contracts loaded from contracts/tools.ttl (data, not code)."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rdflib import RDF, RDFS, Graph, URIRef

from .ontology import PLA, RFQ

CONTRACTS = Path(__file__).resolve().parent / "contracts" / "tools.ttl"


@dataclass(frozen=True)
class Contract:
    iri: URIRef
    name: str
    agentic: bool
    requires_approval: bool
    input: str
    output: str
    stage: str
    order: int
    requires: str
    produces: str


@lru_cache(maxsize=None)
def load_contracts(path: str = str(CONTRACTS)) -> dict[str, Contract]:
    g = Graph().parse(path, format="turtle")
    out = {}
    for t in g.subjects(RDF.type, RFQ.Tool):
        c = Contract(t, str(g.value(t, RDFS.label)), bool(g.value(t, RFQ.isAgentic).toPython()),
                     bool(g.value(t, RFQ.requiresApproval).toPython()), str(g.value(t, RFQ.toolContractInput)),
                     str(g.value(t, RFQ.toolContractOutput)), str(g.value(t, PLA.stage)), int(g.value(t, PLA.order)),
                     str(g.value(t, PLA.requires)), str(g.value(t, PLA.produces)))
        out[c.name] = c
    return dict(sorted(out.items(), key=lambda kv: kv[1].order))
