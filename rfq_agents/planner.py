"""Planners choose the PLA's next action from the program state and the tool contracts.

`DeterministicPlanner` is a rule-based planner over the contracts' requires/produces artifacts.
`LLMPlanner` shows the swap-in point: it asks a model to pick among the tools the deterministic
rules say are *eligible*, so a model can reorder work but can never skip a gate or call an
ineligible tool."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from .contracts import Contract

# Tools that re-check data and can close the blocker issues they raised.
RECHECK_TOOLS = ("validate_rfq", "match_library_part", "explode_bom")

STAGES = ["intake", "validate", "match", "cost", "approve", "send"]


@dataclass
class Decision:
    kind: str                 # call | open_gate | wait_human | wait_approval | done
    tool: str | None = None
    reason: str = ""


class Planner(Protocol):
    def next(self, state: dict, contracts: dict[str, Contract]) -> Decision: ...


def step_key(state: dict, tool: str) -> str:
    """Idempotency key per step. Pre-gate steps are keyed by the RFQ data version, so a human fix
    (which bumps rfq_version) re-runs exactly the steps that depend on the RFQ data."""
    if tool not in ("parse_rfq_document", "render_quote"):
        return f"{tool}@rfq-v{state.get('rfq_version', 1)}"
    return tool


def available_artifacts(state: dict) -> set[str]:
    done = state.get("done", {})
    have = {"rfq_document", "program_graph"}
    if "parse_rfq_document" in done:
        have.add("rfq_graph")
    if f"validate_rfq@rfq-v{state.get('rfq_version', 1)}" in done and state.get("validation_ok"):
        have.add("validation_report")
    v = state.get("rfq_version", 1)
    if f"match_library_part@rfq-v{v}" in done and state.get("match_ok", True):
        have.add("product_match")
    if f"explode_bom@rfq-v{v}" in done and state.get("bom_ok", True):
        have.add("bom")
    if f"cost_quote@rfq-v{v}" in done:
        have.add("quote")
    if state.get("gate_decision") == "approved":
        have.add("approved_quote")
    return have


def eligible(state: dict, contracts: dict[str, Contract]) -> list[str]:
    have = available_artifacts(state)
    done = state.get("done", {})
    out = []
    for name, c in contracts.items():
        if step_key(state, name) in done or c.requires not in have:
            continue
        if c.requires_approval and state.get("gate_decision") != "approved":
            continue
        if name == "run_competency_queries" and not state.get("validation_ok"):
            continue
        out.append(name)
    return out


class DeterministicPlanner:
    def next(self, state: dict, contracts: dict[str, Contract]) -> Decision:
        if state["status"] in ("failed", "done", "rejected"):
            return Decision("done", reason=state["status"])
        el = eligible(state, contracts)
        if any(i["status"] == "open" and i["severity"] == "blocker" for i in state["issues"].values()):
            recheck = [t for t in el if t in RECHECK_TOOLS]
            if recheck:
                return Decision("call", recheck[0], reason="re-check after human fix")
            return Decision("wait_human", reason="open blocker issues")
        if el:
            return Decision("call", el[0])
        if step_key(state, "explain_quote") in state.get("done", {}) and state.get("gate_decision") is None:
            return Decision("open_gate", reason="quote ready for human approval")
        if state.get("gate_decision") == "pending":
            return Decision("wait_approval", reason="waiting at approval gate")
        if state.get("gate_decision") == "rejected":
            return Decision("done", reason="rejected")
        if "render_quote" in state.get("done", {}):
            return Decision("done", reason="quote sent")
        return Decision("wait_human", reason="no eligible tool; needs a person")


class LLMPlanner:
    """Model-assisted planner. The deterministic planner defines what is allowed; the model only
    chooses among eligible tools. Any invalid or failed answer falls back to the rules."""

    def __init__(self, llm, fallback: Planner | None = None):
        self.llm, self.fallback = llm, fallback or DeterministicPlanner()

    def next(self, state: dict, contracts: dict[str, Contract]) -> Decision:
        base = self.fallback.next(state, contracts)
        if base.kind != "call":
            return base
        options = eligible(state, contracts)
        if len(options) == 1:
            return base
        try:
            d = self.llm.complete_json(
                "plan_next", "Pick the next tool for a quote program. Answer {\"tool\": name}.",
                json.dumps({"stage": state.get("stage"), "options": {o: contracts[o].output for o in options}}),
                {"type": "object", "required": ["tool"], "properties": {"tool": {"type": "string", "enum": options}}})
            if d.get("tool") in options:
                return Decision("call", d["tool"], reason="llm planner")
        except Exception:  # noqa: BLE001 - planner failures must never stop the program
            pass
        return base
