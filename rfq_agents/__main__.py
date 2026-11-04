"""CLI for the PLA.

  python -m rfq_agents run --rfq data/rfq-1002-incomplete.ttl [--inject-failure TOOL[:N|:fatal|:crash]]
  python -m rfq_agents run --resume RUN_ID [--fix FILE.ttl] [--resolve ISS-ID] [--retry] [--approve|--reject --by NAME]
  python -m rfq_agents status RUN_ID [--json]
  python -m rfq_agents list

Paths given to --rfq/--fix are resolved against the cwd, then the pinned rfq-ontology checkout,
then this repo. The run store is $RFQ_AGENTS_DB (default runs/pla.sqlite).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .llm import client_from_name
from .pla import PLA
from .retry import FailureInjector, InjectedCrash, RetryPolicy
from .store import RunStore


def summary(state: dict) -> str:
    out = [f"run {state['run_id']}  status={state['status']}  stage={state['stage']}  rfq={state.get('rfq_iri', '')}"]
    out.append("tool runs:")
    for r in state["runs"]:
        badge = "AI " if r["agentic"] else "DET"
        retry = f" retryOf={r['retry_of'].split('#')[-1]}" if r.get("retry_of") else ""
        err = f"  ({r['error'][:90]})" if r.get("error") else ""
        out.append(f"  [{badge}] {r['iri'].split('#')[-1]:<22} {r['tool']:<24} #{r['attempt']} {r['status']}{retry}{err}")
    opened = [i for i in state["issues"].values() if i["status"] == "open"]
    out.append(f"issues: {len(opened)} open / {len(state['issues'])} total")
    for i in state["issues"].values():
        out.append(f"  {i['iri'].split('#')[-1]:<16} {i['status']:<9} {i['severity']:<8} {i['assigned_to']:<16} {i['label']}")
    for b in state.get("breaks", []):
        out.append(f"  qty {b['quantity']:>6,}: unit ${b['unit_price']}  total ${float(b['total']):,.2f}")
    if state["status"] == "waiting_approval":
        out.append(f"next: approve with  python -m rfq_agents run --resume {state['run_id']} --approve --by NAME")
    elif state["status"] == "waiting_human":
        out.append(f"next: fix the data with  --resume {state['run_id']} --fix FILE.ttl  (or --resolve ISS-ID)")
    elif state["status"] == "failed":
        out.append(f"next: investigate, then  --resume {state['run_id']} --retry")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="rfq_agents", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--rfq"); r.add_argument("--resume", metavar="RUN_ID"); r.add_argument("--run-id")
    r.add_argument("--inject-failure", action="append", metavar="TOOL[:N|:fatal|:crash]")
    r.add_argument("--fix", metavar="TTL"); r.add_argument("--resolve", metavar="ISSUE_ID")
    r.add_argument("--retry", action="store_true", help="retry a failed step after exhaustion")
    g = r.add_mutually_exclusive_group(); g.add_argument("--approve", action="store_true"); g.add_argument("--reject", action="store_true")
    r.add_argument("--by", default=os.environ.get("USER", "human"))
    r.add_argument("--llm", default=os.environ.get("RFQ_AGENTS_LLM", "canned"), help="canned | workers-ai")
    r.add_argument("--quote-date", help="YYYY-MM-DD; rates effective on this date (default today)")
    r.add_argument("--max-attempts", type=int, default=3); r.add_argument("--base-delay", type=float, default=0.2)
    r.add_argument("--json", action="store_true")
    s = sub.add_parser("status"); s.add_argument("run_id"); s.add_argument("--json", action="store_true")
    sub.add_parser("list")
    for p in (r, s):
        p.add_argument("--db", default=os.environ.get("RFQ_AGENTS_DB", "runs/pla.sqlite"))
    a = ap.parse_args(argv)
    db = getattr(a, "db", os.environ.get("RFQ_AGENTS_DB", "runs/pla.sqlite"))
    store = RunStore(db)

    if a.cmd == "list":
        for rid, st, stage in store.list_runs():
            print(f"{rid}\t{st}\t{stage}")
        return 0
    if a.cmd == "status":
        state, _ = store.load(a.run_id)
        print(json.dumps(state, indent=2) if a.json else summary(state))
        return 0

    pla = PLA(store, llm=client_from_name(a.llm), injector=FailureInjector.parse(a.inject_failure),
              retry=RetryPolicy(max_attempts=a.max_attempts, base_delay=a.base_delay),
              out_dir=os.path.join(os.path.dirname(db) or ".", "out"))
    try:
        rid = _prepare(pla, a, ap)
    except (ValueError, KeyError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    try:
        state = pla.run(rid)
    except InjectedCrash as e:
        print(f"CRASH (injected): {e}. State is checkpointed; resume with --resume {rid}", file=sys.stderr)
        return 3
    print(json.dumps(state, indent=2) if a.json else summary(state))
    return {"failed": 2}.get(state["status"], 0)


def _prepare(pla: PLA, a, ap) -> str:
    if a.resume:
        rid = a.resume
        if a.fix:
            pla.apply_fix(rid, a.fix, by=a.by)
        if a.resolve:
            pla.resolve_issue(rid, a.resolve, by=a.by)
        if a.retry:
            pla.retry_failed(rid)
        if a.approve or a.reject:
            pla.decide(rid, approve=a.approve, by=a.by)
    elif a.rfq:
        rid = pla.start(a.rfq, run_id=a.run_id, quote_date=a.quote_date)
    else:
        ap.error("run needs --rfq or --resume")
    return rid


if __name__ == "__main__":
    raise SystemExit(main())
