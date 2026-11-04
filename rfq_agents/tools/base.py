"""Tool interface: a tool is a function ToolContext -> ToolResult, registered under its contract name."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from rdflib import Graph, URIRef

from ..ontology import bind, context_graph


@dataclass
class IssueSpec:
    key: str                    # stable key, so re-runs update rather than duplicate
    label: str
    severity: str = "blocker"   # blocker | warning | info
    assigned_to: str = "human:estimator"


@dataclass
class ToolResult:
    outputs: dict = field(default_factory=dict)        # JSON summary, stored in the run log
    add: Graph = field(default_factory=lambda: bind(Graph()))  # triples to write to the program graph
    remove: list = field(default_factory=list)         # (s, p, None) patterns to remove first
    inputs: list[URIRef] = field(default_factory=list)
    output_nodes: list[URIRef] = field(default_factory=list)
    issues: list[IssueSpec] = field(default_factory=list)
    resolves_prefix: str | None = None                 # resolve open issues with this key prefix not re-raised
    state: dict = field(default_factory=dict)          # facts for the planner (e.g. validation_ok)


@dataclass
class ToolContext:
    run_id: str
    state: dict
    program: Graph
    llm: object
    out_dir: Path
    _ctx: Graph | None = None

    def view(self) -> Graph:
        """Union of read-only context (ontology, rates, catalog, contracts) and the program graph."""
        g = bind(Graph())
        g += self._ctx if self._ctx is not None else context_graph()
        g += self.program
        return g

    @property
    def rfq(self) -> URIRef | None:
        r = self.state.get("rfq_iri")
        return URIRef(r) if r else None


@dataclass
class Tool:
    name: str
    fn: Callable[[ToolContext], ToolResult]
    agentic: bool


REGISTRY: dict[str, Tool] = {}


def tool(name: str, agentic: bool):
    def deco(fn):
        REGISTRY[name] = Tool(name, fn, agentic)
        return fn
    return deco
