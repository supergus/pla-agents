"""Retries with backoff, recovery, max-attempt exhaustion, fatal errors."""
import random

import pytest

from conftest import QUOTE_DATE, open_issues, runs_of
from rfq_agents.retry import FailureInjector, FatalError, RetryableError, RetryPolicy, idempotency_key, is_retryable


def test_backoff_is_exponential_capped_and_jittered():
    p = RetryPolicy(base_delay=0.5, max_delay=4, jitter=False)
    assert [p.delay(a) for a in range(1, 6)] == [0.5, 1, 2, 4, 4]
    j = RetryPolicy(base_delay=0.5, max_delay=4, rng=random.Random(1))
    for a in range(1, 6):
        assert 0 <= j.delay(a) <= min(4, 0.5 * 2 ** (a - 1))


def test_error_classification_and_idempotency_keys():
    assert is_retryable(RetryableError()) and is_retryable(TimeoutError()) and is_retryable(ConnectionError())
    assert not is_retryable(FatalError()) and not is_retryable(ValueError())
    assert idempotency_key("r", "s", {"a": 1, "b": 2}) == idempotency_key("r", "s", {"b": 2, "a": 1})
    assert idempotency_key("r", "s", {"a": 1}) != idempotency_key("r", "s", {"a": 2})


def test_transient_failures_are_retried_and_recovered(make_pla, sleeps):
    pla = make_pla(injector=FailureInjector(fail={"match_library_part": 2}))
    rid = pla.start("data/rfq-1001.ttl", run_id="1001-r", quote_date=QUOTE_DATE)
    s = pla.run(rid)
    runs = runs_of(s, "match_library_part")
    assert [(r["attempt"], r["status"]) for r in runs] == [(1, "failed"), (2, "failed"), (3, "succeeded")]
    assert runs[0]["retry_of"] is None
    assert runs[1]["retry_of"] == runs[0]["iri"] and runs[2]["retry_of"] == runs[1]["iri"]
    assert len(sleeps) == 2 and 0 <= sleeps[0] <= 0.5 and 0 <= sleeps[1] <= 1.0
    warn = [i for k, i in s["issues"].items() if k.startswith("fail:")]
    assert len(warn) == 2 and all(i["status"] == "resolved" and i["severity"] == "warning" for i in warn)
    assert s["status"] == "waiting_approval"


def test_max_attempts_exhaustion_creates_blocker_issue(make_pla):
    pla = make_pla(injector=FailureInjector(fail={"cost_quote": 5}), max_attempts=3)
    rid = pla.start("data/rfq-1001.ttl", run_id="1001-x", quote_date=QUOTE_DATE)
    s = pla.run(rid)
    assert s["status"] == "failed"
    assert [r["status"] for r in runs_of(s, "cost_quote")] == ["failed"] * 3
    blockers = open_issues(s, "blocker")
    assert len(blockers) == 1 and blockers[0]["assigned_to"] == "human:operator"
    assert "retries exhausted" in blockers[0]["label"]
    _, g = pla.store.load(rid)
    from rfq_agents.ontology import EX, RFQ
    assert str(g.value(EX["TASK-1001-x-cost"], RFQ.taskStatus)) == "failed"

    # An operator asks for a retry; the remaining injected failures (2) are absorbed by retries.
    pla.retry_failed(rid)
    s = pla.run(rid)
    assert s["status"] == "waiting_approval"
    assert [r["attempt"] for r in runs_of(s, "cost_quote")] == [1, 2, 3, 4, 5, 6]
    assert not open_issues(s, "blocker")


def test_fatal_error_is_not_retried(make_pla, sleeps):
    pla = make_pla(injector=FailureInjector(fail={"explode_bom": 1}, fatal={"explode_bom"}))
    rid = pla.start("data/rfq-1001.ttl", run_id="1001-f", quote_date=QUOTE_DATE)
    s = pla.run(rid)
    assert s["status"] == "failed" and len(runs_of(s, "explode_bom")) == 1 and sleeps == []
    assert "fatal error" in open_issues(s, "blocker")[0]["label"]


def test_cli_parse_of_injection_specs():
    inj = FailureInjector.parse(["cost_quote", "match_library_part:2", "explode_bom:fatal", "validate_rfq:crash"])
    assert inj.fail == {"cost_quote": 1, "match_library_part": 2, "explode_bom": 1}
    assert inj.fatal == {"explode_bom"} and inj.crash_after == "validate_rfq"
    with pytest.raises(RetryableError):
        inj.before("cost_quote", 1)
