"""The Program Lifecycle Agent (PLA): a small, durable orchestrator loop.

Each program's state lives in two places, saved together after every step (store.RunStore):
- an RDF graph that conforms to the ontology's PLA module (ontology/ontology/rfq-pla.ttl) (Program, Task, Issue, ToolRun,
  ApprovalGate) plus the RFQ facts the tools wrote, and
- a JSON state document (status, idempotency ledger, in-flight step, retry bookkeeping).

The loop: ask the Planner for the next action -> call the tool with retries -> record every attempt
as a ToolRun -> raise/resolve Issues -> checkpoint. It stops for people: open blocker issues
(waiting_human) and the ApprovalGate before render_quote (waiting_approval).
"""
from __future__ import annotations

import datetime as dt
import json
import secrets
from pathlib import Path
from typing import Callable

from pyshacl import validate as shacl_validate
from rdflib import RDF, RDFS, Graph, Literal, URIRef
from rdflib.namespace import OWL, XSD

from .contracts import Contract, load_contracts
from .llm import CannedLLMClient
from .ontology import EX, PROV, RFQ, bind, context_graph, load_files, resolve_input, shapes_path
from .planner import DeterministicPlanner, Planner, step_key
from .retry import FailureInjector, InjectedCrash, RetryPolicy, idempotency_key, is_retryable
from .store import RunStore
from .tools import REGISTRY, IssueSpec, ToolContext, ToolResult

TASKS = {"intake": "PLA", "validate": "PLA", "match": "PLA", "cost": "PLA", "send": "human:sales"}


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


