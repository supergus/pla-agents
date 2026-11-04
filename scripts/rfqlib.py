"""Shared helpers: load the ontology and data with rdflib."""
from pathlib import Path

from rdflib import Graph, Namespace

ROOT = Path(__file__).resolve().parent.parent
RFQ = Namespace("https://supergus.github.io/rfq-ontology/ns#")
EX = Namespace("https://supergus.github.io/rfq-ontology/data#")
PROV = Namespace("http://www.w3.org/ns/prov#")

ONTOLOGY_FILES = sorted((ROOT / "ontology").glob("*.ttl"))
REFERENCE = ROOT / "data" / "reference.ttl"
RFQ_1001 = ROOT / "data" / "rfq-1001.ttl"
RFQ_1002 = ROOT / "data" / "rfq-1002-incomplete.ttl"
SHAPES = ROOT / "shapes" / "rfq-completeness.ttl"


def load(*paths, ontology=True) -> Graph:
    g = Graph()
    g.bind("rfq", RFQ)
    g.bind("ex", EX)
    g.bind("prov", PROV)
    files = (ONTOLOGY_FILES if ontology else []) + [Path(p) for p in paths]
    for f in files:
        g.parse(f, format="turtle")
    return g


def all_data() -> Graph:
    return load(REFERENCE, RFQ_1001, RFQ_1002)
