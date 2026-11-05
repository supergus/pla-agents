"""Locate and load the in-repo ontology (ontology/, formerly the supergus/rfq-ontology repo)."""
from __future__ import annotations

import importlib.util
import os
from functools import lru_cache
from pathlib import Path

from rdflib import Graph, Namespace

REPO_ROOT = Path(__file__).resolve().parent.parent
RFQ = Namespace("https://supergus.github.io/rfq-ontology/ns#")
EX = Namespace("https://supergus.github.io/rfq-ontology/data#")
PROV = Namespace("http://www.w3.org/ns/prov#")
PLA = Namespace("https://supergus.github.io/rfq-agents/ns#")


class OntologyMissing(RuntimeError):
    pass


def ontology_dir() -> Path:
    env = os.environ.get("PLA_ONTOLOGY_DIR")
    d = Path(env) if env else REPO_ROOT / "ontology"
    if not (d / "ontology" / "rfq-pla.ttl").exists():
        raise OntologyMissing(f"ontology not found at {d}; expected the in-repo ontology/ tree or $PLA_ONTOLOGY_DIR")
    return d


def bind(g: Graph) -> Graph:
    g.bind("rfq", RFQ); g.bind("ex", EX); g.bind("prov", PROV); g.bind("pla", PLA)
    return g


@lru_cache(maxsize=None)
def _parsed(path: str) -> Graph:
    g = Graph()
    g.parse(path, format="turtle")
    return g


def load_files(*paths: Path) -> Graph:
    g = bind(Graph())
    for p in paths:
        g += _parsed(str(p))
    return g


def ontology_files() -> list[Path]:
    return sorted((ontology_dir() / "ontology").glob("*.ttl"))


def context_graph() -> Graph:
    """Ontology modules + reference rates + the product catalog (BRK-100 lives in rfq-1001.ttl)
    + this repo's tool contracts. Read-only context; program facts live in the run's own graph."""
    d = ontology_dir()
    return load_files(*ontology_files(), d / "data" / "reference.ttl", d / "data" / "rfq-1001.ttl",
                      REPO_ROOT / "pla_agents" / "contracts" / "tools.ttl")


def shapes_path(name: str) -> Path:
    return ontology_dir() / "shapes" / name


def queries() -> list[Path]:
    return sorted((ontology_dir() / "queries").glob("*.rq"))


@lru_cache(maxsize=None)
def quote_module():
    """The ontology repo's scripts/quote.py, imported from the pinned checkout (single source of truth
    for the costing formulas, so the PLA's numbers cannot drift from the worked example)."""
    scripts = ontology_dir() / "scripts"
    import sys
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location("rfq_ontology_quote", scripts / "quote.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses need the module registered
    spec.loader.exec_module(mod)
    return mod


def resolve_input(path: str) -> Path:
    """An input path as given, else relative to the ontology checkout (e.g. data/rfq-1002-incomplete.ttl)."""
    p = Path(path)
    if p.exists():
        return p.resolve()
    q = ontology_dir() / path
    if q.exists():
        return q.resolve()
    q = REPO_ROOT / path
    if q.exists():
        return q.resolve()
    raise FileNotFoundError(path)
