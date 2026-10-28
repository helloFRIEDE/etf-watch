import pytest

from etfwatch.models import Holding
from etfwatch.portfolio import build_positions, summarize

FX = {"TWD": 1.0, "USD": 32.0}


def test_tw_position_pnl():
    [p] = build_positions([Holding("0050", 1000, 150)], {"0050.TW": 180}, FX)
    assert p.cost_twd == pytest.approx(150_000)
    assert p.value_twd == pytest.approx(180_000)
    assert p.pnl_twd == pytest.approx(30_000)
    assert p.pnl_pct == pytest.approx(0.2)


def test_usd_position_converted_to_twd():
    [p] = build_positions([Holding("NVDA", 0.5, 100)], {"NVDA": 120}, FX)
    assert p.market_value == pytest.approx(60)  # USD
    assert p.cost_twd == pytest.approx(0.5 * 100 * 32)
    assert p.value_twd == pytest.approx(0.5 * 120 * 32)
    assert p.pnl_pct == pytest.approx(0.2)


def test_zero_cost_has_no_pct():
    [p] = build_positions([Holding("0050", 10, 0)], {"0050.TW": 100}, FX)
    assert p.pnl_pct is None


def test_missing_price_or_fx():
    with pytest.raises(KeyError):
        build_positions([Holding("0050", 1, 1)], {}, FX)
    with pytest.raises(KeyError):
        build_positions([Holding("NVDA", 1, 1)], {"NVDA": 1}, {"TWD": 1.0})


def test_summary_totals_and_weights():
    holdings = [
        Holding("0050", 1000, 150),  # value 180,000
        Holding("NVDA", 0.5, 100),   # value 0.5*125*32 = 2,000 TWD
        Holding("0050", 100, 170),   # second lot: value 18,000
    ]
    positions = build_positions(holdings, {"0050.TW": 180, "NVDA": 125}, FX)
    s = summarize(positions)
    assert s.total_value_twd == pytest.approx(200_000)
    assert s.total_cost_twd == pytest.approx(150_000 + 1_600 + 17_000)
    assert s.pnl_twd == pytest.approx(200_000 - 168_600)
    assert s.weights["0050.TW"] == pytest.approx(0.99)
    assert s.weights["NVDA"] == pytest.approx(0.01)
    assert sum(s.weights.values()) == pytest.approx(1.0)


def test_empty_portfolio():
    s = summarize([])
    assert s.total_value_twd == 0
    assert s.weights == {}
    assert s.pnl_pct is None


from etfwatch.portfolio import cost_warning


def test_cost_warning_catches_total_typed_as_per_share():
    # Regression: user typed total cost 108,714 into the per-share field.
    [p] = build_positions([Holding("0050", 1945, 108714)], {"0050.TW": 108.65}, FX)
    msg = cost_warning(p)
    assert msg is not None
    assert "55.89" in msg  # suggests the corrected per-share cost


def test_cost_warning_quiet_for_normal_cost():
    [p] = build_positions([Holding("0050", 1945, 55.89)], {"0050.TW": 108.65}, FX)
    assert cost_warning(p) is None
    # a real loss of up to 2/3 is not flagged
    [p] = build_positions([Holding("NVDA", 1, 300)], {"NVDA": 120}, FX)
    assert cost_warning(p) is None
