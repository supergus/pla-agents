"""Agentic tools: schema + SHACL gates, low confidence -> Issue, and the Workers AI client (offline)."""
import io
import json
import urllib.error

import pytest

from conftest import QUOTE_DATE, open_issues, runs_of
from rfq_agents.llm import CannedLLMClient, WorkersAIClient, parse_workers_ai_payload
from rfq_agents.planner import DeterministicPlanner, LLMPlanner
from rfq_agents.retry import FatalError, RetryableError


def test_email_intake_low_confidence_becomes_issue(make_pla):
    pla = make_pla()
    rid = pla.start("data/rfq-1003-email.txt", run_id="1003-a", quote_date=QUOTE_DATE)
    s = pla.run(rid)
    labels = {i["label"] for i in open_issues(s)}
    assert any("low-confidence incoterm" in l for l in labels)  # not written as a fact...
    assert "RFQ-1003: missing Incoterm" in labels                # ...so SHACL also blocks it
    assert s["status"] == "waiting_human"


def test_bad_llm_output_is_rejected_by_schema(make_pla):
    bad = {"rfq_id": "RFQ-9", "incoterm": "XYZ", "lines": [{"part": "P", "quantities": [1]}], "confidence": {}}
    pla = make_pla(llm=CannedLLMClient({"parse_rfq_document": bad}), max_attempts=2)
    rid = pla.start("data/rfq-1003-email.txt", run_id="1003-b", quote_date=QUOTE_DATE)
    s = pla.run(rid)
    assert [r["status"] for r in runs_of(s, "parse_rfq_document")] == ["failed", "failed"]
    assert "SchemaError" in runs_of(s, "parse_rfq_document")[0]["error"]
    assert s["status"] == "failed"
    _, g = pla.store.load(rid)
    from rfq_agents.ontology import RFQ
    assert (None, RFQ.identifier, None) not in g  # nothing from the bad proposal was written


def test_shacl_gate_rejects_nonpositive_quantity(make_pla):
    bad = {"rfq_id": "RFQ-9", "lines": [{"part": "P", "quantities": [0]}], "confidence": {}}
    pla = make_pla(llm=CannedLLMClient({"parse_rfq_document": bad}), max_attempts=1)
    rid = pla.start("data/rfq-1003-email.txt", run_id="1003-c", quote_date=QUOTE_DATE)
    s = pla.run(rid)
    assert s["status"] == "failed" and "SchemaError" in runs_of(s, "parse_rfq_document")[0]["error"]


def test_low_score_match_is_issue_not_fact(make_pla):
    weak = {"product_id": "BRK-100", "score": 0.5, "method": "llm-similarity"}
    pla = make_pla(llm=CannedLLMClient({"match_library_part": weak}))
    rid = pla.start("data/rfq-1002-incomplete.ttl", run_id="1002-w", quote_date=QUOTE_DATE)
    pla.run(rid); pla.apply_fix(rid, "data/fixes/rfq-1002-fix.ttl")
    s = pla.run(rid)
    assert s["status"] == "waiting_human"
    assert any("scored 0.5" in i["label"] for i in open_issues(s, "blocker"))
    assert not runs_of(s, "cost_quote")


def test_hallucinated_product_is_rejected(make_pla):
    pla = make_pla(llm=CannedLLMClient({"match_library_part": {"product_id": "NOPE", "score": 0.99, "method": "x"}}),
                   max_attempts=1)
    rid = pla.start("data/rfq-1002-incomplete.ttl", run_id="1002-h", quote_date=QUOTE_DATE)
    pla.run(rid); pla.apply_fix(rid, "data/fixes/rfq-1002-fix.ttl")
    s = pla.run(rid)
    assert s["status"] == "failed" and "unknown product" in runs_of(s, "match_library_part")[0]["error"]


def test_explain_cannot_invent_numbers(make_pla):
    pla = make_pla(llm=CannedLLMClient({"explain_quote": {"summary": "Great deal: only $49.99 per unit!"}}),
                   max_attempts=1)
    rid = pla.start("data/rfq-1001.ttl", run_id="1001-e", quote_date=QUOTE_DATE)
    s = pla.run(rid)
    assert s["status"] == "failed" and "49.99" in runs_of(s, "explain_quote")[0]["error"]


class FakeResp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_workers_ai_client_request_and_parsing(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct123")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok-test")
    seen = {}

    def opener(req, timeout):
        seen.update(url=req.full_url, auth=req.get_header("Authorization"), body=json.loads(req.data))
        return FakeResp(json.dumps({"success": True, "result": {"response": {"summary": "ok ok ok ok"}}}).encode())

    c = WorkersAIClient(opener=opener)
    out = c.complete_json("explain_quote", "sys", "user", {"type": "object"})
    assert out == {"summary": "ok ok ok ok"}
    assert seen["url"] == "https://api.cloudflare.com/client/v4/accounts/acct123/ai/run/@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    assert seen["auth"] == "Bearer tok-test"
    assert seen["body"]["response_format"]["type"] == "json_schema"
    assert parse_workers_ai_payload({"result": {"response": '```json\n{"a": 1}\n```'}}) == {"a": 1}
    with pytest.raises(RetryableError):
        parse_workers_ai_payload({"result": {"response": "not json"}})


def test_workers_ai_client_error_mapping(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    with pytest.raises(FatalError):
        WorkersAIClient()

    def err(code):
        def opener(req, timeout):
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, None)
        return WorkersAIClient(account_id="a", api_token="t", opener=opener)
    with pytest.raises(RetryableError):
        err(429).complete_json("t", "s", "u", {})
    with pytest.raises(RetryableError):
        err(503).complete_json("t", "s", "u", {})
    with pytest.raises(FatalError):
        err(400).complete_json("t", "s", "u", {})


def test_llm_planner_can_only_choose_eligible_tools(make_pla):
    picky = CannedLLMClient({"plan_next": {"tool": "render_quote"}})  # tries to skip the gate
    pla = make_pla(planner=LLMPlanner(picky))
    rid = pla.start("data/rfq-1001.ttl", run_id="1001-p", quote_date=QUOTE_DATE)
    s = pla.run(rid)
    assert s["status"] == "waiting_approval" and not runs_of(s, "render_quote")
    assert isinstance(LLMPlanner(picky).fallback, DeterministicPlanner)
