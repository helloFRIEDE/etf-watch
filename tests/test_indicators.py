import pytest

from etfwatch.indicators import (
    analyze,
    max_drawdown,
    moving_average,
    period_return,
    trend_label,
)
from tests.conftest import make_series


def test_period_return():
    s = make_series([100, 105, 110])
    assert period_return(s, 2) == pytest.approx(0.10)
    assert period_return(s, 1) == pytest.approx(110 / 105 - 1)


def test_period_return_not_enough_data():
    assert period_return(make_series([100, 101]), 5) is None


def test_period_return_invalid_days():
    with pytest.raises(ValueError):
        period_return(make_series([1, 2]), 0)


def test_moving_average():
    ma = moving_average(make_series([1, 2, 3, 4]), 2)
    assert ma.isna().iloc[0]
    assert list(ma.iloc[1:]) == [1.5, 2.5, 3.5]


def test_max_drawdown():
    s = make_series([100, 120, 90, 110, 130])
    assert max_drawdown(s) == pytest.approx(90 / 120 - 1)
    assert max_drawdown(make_series([1, 2, 3])) == 0.0
    assert max_drawdown(make_series([])) == 0.0


def test_trend_labels():
    up = make_series(range(1, 81))
    down = make_series(range(80, 0, -1))
    flat = make_series([10] * 80)
    assert trend_label(up) == "多頭排列"
    assert trend_label(down) == "空頭排列"
    assert trend_label(flat) == "盤整"
    assert trend_label(make_series([1] * 10)) == "資料不足"


def test_analyze_report():
    r = analyze(make_series(range(1, 101)))
    assert r.last_price == 100
    assert r.returns["1w"] == pytest.approx(100 / 95 - 1)
    assert r.returns["3m"] == pytest.approx(100 / 37 - 1)
    assert r.trend == "多頭排列"
    assert r.max_drawdown == 0.0


def test_analyze_empty():
    with pytest.raises(ValueError):
        analyze(make_series([]))
