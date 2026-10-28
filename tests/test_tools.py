from datetime import datetime, timezone
from pathlib import Path

import pytest

from etfwatch import tools
from etfwatch.models import Holding
from etfwatch.news import NewsError, NewsItem
from etfwatch.storage import PROJECT_ROOT, HoldingStore, default_db_path
from tests.conftest import FakeProvider


@pytest.fixture
def store():
    s = HoldingStore(":memory:")
    yield s
    s.close()


class FakeNews:
    def headlines(self, symbol, limit=5):
        if symbol == "BAD":
            raise NewsError("down")
        when = datetime(2026, 10, 27, tzinfo=timezone.utc)
        return [NewsItem(f"{symbol} 新聞 {i}", "來源", when, "https://x") for i in range(limit)]


def test_list_holdings(store):
    store.add(Holding("0050", 100, 55.5, note="定期定額"))
    [h] = tools.list_holdings(store)
    assert h == {
        "id": 1, "symbol": "0050.TW", "code": "0050", "shares": 100.0,
        "avg_cost": 55.5, "currency": "TWD", "note": "定期定額",
    }


def test_portfolio_summary_merges_lots(store, fake_provider):
    store.add(Holding("0050", 100, 150))
    store.add(Holding("0050", 10, 160))
    store.add(Holding("NVDA", 1, 100))
    out = tools.portfolio_summary(store, fake_provider)
    assert out["total_value"] == round(110 * 185 + 140 * 32.5)
    assert out["usd_twd"] == 32.5
    codes = [h["code"] for h in out["holdings"]]
    assert codes == ["0050", "NVDA"]
    tw = out["holdings"][0]
    assert tw["shares"] == 110
    assert tw["cost_twd"] == 100 * 150 + 10 * 160
    assert sum(h["weight"] for h in out["holdings"]) == pytest.approx(1.0, abs=1e-3)
    assert out["warnings"] == []
    assert "不構成投資建議" in out["disclaimer"]


def test_portfolio_summary_reports_bad_cost_and_errors(store):
    provider = FakeProvider({"0050.TW": [100.0]})
    store.add(Holding("0050", 1000, 50000))
    store.add(Holding("9999", 1, 1))
    out = tools.portfolio_summary(store, provider)
    assert "9999.TW" in out["errors"]
    assert len(out["warnings"]) == 1


def test_analyze_symbol(fake_provider):
    out = tools.analyze_symbol(fake_provider, "nvda", period="3mo")
    assert out["symbol"] == "NVDA"
    assert out["last_price"] == 140
    assert out["last_date"] == "2026-01-05"
    assert out["trend"] == "資料不足"


@pytest.mark.parametrize("symbol, period", [("XXXX", "6mo"), ("0050", "5y"), ("台積電", "6mo")])
def test_analyze_symbol_errors(fake_provider, symbol, period):
    with pytest.raises(ValueError):
        tools.analyze_symbol(fake_provider, symbol, period)


def test_get_news_clamps_limit():
    out = tools.get_news(FakeNews(), "0050", limit=50)
    assert out["symbol"] == "0050.TW"
    assert len(out["items"]) == 10
    assert out["items"][0]["published"].startswith("2026-10-27")


def test_get_news_error():
    with pytest.raises(ValueError):
        tools.get_news(FakeNews(), "BAD")


def test_add_holding_total_cost(store):
    out = tools.add_holding(store, "0050", 1945, 108714, cost_type="total")
    assert out["avg_cost"] == pytest.approx(108714 / 1945, abs=1e-4)
    assert store.get(out["id"]).shares == 1945


@pytest.mark.parametrize(
    "kwargs",
    [
        {"symbol": "0050", "shares": 1, "cost": 1, "cost_type": "avg"},
        {"symbol": "0050", "shares": 0, "cost": 1},
        {"symbol": "", "shares": 1, "cost": 1},
    ],
)
def test_add_holding_validation(store, kwargs):
    with pytest.raises(ValueError):
        tools.add_holding(store, **kwargs)
    assert store.list() == []


def test_remove_holding(store):
    h = store.add(Holding("0050", 1, 1))
    assert tools.remove_holding(store, h.id)["removed"]["code"] == "0050"
    assert store.list() == []
    with pytest.raises(ValueError):
        tools.remove_holding(store, h.id)


def test_latest_briefing(store):
    assert tools.latest_briefing(store) == {"created_at": None, "content": None}
    store.save_briefing("hello", datetime(2026, 10, 28, 9, 0))
    assert tools.latest_briefing(store) == {"created_at": "2026-10-28T09:00:00", "content": "hello"}


def test_default_db_path(monkeypatch, tmp_path):
    monkeypatch.delenv("ETFWATCH_DB", raising=False)
    assert default_db_path() == PROJECT_ROOT / "data" / "portfolio.db"
    monkeypatch.setenv("ETFWATCH_DB", "data/other.db")  # relative -> project root, not cwd
    monkeypatch.chdir(tmp_path)
    assert default_db_path() == PROJECT_ROOT / "data" / "other.db"
    monkeypatch.setenv("ETFWATCH_DB", str(tmp_path / "abs.db"))
    assert default_db_path() == tmp_path / "abs.db"
    assert (PROJECT_ROOT / "pyproject.toml").exists()
