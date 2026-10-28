import pytest

from etfwatch.models import Holding


def test_holding_normalizes_and_computes_cost():
    h = Holding(" 0050 ", "1000", "150.5")
    assert h.symbol == "0050.TW"
    assert h.currency == "TWD"
    assert h.cost == pytest.approx(150500)


def test_fractional_us_shares():
    h = Holding("NVDA", 0.25, 120)
    assert h.currency == "USD"
    assert h.cost == pytest.approx(30)


@pytest.mark.parametrize(
    "shares, cost",
    [(0, 10), (-1, 10), (1, -0.01), ("abc", 10), (1, None)],
)
def test_invalid_holding(shares, cost):
    with pytest.raises(ValueError):
        Holding("0050", shares, cost)


from etfwatch.models import COST_MODE_PER_SHARE, COST_MODE_TOTAL, to_avg_cost


def test_to_avg_cost_per_share():
    assert to_avg_cost(55.5, 1945, COST_MODE_PER_SHARE) == 55.5


def test_to_avg_cost_from_total():
    assert to_avg_cost(108714, 1945, COST_MODE_TOTAL) == pytest.approx(108714 / 1945)


def test_to_avg_cost_errors():
    with pytest.raises(ValueError):
        to_avg_cost(100, 0, COST_MODE_TOTAL)
    with pytest.raises(ValueError):
        to_avg_cost(100, 1, "unknown")
