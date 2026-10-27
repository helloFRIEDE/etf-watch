import pytest

from etfwatch.market import DemoProvider, YFinanceProvider
from etfwatch.models import Holding
from etfwatch.service import default_provider, load_snapshot
from tests.conftest import FakeProvider


def test_snapshot_values_portfolio(fake_provider):
    holdings = [Holding("0050", 100, 150), Holding("NVDA", 1, 100), Holding("0050", 10, 160)]
    snap = load_snapshot(holdings, fake_provider)
    assert snap.errors == {}
    assert snap.fx_to_twd["USD"] == 32.5
    # 110 * 185 + 1 * 140 * 32.5
    assert snap.summary.total_value_twd == pytest.approx(110 * 185 + 140 * 32.5)
    # each symbol fetched only once even with two 0050 lots
    fetched = [s for s, _ in fake_provider.calls if s != "TWD=X"]
    assert sorted(fetched) == ["0050.TW", "NVDA"]
    assert set(snap.trends) == {"0050.TW", "NVDA"}


def test_failed_symbol_is_reported_not_fatal(fake_provider):
    snap = load_snapshot([Holding("0050", 1, 1), Holding("9999", 1, 1)], fake_provider)
    assert "9999.TW" in snap.errors
    assert [p.holding.symbol for p in snap.positions] == ["0050.TW"]


def test_fx_failure_keeps_twd_holdings():
    provider = FakeProvider({"0050.TW": [100], "NVDA": [10]})  # no TWD=X
    snap = load_snapshot([Holding("0050", 1, 1), Holding("NVDA", 1, 1)], provider)
    assert "NVDA" in snap.errors
    assert [p.holding.symbol for p in snap.positions] == ["0050.TW"]


def test_empty_holdings(fake_provider):
    snap = load_snapshot([], fake_provider)
    assert snap.positions == []
    assert snap.summary.total_value_twd == 0


def test_default_provider(monkeypatch):
    monkeypatch.setenv("ETFWATCH_DEMO", "1")
    assert isinstance(default_provider(), DemoProvider)
    monkeypatch.delenv("ETFWATCH_DEMO")
    assert isinstance(default_provider(), YFinanceProvider)


def test_demo_provider_is_deterministic():
    a = DemoProvider().history("0050.TW")
    b = DemoProvider().history("0050.TW")
    assert a.equals(b)
    assert len(a) == 126
    assert 30 < DemoProvider().history("TWD=X").iloc[-1] < 35
