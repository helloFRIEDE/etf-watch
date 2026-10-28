"""Agent-callable operations, returning plain JSON-friendly dicts.

These functions hold the logic behind the MCP tools. They take their
dependencies (store, price provider, news provider) as arguments, so tests
can pass fakes and never touch the network or the user's real database.

Note: no tool calls our own LLM. The MCP client *is* an LLM, so the server
only supplies grounded data and the agent does the reasoning.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .indicators import analyze
from .market import MarketDataError, PriceProvider
from .models import COST_MODE_PER_SHARE, COST_MODE_TOTAL, Holding, to_avg_cost
from .news import NewsError, NewsProvider
from .portfolio import cost_warning
from .service import load_snapshot
from .storage import HoldingStore
from .symbols import display_code, normalize_symbol

COST_TYPES = {"per_share": COST_MODE_PER_SHARE, "total": COST_MODE_TOTAL}


def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(float(x), nd)


def _holding_dict(h: Holding) -> dict[str, Any]:
    return {
        "id": h.id,
        "symbol": h.symbol,
        "code": display_code(h.symbol),
        "shares": h.shares,
        "avg_cost": _r(h.avg_cost),
        "currency": h.currency,
        "note": h.note,
    }


def list_holdings(store: HoldingStore) -> list[dict[str, Any]]:
    return [_holding_dict(h) for h in store.list()]


def portfolio_summary(store: HoldingStore, provider: PriceProvider) -> dict[str, Any]:
    snap = load_snapshot(store.list(), provider)
    s = snap.summary

    merged: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for p in snap.positions:
        sym = p.holding.symbol
        row = merged.setdefault(
            sym,
            {
                "code": display_code(sym),
                "currency": p.holding.currency,
                "shares": 0.0,
                "price": _r(p.price),
                "cost_twd": 0.0,
                "value_twd": 0.0,
            },
        )
        row["shares"] += p.holding.shares
        row["cost_twd"] += p.cost_twd
        row["value_twd"] += p.value_twd
        if (msg := cost_warning(p)) is not None:
            warnings.append(f"{display_code(sym)} (id {p.holding.id}): {msg}")

    holdings = []
    for sym, row in merged.items():
        t = snap.trends[sym]
        cost = row["cost_twd"]
        holdings.append(
            {
                **row,
                "cost_twd": round(cost),
                "value_twd": round(row["value_twd"]),
                "pnl_twd": round(row["value_twd"] - cost),
                "pnl_pct": _r(row["value_twd"] / cost - 1) if cost else None,
                "weight": _r(s.weights.get(sym, 0.0)),
                "return_1w": _r(t.returns["1w"]),
                "return_1m": _r(t.returns["1m"]),
                "return_3m": _r(t.returns["3m"]),
                "trend": t.trend,
            }
        )

    return {
        "as_of": datetime.now().isoformat(timespec="minutes"),
        "currency": "TWD",
        "total_value": round(s.total_value_twd),
        "total_cost": round(s.total_cost_twd),
        "pnl": round(s.pnl_twd),
        "pnl_pct": _r(s.pnl_pct),
        "usd_twd": _r(snap.fx_to_twd.get("USD")),
        "holdings": holdings,
        "errors": snap.errors,
        "warnings": warnings,
        "disclaimer": "資訊整理，不構成投資建議。",
    }


def analyze_symbol(provider: PriceProvider, symbol: str, period: str = "6mo") -> dict[str, Any]:
    """Trend report for any ticker, held or not."""
    sym = normalize_symbol(symbol)
    if period not in {"1mo", "3mo", "6mo", "1y"}:
        raise ValueError("period 必須是 1mo / 3mo / 6mo / 1y 之一")
    try:
        closes = provider.history(sym, period=period)
    except MarketDataError as exc:
        raise ValueError(str(exc)) from exc
    t = analyze(closes)
    return {
        "symbol": sym,
        "code": display_code(sym),
        "period": period,
        "last_price": _r(t.last_price),
        "last_date": closes.index[-1].date().isoformat(),
        "return_1w": _r(t.returns["1w"]),
        "return_1m": _r(t.returns["1m"]),
        "return_3m": _r(t.returns["3m"]),
        "max_drawdown": _r(t.max_drawdown),
        "trend": t.trend,
    }


def get_news(news: NewsProvider, symbol: str, limit: int = 5) -> dict[str, Any]:
    sym = normalize_symbol(symbol)
    limit = max(1, min(int(limit), 10))
    try:
        items = news.headlines(sym, limit)
    except NewsError as exc:
        raise ValueError(str(exc)) from exc
    return {
        "symbol": sym,
        "items": [
            {
                "title": n.title,
                "source": n.source,
                "published": n.published.isoformat() if n.published else None,
                "link": n.link,
            }
            for n in items
        ],
    }


def add_holding(
    store: HoldingStore,
    symbol: str,
    shares: float,
    cost: float,
    cost_type: str = "per_share",
    note: str = "",
) -> dict[str, Any]:
    if cost_type not in COST_TYPES:
        raise ValueError("cost_type 必須是 'per_share'（每股成本）或 'total'（總成本）")
    avg = to_avg_cost(cost, shares, COST_TYPES[cost_type])
    h = store.add(Holding(symbol, shares, avg, note))
    return _holding_dict(h)


def remove_holding(store: HoldingStore, holding_id: int) -> dict[str, Any]:
    h = store.get(int(holding_id))
    if h is None:
        raise ValueError(f"找不到持股 id={holding_id}")
    store.delete(h.id)
    return {"removed": _holding_dict(h)}


def latest_briefing(store: HoldingStore) -> dict[str, Any]:
    found = store.latest_briefing()
    if found is None:
        return {"created_at": None, "content": None}
    created_at, content = found
    return {"created_at": created_at.isoformat(), "content": content}
