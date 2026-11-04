"""Crash and resume from the persisted run store."""
import pytest

from conftest import QUOTE_DATE, open_issues, runs_of
from rfq_agents.retry import FailureInjector, InjectedCrash


def test_crash_after_step_resumes_without_redoing_it(make_pla):
    pla = make_pla(injector=FailureInjector(crash_after="cost_quote"))
    rid = pla.start("data/rfq-1001.ttl", run_id="1001-c", quote_date=QUOTE_DATE)
    with pytest.raises(InjectedCrash):
        pla.run(rid)
    pla.store.close()

    fresh = make_pla()  # new process: new store connection, new PLA, no memory
    s = fresh.run(rid)
    assert s["status"] == "waiting_approval"
    for tool in ("parse_rfq_document", "validate_rfq", "match_library_part", "explode_bom", "cost_quote", "explain_quote"):
        assert len(runs_of(s, tool)) == 1, tool
    assert [b["unit_price"] for b in s["breaks"]] == ["60.86", "58.01", "57.72"]


def test_crash_mid_step_is_recorded_and_retried(make_pla):
    inj = FailureInjector(crash_before="match_library_part")
    pla = make_pla(injector=inj)
    rid = pla.start("data/rfq-1001.ttl", run_id="1001-m", quote_date=QUOTE_DATE)
    with pytest.raises(InjectedCrash):
        pla.run(rid)
    state, _ = pla.store.load(rid)
    assert state["inflight"]["tool"] == "match_library_part"  # the checkpoint saw the step start

    s = make_pla().run(rid)
    runs = runs_of(s, "match_library_part")
    assert [(r["attempt"], r["status"]) for r in runs] == [(1, "failed"), (2, "succeeded")]
    assert runs[0]["error"].startswith("interrupted") and runs[1]["retry_of"] == runs[0]["iri"]
    assert s["status"] == "waiting_approval" and not open_issues(s)


def test_checkpoint_after_every_step(make_pla):
    pla = make_pla()
    rid = pla.start("data/rfq-1001.ttl", run_id="1001-k", quote_date=QUOTE_DATE)
    s = pla.run(rid)
    labels = pla.store.checkpoints(rid)
    for r in s["runs"]:
        assert f"start {r['tool']}#{r['attempt']}" in labels
        assert f"done {r['tool']}" in labels
    assert labels[-1] == "gate opened" and s["version"] == len(labels)


def test_resume_between_processes_at_gates(make_pla):
    rid = make_pla().start("data/rfq-1002-incomplete.ttl", run_id="1002-p", quote_date=QUOTE_DATE)
    assert make_pla().run(rid)["status"] == "waiting_human"
    make_pla().apply_fix(rid, "data/fixes/rfq-1002-fix.ttl")
    assert make_pla().run(rid)["status"] == "waiting_approval"
    make_pla().decide(rid, True, "chris")
    assert make_pla().run(rid)["status"] == "done"
