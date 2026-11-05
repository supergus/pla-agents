"""Offline responses for CannedLLMClient: deterministic stand-ins for Llama 3.3 70B."""
from __future__ import annotations

import json
import re


def _parse(user: str) -> dict:
    if "RFQ-1003" in user:
        return {
            "rfq_id": "RFQ-1003", "revision": "A", "customer": "Northwind Agricultural Equipment",
            "payment_terms": "Net 30", "incoterm": "DAP", "delivery_date": "2027-04-01",
            "drawing": "Drawing BRK-300 rev A", "material_spec": "ASTM A36 steel plate", "finish_spec": None,
            "lines": [{"part": "BRK-300", "description": "Welded mounting bracket, BRK-300",
                       "quantities": [250, 2500]}],
            "confidence": {"incoterm": 0.55, "delivery_date": 0.9, "material_spec": 0.85, "lines": 0.95},
        }
    return {"rfq_id": "RFQ-UNKNOWN", "revision": "A", "customer": "Unknown", "payment_terms": None,
            "incoterm": None, "delivery_date": None, "drawing": None, "material_spec": None, "finish_spec": None,
            "lines": [{"part": "UNKNOWN", "description": "unparsed", "quantities": [1]}],
            "confidence": {"lines": 0.2}}


def _match(user: str) -> dict:
    if re.search(r"BRK-\d+", user):
        return {"product_id": "BRK-100", "score": 0.91, "method": "llm-similarity (canned Llama 3.3 70B stand-in)",
                "rationale": "Same welded bracket family and process route as BRK-100."}
    return {"product_id": "BRK-100", "score": 0.4, "method": "llm-similarity (canned)", "rationale": "weak match"}


def _explain(user: str) -> dict:
    data = json.loads(user[user.index("{"):])
    parts = [f"{b['quantity']:,} units at ${float(b['unit_price']):,.2f} each (total ${float(b['total']):,.2f})"
             for b in data["breaks"]]
    return {"summary": f"Quote {data['quote']}: " + "; ".join(parts) +
            ". The unit price falls with volume because setup cost is spread over more parts."}


DEFAULT_RESPONSES = {"parse_rfq_document": _parse, "match_library_part": _match, "explain_quote": _explain}
