"""Every Turtle file parses; every term in our namespace has a label and comment; the toy stays small."""
from pathlib import Path

import pytest
from rdflib import OWL, RDF, RDFS, Graph

from rfqlib import RFQ, ROOT, load

TTL = sorted(p for d in ("ontology", "data", "shapes") for p in (ROOT / d).glob("*.ttl"))


@pytest.mark.parametrize("path", TTL, ids=lambda p: str(p.relative_to(ROOT)))
def test_turtle_parses(path: Path):
    assert len(Graph().parse(path, format="turtle")) > 0


def _terms(g, kinds):
    return {s for k in kinds for s in g.subjects(RDF.type, k) if str(s).startswith(str(RFQ))}


def test_every_term_has_label_and_comment():
    g = load()
    terms = _terms(g, (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty))
    missing = [t for t in terms if not (t, RDFS.label, None) in g or not (t, RDFS.comment, None) in g]
    assert not missing, missing


def test_labels_unique():
    g = load()
    labels = [str(o) for t in _terms(g, (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty)) for o in g.objects(t, RDFS.label)]
    assert len(labels) == len(set(labels))


def test_toy_size():
    g = load()
    n_classes = len(_terms(g, (OWL.Class,)))
    assert 25 <= n_classes <= 40, n_classes