class PLA:
    def __init__(self, store: RunStore, *, llm=None, planner: Planner | None = None,
                 retry: RetryPolicy | None = None, injector: FailureInjector | None = None,
                 clock: Callable[[], dt.datetime] = utcnow, out_dir: str | Path = "runs/out",
                 check_records: bool = True):
        self.store = store
        self.llm = llm or CannedLLMClient()
        self.planner = planner or DeterministicPlanner()
        self.retry = retry or RetryPolicy()
        self.injector = injector or FailureInjector()
        self.clock = clock
        self.out_dir = Path(out_dir)
        self.contracts: dict[str, Contract] = load_contracts()
        self.context = context_graph()
        self.check_records = check_records
        missing = set(self.contracts) ^ set(REGISTRY)
        if missing:
            raise RuntimeError(f"tool registry and contracts disagree: {sorted(missing)}")

    # ------------------------------------------------------------------ lifecycle
    def start(self, rfq_path: str, run_id: str | None = None, quote_date: str | None = None) -> str:
        resolve_input(rfq_path)  # fail fast if missing
        stem = Path(rfq_path).stem.split("-")[1] if "-" in Path(rfq_path).stem else "X"
        run_id = run_id or f"{stem}-{secrets.token_hex(3)}"
        prg = EX[f"PRG-{run_id}"]
        state = {
            "run_id": run_id, "rfq_path": rfq_path, "program_iri": str(prg), "rfq_iri": None,
            "quote_date": quote_date or self.clock().date().isoformat(), "status": "running", "stage": "intake",
            "rfq_version": 1, "done": {}, "issues": {}, "runs": [], "seq": {"run": 0, "issue": 0, "fix": 0},
            "attempts": {}, "last_failed": {}, "inflight": None, "gate_decision": None, "events": [],
        }
        g = bind(Graph())
        g.add((prg, RDF.type, RFQ.Program)); g.add((prg, RDFS.label, Literal(f"Program {run_id}")))
        g.add((prg, RFQ.programStage, Literal("intake")))
        for stage, owner in TASKS.items():
            t = EX[f"TASK-{run_id}-{stage}"]
            g.add((prg, RFQ.hasTask, t)); g.add((t, RDF.type, RFQ.Task))
            g.add((t, RDFS.label, Literal(f"{stage.capitalize()} ({run_id})")))
            g.add((t, RFQ.taskStatus, Literal("pending"))); g.add((t, RFQ.assignedTo, Literal(owner)))
            for c in self.contracts.values():
                if c.stage == stage:
                    g.add((t, RFQ.usesTool, c.iri))
        self._event(state, "started", rfq=rfq_path)
        self.store.save(run_id, state, g, "start")
        return run_id

    def run(self, run_id: str, max_steps: int = 100) -> dict:
        state, g = self.store.load(run_id)
        self._recover_inflight(state, g)
        for _ in range(max_steps):
            d = self.planner.next(state, self.contracts)
            if d.kind == "call":
                if state["status"] != "running":
                    state["status"] = "running"
                if not self._execute(state, g, d.tool):
                    break
            elif d.kind == "open_gate":
                self._open_gate(state, g)
            elif d.kind in ("wait_human", "wait_approval"):
                new = "waiting_human" if d.kind == "wait_human" else "waiting_approval"
                if state["status"] != new:
                    state["status"] = new
                    if d.kind == "wait_human":
                        self._set_task(g, state, "validate" if any(k.startswith("shacl:") and v["status"] == "open"
                                                                   for k, v in state["issues"].items()) else state["stage"], "blocked")
                    self._event(state, new, reason=d.reason)
                    self._save(state, g, new)
                break
            else:
                if state["status"] == "running":
                    state["status"] = "done"
                    self._event(state, "done", reason=d.reason)
                    self._save(state, g, "done")
                break
        return state

    # ------------------------------------------------------------------ human inputs
    def apply_fix(self, run_id: str, fix_path: str, by: str = "human:estimator") -> dict:
        state, g = self.store.load(run_id)
        if state["gate_decision"] is not None:
            raise ValueError("RFQ data is frozen once the approval gate is open; start a new revision")
        fix = bind(Graph()); fix.parse(resolve_input(fix_path), format="turtle")
        for s in list(fix.subjects(RDF.type, OWL.Ontology)):
            fix.remove((s, None, None))
        g += fix
        state["rfq_version"] += 1
        state["seq"]["fix"] += 1
        f = EX[f"FIX-{run_id}-{state['seq']['fix']}"]
        g.add((f, RDF.type, RFQ.HumanFix)); g.add((f, RDFS.label, Literal(f"Human fix {state['seq']['fix']} from {Path(fix_path).name}")))
        g.add((f, RFQ.appliedBy, Literal(by))); g.add((f, PROV.generatedAtTime, self._now()))
        g.add((URIRef(state["program_iri"]), RFQ.hasFix, f))
        state["status"] = "running"
        self._event(state, "fix_applied", file=fix_path, by=by, triples=len(fix), rfq_version=state["rfq_version"])
        self._save(state, g, f"fix {state['seq']['fix']}")
        return state

    def resolve_issue(self, run_id: str, issue_id: str, by: str = "human") -> dict:
        state, g = self.store.load(run_id)
        for k, v in state["issues"].items():
            if v["iri"].endswith(issue_id) and v["status"] == "open":
                self._set_issue_status(state, g, k, "resolved")
                self._event(state, "issue_resolved", issue=issue_id, by=by)
                state["status"] = "running"
                self._save(state, g, f"resolve {issue_id}")
                return state
        raise KeyError(f"no open issue {issue_id}")

    def retry_failed(self, run_id: str) -> dict:
        state, g = self.store.load(run_id)
        if state["status"] != "failed":
            return state
        for k, v in state["issues"].items():
            if k.startswith("exhausted:") and v["status"] == "open":
                self._set_issue_status(state, g, k, "resolved")
        state["status"] = "running"
        self._event(state, "retry_requested")
        self._save(state, g, "retry requested")
        return state

    def decide(self, run_id: str, approve: bool, by: str) -> dict:
        state, g = self.store.load(run_id)
        if state["gate_decision"] != "pending":
            raise ValueError(f"no pending approval gate (gate is {state['gate_decision']})")
        gate, quote = EX[f"GATE-{run_id}"], URIRef(state["quote_iri"])
        decision = "approved" if approve else "rejected"
        self._set1(g, gate, RFQ.gateDecision, Literal(decision))
        g.add((gate, RFQ.approvedBy if approve else RFQ.rejectedBy, Literal(by)))
        g.add((gate, RFQ.decidedAtTime, self._now()))
        state["gate_decision"] = decision
        if approve:
            state["status"] = "running"; state["stage"] = "send"
            self._set1(g, URIRef(state["program_iri"]), RFQ.programStage, Literal("send"))
            self._set_task(g, state, "send", "pending", owner="PLA")
        else:
            state["status"] = "rejected"
            self._set1(g, quote, RFQ.quoteStatus, Literal("draft"))
        self._event(state, f"gate_{decision}", by=by)
        self._save(state, g, f"gate {decision}")
        return state

    # ------------------------------------------------------------------ internals
    def _execute(self, state: dict, g: Graph, name: str) -> bool:
        c = self.contracts[name]
        key = step_key(state, name)
        attempt = state["attempts"].get(key, 0) + 1
        first = attempt
        prev = state["last_failed"].get(key)
        if state["stage"] != c.stage:
            state["stage"] = c.stage
            self._set1(g, URIRef(state["program_iri"]), RFQ.programStage, Literal(c.stage))
        self._set_task(g, state, c.stage, "running")
        while True:
            inputs = {"rfq_version": state["rfq_version"], "rfq": state.get("rfq_iri"), "tool": name}
            idem = idempotency_key(state["run_id"], key, inputs)
            run = self._new_run(state, g, c, attempt, prev, idem)
            state["inflight"] = {"tool": name, "key": key, "run": str(run), "attempt": attempt}
            self._save(state, g, f"start {name}#{attempt}")
            ctx = ToolContext(state["run_id"], state, g, self.llm, self.out_dir, self.context)
            try:
                self.injector.before(name, attempt)
                result = REGISTRY[name].fn(ctx)
            except InjectedCrash:
                raise
            except Exception as e:  # noqa: BLE001 - every failure is recorded, then classified
                retryable = is_retryable(e)
                self._finish_run(state, g, run, "failed", error=f"{type(e).__name__}: {e}")
                state["attempts"][key] = attempt
                state["last_failed"][key] = str(run)
                state["inflight"] = None
                self._raise_issue(state, g, IssueSpec(f"fail:{key}:{attempt}", f"{name} attempt {attempt} failed: "
                                                      f"{str(e).splitlines()[0][:160]}", "warning", "PLA"), run)
                if retryable and attempt - first + 1 < self.retry.max_attempts:
                    delay = self.retry.delay(attempt)
                    self._event(state, "retry_scheduled", tool=name, attempt=attempt + 1, delay_s=round(delay, 3))
                    self._save(state, g, f"failed {name}#{attempt}")
                    (self.retry.sleep or __import__("time").sleep)(delay)
                    prev, attempt = str(run), attempt + 1
                    continue
                why = "retries exhausted" if retryable else "fatal error"
                self._raise_issue(state, g, IssueSpec(f"exhausted:{key}", f"{name} stopped after {attempt - first + 1} "
                                                      f"attempt(s) ({why}): {str(e).splitlines()[0][:160]}",
                                                      "blocker", "human:operator"), run)
                self._set_task(g, state, c.stage, "failed")
                state["status"] = "failed"
                self._event(state, "step_failed", tool=name, reason=why)
                self._save(state, g, f"failed {name}")
                return False
            self._apply(state, g, run, key, result)
            self._finish_run(state, g, run, "succeeded", outputs=result.outputs)
            state["done"][key] = {"run": str(run), "idempotency_key": idem}
            state["inflight"] = None
            for k in [k for k in state["issues"] if k.startswith(f"fail:{key}:")]:
                if state["issues"][k]["status"] == "open":
                    self._set_issue_status(state, g, k, "resolved")
            self._set_task(g, state, c.stage, "done")
            if self.check_records:
                self._check_records(g)
            self._save(state, g, f"done {name}")
            self.injector.after(name)
            return True

    def _apply(self, state: dict, g: Graph, run: URIRef, key: str, r: ToolResult) -> None:
        for s, p, o in r.remove:
            g.remove((s, p, o))
        g += r.add
        state.update(r.state)
        if "rfq_iri" in r.state:
            self._set1(g, URIRef(state["program_iri"]), RFQ.programForRFQ, URIRef(r.state["rfq_iri"]))
        for n in r.inputs:
            g.add((run, RFQ.toolRunInput, n))
        for n in r.output_nodes:
            g.add((run, RFQ.toolRunOutput, n))
        raised = set()
        for spec in r.issues:
            raised.add(spec.key)
            self._raise_issue(state, g, spec, run)
        if r.resolves_prefix:
            for k, v in state["issues"].items():
                if k.startswith(r.resolves_prefix) and k not in raised and v["status"] == "open":
                    self._set_issue_status(state, g, k, "resolved")

    def _new_run(self, state, g, c: Contract, attempt: int, retry_of: str | None, idem: str) -> URIRef:
        state["seq"]["run"] += 1
        run = EX[f"RUN-{state['run_id']}-{state['seq']['run']}"]
        g.add((run, RDF.type, RFQ.ToolRun))
        g.add((run, RDFS.label, Literal(f"{c.name} run {attempt}" + (" (retry)" if retry_of else ""))))
        g.add((run, RFQ.toolRunOf, c.iri)); g.add((run, RFQ.runInProgram, URIRef(state["program_iri"])))
        g.add((run, RFQ.forTask, EX[f"TASK-{state['run_id']}-{c.stage}"]))
        g.add((run, RFQ.attemptNumber, Literal(attempt, datatype=XSD.integer)))
        g.add((run, RFQ.runStatus, Literal("running")))
        g.add((run, PROV.startedAtTime, self._now()))
        g.add((run, RFQ.idempotencyKey, Literal(idem)))
        if retry_of:
            g.add((run, RFQ.retryOf, URIRef(retry_of)))
        state["runs"].append({"iri": str(run), "tool": c.name, "agentic": c.agentic, "attempt": attempt,
                              "retry_of": retry_of, "status": "running", "started": str(self._now()),
                              "idempotency_key": idem})
        return run

    def _finish_run(self, state, g, run: URIRef, status: str, outputs: dict | None = None, error: str | None = None):
        self._set1(g, run, RFQ.runStatus, Literal(status))
        g.add((run, PROV.endedAtTime, self._now()))
        rec = next(r for r in state["runs"] if r["iri"] == str(run))
        rec.update(status=status, ended=str(self._now()))
        if outputs is not None:
            rec["outputs"] = outputs
            g.add((run, RFQ.outputSummary, Literal(json.dumps(outputs, sort_keys=True, default=str)[:4000])))
        if error:
            rec["error"] = error
            g.add((run, RFQ.runError, Literal(error[:1000])))

    def _recover_inflight(self, state: dict, g: Graph) -> None:
        """A step that was running when the process died: record it as failed and let the retry logic
        start a new attempt that points back to it (retryOf)."""
        inf = state.get("inflight")
        if not inf:
            return
        run = URIRef(inf["run"])
        self._finish_run(state, g, run, "failed", error="interrupted: process stopped mid-step")
        state["attempts"][inf["key"]] = inf["attempt"]
        state["last_failed"][inf["key"]] = inf["run"]
        state["inflight"] = None
        self._raise_issue(state, g, IssueSpec(f"fail:{inf['key']}:{inf['attempt']}",
                                              f"{inf['tool']} attempt {inf['attempt']} interrupted (crash); resuming",
                                              "warning", "PLA"), run)
        self._event(state, "recovered_inflight", tool=inf["tool"], attempt=inf["attempt"])
        self._save(state, g, f"recovered {inf['tool']}")

    def _open_gate(self, state: dict, g: Graph) -> None:
        rid = state["run_id"]
        gate, quote, prg = EX[f"GATE-{rid}"], URIRef(state["quote_iri"]), URIRef(state["program_iri"])
        g.add((gate, RDF.type, RFQ.ApprovalGate)); g.add((gate, RDFS.label, Literal(f"Approval gate for {quote.split('#')[-1]}")))
        g.add((gate, RFQ.gateForQuote, quote)); g.add((gate, RFQ.gateDecision, Literal("pending")))
        g.add((prg, RFQ.hasApprovalGate, gate))
        self._set1(g, quote, RFQ.quoteStatus, Literal("awaiting approval"))
        self._set1(g, prg, RFQ.programStage, Literal("approve"))
        self._set_task(g, state, "send", "blocked")
        state.update(gate_decision="pending", stage="approve", status="waiting_approval")
        self._event(state, "gate_opened", quote=quote.split("#")[-1])
        self._save(state, g, "gate opened")

    def _raise_issue(self, state, g, spec: IssueSpec, run: URIRef) -> None:
        cur = state["issues"].get(spec.key)
        if cur and cur["status"] == "open":
            g.add((URIRef(cur["iri"]), RFQ.raisedBy, run))
            return
        if cur:  # re-opened
            iri = URIRef(cur["iri"])
            self._set_issue_status(state, g, spec.key, "open")
            g.add((iri, RFQ.raisedBy, run))
            return
        state["seq"]["issue"] += 1
        iri = EX[f"ISS-{state['run_id']}-{state['seq']['issue']}"]
        g.add((URIRef(state["program_iri"]), RFQ.hasIssue, iri))
        g.add((iri, RDF.type, RFQ.Issue)); g.add((iri, RDFS.label, Literal(spec.label)))
        g.add((iri, RFQ.issueSeverity, Literal(spec.severity))); g.add((iri, RFQ.issueStatus, Literal("open")))
        g.add((iri, RFQ.raisedBy, run)); g.add((iri, RFQ.assignedTo, Literal(spec.assigned_to)))
        state["issues"][spec.key] = {"iri": str(iri), "label": spec.label, "severity": spec.severity,
                                     "status": "open", "assigned_to": spec.assigned_to}

    def _set_issue_status(self, state, g, key: str, status: str) -> None:
        state["issues"][key]["status"] = status
        self._set1(g, URIRef(state["issues"][key]["iri"]), RFQ.issueStatus, Literal(status))

    def _set_task(self, g, state, stage: str, status: str, owner: str | None = None) -> None:
        if stage not in TASKS:
            return
        t = EX[f"TASK-{state['run_id']}-{stage}"]
        self._set1(g, t, RFQ.taskStatus, Literal(status))
        if owner:
            self._set1(g, t, RFQ.assignedTo, Literal(owner))

    def _check_records(self, g: Graph) -> None:
        view = bind(Graph()); view += self.context; view += g
        ok, _, text = shacl_validate(view, shacl_graph=load_files(shapes_path("pla-shapes.ttl")), inference="none",
                                     advanced=True)
        if not ok:
            raise RuntimeError("PLA records violate shapes/pla-shapes.ttl:\n" + text)

    @staticmethod
    def _set1(g: Graph, s, p, o) -> None:
        g.remove((s, p, None)); g.add((s, p, o))

    def _now(self) -> Literal:
        return Literal(self.clock().isoformat(), datatype=XSD.dateTime)

    def _event(self, state, kind: str, **kw) -> None:
        state["events"].append({"at": self.clock().isoformat(), "event": kind, **kw})

    def _save(self, state, g, label: str) -> None:
        self.store.save(state["run_id"], state, g, label)
