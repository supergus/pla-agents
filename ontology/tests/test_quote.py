"""Worked example (docs/worked-example.md): exact numbers for RFQ-1001 line 1, quote Q-1001-B."""
from decimal import Decimal as D

import pytest

from quote import compute
from rfqlib import EX, all_data


@pytest.fixture(scope="module")
def breaks():
    return {p.quantity: p for p in compute(all_data(), EX["RFQ-1001-L1"], EX["Q-1001-B"])}


def test_material_is_quantity_independent(breaks):
    # 1x4.00x1.05 + 2x1.50x1.05 + 4x0.12x1.02 + 2x0.85x1.00 + 1x0.25x1.10
    for p in breaks.values():
        assert p.material == D("9.8146")


@pytest.mark.parametrize("qty,conv,cogs,unit,total", [
    (100,   "27.60",   "37.4146", "60.86", "8016.00"),
    (1000,  "25.845",  "35.6596", "58.01", "60660.00"),
    (10000, "25.6695", "35.4841", "57.72", "587050.00"),
])
def test_price_breaks(breaks, qty, conv, cogs, unit, total):
    p = breaks[qty]
    assert p.conversion == D(conv)
    assert p.cogs == D(cogs)
    assert p.loaded == p.cogs * D("1.22")
    assert p.unit_price == D(unit)
    assert p.nre == D("1850.00")
    assert p.freight == D("0.80") * qty          # DAP: seller pays freight
    assert p.total == D(total)


def test_margin_is_on_price_not_markup(breaks):
    p = breaks[1000]
    margin = (p.unit_price - p.loaded) / p.unit_price
    assert abs(margin - D("0.25")) < D("0.0001")


def test_uses_current_weld_rate(breaks):
    assert EX["WCR-WELD-2026"] in breaks[100].derived_from["conversion"]
    assert EX["WCR-WELD-2025"] not in breaks[100].derived_from["conversion"]
