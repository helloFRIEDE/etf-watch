"""Trend indicators on a daily close series. Pure functions."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

TRADING_DAYS = {"1w": 5, "1m": 21, "3m": 63}


def period_return(closes: pd.Series, days: int) -> float | None:
    """Return over the last `days` trading days; None if not enough data."""
    if days <= 0:
        raise ValueError("days 必須大於 0")
    if len(closes) <= days:
        return None
    start = float(closes.iloc[-days - 1])
    end = float(closes.iloc[-1])
    if start == 0:
        return None
    return end / start - 1


def moving_average(closes: pd.Series, window: int) -> pd.Series:
    if window <= 0:
        raise ValueError("window 必須大於 0")
    return closes.rolling(window=window, min_periods=window).mean()


def max_drawdown(closes: pd.Series) -> float:
    """Largest peak-to-trough drop as a negative fraction (0.0 if never fell)."""
    if closes.empty:
        return 0.0
    running_peak = closes.cummax()
    drawdowns = closes / running_peak - 1
    return float(drawdowns.min())


def trend_label(closes: pd.Series, short: int = 20, long: int = 60) -> str:
    """Simple MA-based trend description.

    多頭排列: price > MA short > MA long
    空頭排列: price < MA short < MA long
    otherwise 盤整; 資料不足 if the long MA is not available yet.
    """
    if len(closes) < long:
        return "資料不足"
    price = float(closes.iloc[-1])
    ma_s = float(moving_average(closes, short).iloc[-1])
    ma_l = float(moving_average(closes, long).iloc[-1])
    if price > ma_s > ma_l:
        return "多頭排列"
    if price < ma_s < ma_l:
        return "空頭排列"
    return "盤整"


@dataclass(frozen=True)
class TrendReport:
    last_price: float
    returns: dict[str, float | None]  # "1w" / "1m" / "3m"
    max_drawdown: float
    trend: str


def analyze(closes: pd.Series) -> TrendReport:
    if closes.empty:
        raise ValueError("沒有價格資料")
    return TrendReport(
        last_price=float(closes.iloc[-1]),
        returns={k: period_return(closes, d) for k, d in TRADING_DAYS.items()},
        max_drawdown=max_drawdown(closes),
        trend=trend_label(closes),
    )
