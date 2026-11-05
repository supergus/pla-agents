"""Competency questions as tests: each SPARQL query must return the expected rows."""
from run_queries import run


def test_cq1_completeness():
    assert run("cq1-rfq-completeness.rq") == [("RFQ-1002", "Incoterm"), ("RFQ-1002", "material or finish spec")]


def test_cq2_make_vs_buy():
    rows = run("cq2-make-vs-buy.rq")
    assert [(r[1], r[3]) for r in rows] == [("BL-1", "make"), ("BL-2", "make"), ("BL-3", "buy"), ("BL-4", "buy"), ("BL-5", "buy")]


def test_cq3_similarity():
    rows = {r[0]: r for r in run("cq3-similarity-used.rq")}
    assert rows["BL-1"][1:4] == ("LIB-PLT-210", "0.92", "attribute-weighted v1")
    assert rows["BL-5"][1] is None and rows["BL-5"][3] == "manual" and rows["BL-5"][5] == "true"


def test_cq4_cogs_by_break():
    assert [(r[1], r[3], r[4]) for r in run("cq4-cogs-by-break.rq")] == [
        ("100", "60.86", "8016.00"), ("1000", "58.01", "60660.00"), ("10000", "57.72", "587050.00")]


def test_cq5_top_driver_is_weld():
    top = run("cq5-conversion-drivers.rq")[0]
    assert top[2] == "WC-WELD" and float(top[3]) == 11.25


def test_cq6_stale_rates():
    assert run("cq6-stale-rates.rq") == [("Q-1001-A", "A", "WCR-WELD-2025", "WCR-WELD-2026")]


def test_cq7_manual_review():
    assert run("cq7-manual-review.rq") == [("BL-5", "Serial number label", "no library match")]


def test_cq8_freight():
    assert run("cq8-freight-by-incoterm.rq") == [("RFQ-1001", "DAP", "true", "Named place of destination, ready for unloading")]


def test_cq9_open_issues():
    assert run("cq9-open-issues.rq") == [
        ("PRG-1002", "ISS-1002-1", "blocker", "human:estimator", "validate_rfq"),
        ("PRG-1002", "ISS-1002-2", "blocker", "human:estimator", "validate_rfq")]


def test_cq10_tool_runs_by_kind():
    assert run("cq10-tool-runs-by-kind.rq") == [("agentic", "3", "1", "1"), ("deterministic", "2", "0", "0")]


def test_cq11_unapproved_quotes():
    assert run("cq11-unapproved-quotes.rq") == [("Q-1002-A", "awaiting approval", "pending")]


def test_cq12_rfq_line_matches():
    assert run("cq12-rfq-line-matches.rq") == [
        ("RFQ-1002-L1", "BRK-100", "0.91", "llm:llama-3.3-70b (example)", "high", "RUN-1002-4")]
