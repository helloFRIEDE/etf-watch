import pytest

from etfwatch.market import MarketDataError, fx_rates_to_twd, latest_price


def test_latest_price(fake_provider):
    assert latest_price(fake_provider, "0050.TW") == 185


def test_latest_price_unknown_symbol(fake_provider):
    with pytest.raises(MarketDataError):
        latest_price(fake_provider, "XXXX")


def test_fx_twd_only_does_not_fetch(fake_provider):
    assert fx_rates_to_twd(fake_provider, {"TWD"}) == {"TWD": 1.0}
    assert fake_provider.calls == []


def test_fx_with_usd(fake_provider):
    rates = fx_rates_to_twd(fake_provider, {"TWD", "USD"})
    assert rates == {"TWD": 1.0, "USD": 32.5}


def test_fx_unsupported_currency(fake_provider):
    with pytest.raises(MarketDataError):
        fx_rates_to_twd(fake_provider, {"JPY"})


# --- YFinanceProvider with yfinance mocked out (no network) ---
import pandas as pd
import yfinance

from etfwatch.market import YFinanceProvider


class _FakeTicker:
    def __init__(self, df=None, exc=None):
        self._df, self._exc = df, exc

    def history(self, **kwargs):
        if self._exc:
            raise self._exc
        return self._df


def test_yfinance_provider_parses_close(monkeypatch):
    idx = pd.date_range("2026-10-20", periods=3, tz="Asia/Taipei")
    df = pd.DataFrame({"Close": [3.0, 1.0, 2.0]}, index=idx[::-1])
    monkeypatch.setattr(yfinance, "Ticker", lambda s: _FakeTicker(df))
    s = YFinanceProvider().history("0050.TW")
    assert list(s) == [2.0, 1.0, 3.0]  # sorted ascending by date
    assert s.index.tz is None


@pytest.mark.parametrize(
    "ticker",
    [_FakeTicker(df=pd.DataFrame()), _FakeTicker(exc=ConnectionError("offline"))],
)
def test_yfinance_provider_errors(monkeypatch, ticker):
    monkeypatch.setattr(yfinance, "Ticker", lambda s: ticker)
    with pytest.raises(MarketDataError):
        YFinanceProvider().history("0050.TW")
