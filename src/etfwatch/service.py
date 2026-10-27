"""Glue between storage, market data and calculations.

The web UI (and later the MCP server) call `load_snapshot`, so the logic is
shared and testable without Streamlit.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import pandas as pd

from .indicators import TrendReport, analyze
from .market import (
    DemoProvider,
    MarketDataError,
    PriceProvider,
    YFinanceProvider,
    fx_rates_to_twd,
)
from .models import Holding
from .portfolio import Position, Summary, build_positions, summarize


@dataclass
class Snapshot:
    positions: list[Position]
    summary: Summary
    histories: dict[str, pd.Series]
    trends: dict[str, TrendReport]
    fx_to_twd: dict[str, float]
    errors: dict[str, str] = field(default_factory=dict)  # symbol -> message


def default_provider() -> PriceProvider:
    if os.getenv("ETFWATCH_DEMO") == "1":
        return DemoProvider()
    return YFinanceProvider()


def load_snapshot(
    holdings: list[Holding],
    provider: PriceProvider,
    period: str = "6mo",
) -> Snapshot:
    """Fetch each symbol once, value the portfolio, and collect per-symbol errors.

    A symbol that fails to load is reported in `errors` and left out of the
    totals instead of breaking the whole page.
    """
    histories: dict[str, pd.Series] = {}
    errors: dict[str, str] = {}
    for symbol in dict.fromkeys(h.symbol for h in holdings):  # unique, ordered
        try:
            series = provider.history(symbol, period=period)
            if series.empty:
                raise MarketDataError(f"查無 {symbol} 的價格資料")
            histories[symbol] = series
        except MarketDataError as exc:
            errors[symbol] = str(exc)

    priced = [h for h in holdings if h.symbol in histories]
    currencies = {h.currency for h in priced}
    try:
        fx = fx_rates_to_twd(provider, currencies)
    except MarketDataError as exc:
        # Without the FX rate we can still show TWD holdings.
        fx = {"TWD": 1.0}
        for h in priced:
            if h.currency != "TWD":
                errors.setdefault(h.symbol, f"匯率取得失敗：{exc}")
        priced = [h for h in priced if h.currency == "TWD"]

    prices = {s: float(series.iloc[-1]) for s, series in histories.items()}
    positions = build_positions(priced, prices, fx)
    trends = {s: analyze(series) for s, series in histories.items()}
    return Snapshot(positions, summarize(positions), histories, trends, fx, errors)
