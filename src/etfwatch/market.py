"""Market data access.

`PriceProvider` is an interface so the rest of the code (and the tests) never
touch the network directly. `YFinanceProvider` is the real implementation.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd

USD_TWD_SYMBOL = "TWD=X"  # Yahoo: price of 1 USD in TWD


class MarketDataError(RuntimeError):
    """Raised when prices cannot be fetched for a symbol."""


class PriceProvider(Protocol):
    def history(self, symbol: str, period: str = "6mo") -> pd.Series:
        """Daily close prices indexed by date (ascending)."""
        ...


class YFinanceProvider:
    """Fetch prices from Yahoo Finance via yfinance."""

    def history(self, symbol: str, period: str = "6mo") -> pd.Series:
        import yfinance as yf  # imported lazily so tests don't need it

        try:
            df = yf.Ticker(symbol).history(period=period, auto_adjust=False)
        except Exception as exc:  # network / parsing errors
            raise MarketDataError(f"無法取得 {symbol} 的價格：{exc}") from exc
        if df is None or df.empty or "Close" not in df:
            raise MarketDataError(f"查無 {symbol} 的價格資料")
        closes = df["Close"].dropna()
        closes.index = pd.to_datetime(closes.index).tz_localize(None)
        return closes.sort_index()


def latest_price(provider: PriceProvider, symbol: str) -> float:
    series = provider.history(symbol, period="5d")
    if series.empty:
        raise MarketDataError(f"查無 {symbol} 的最新價格")
    return float(series.iloc[-1])


def fx_rates_to_twd(provider: PriceProvider, currencies: set[str]) -> dict[str, float]:
    """Conversion rate from each currency to TWD."""
    rates: dict[str, float] = {"TWD": 1.0}
    if "USD" in currencies:
        rates["USD"] = latest_price(provider, USD_TWD_SYMBOL)
    unknown = currencies - rates.keys()
    if unknown:
        raise MarketDataError(f"不支援的幣別：{', '.join(sorted(unknown))}")
    return rates


class DemoProvider:
    """Deterministic synthetic prices for offline demos and UI tests.

    Enabled by setting ETFWATCH_DEMO=1. Never use it for real decisions.
    """

    _BASE = {"TWD=X": 32.0}

    def history(self, symbol: str, period: str = "6mo") -> pd.Series:
        import numpy as np

        days = {"5d": 5, "1mo": 21, "3mo": 63, "6mo": 126, "1y": 252}.get(period, 126)
        seed = sum(ord(c) for c in symbol)
        rng = np.random.default_rng(seed)
        base = self._BASE.get(symbol, 50 + seed % 150)
        is_fx = symbol == USD_TWD_SYMBOL
        drift, vol = (0.0, 0.002) if is_fx else (0.0008, 0.015)
        steps = rng.normal(drift, vol, size=days)
        prices = base * np.exp(np.cumsum(steps))
        idx = pd.bdate_range(end=pd.Timestamp("2026-10-27"), periods=days)
        return pd.Series(prices.round(2), index=idx)
