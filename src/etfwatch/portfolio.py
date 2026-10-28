"""Portfolio valuation. Pure functions: no I/O, easy to unit-test."""

from __future__ import annotations

from dataclasses import dataclass

from .models import Holding


@dataclass(frozen=True)
class Position:
    holding: Holding
    price: float  # latest price, asset currency
    fx: float  # asset currency -> TWD

    @property
    def market_value(self) -> float:
        """Market value in the asset's own currency."""
        return self.holding.shares * self.price

    @property
    def cost_twd(self) -> float:
        return self.holding.cost * self.fx

    @property
    def value_twd(self) -> float:
        return self.market_value * self.fx

    @property
    def pnl_twd(self) -> float:
        return self.value_twd - self.cost_twd

    @property
    def pnl_pct(self) -> float | None:
        """Return on cost; None when cost is zero (e.g. gifted shares)."""
        if self.holding.cost == 0:
            return None
        return self.price / self.holding.avg_cost - 1


@dataclass(frozen=True)
class Summary:
    total_cost_twd: float
    total_value_twd: float
    weights: dict[str, float]  # symbol -> share of total value

    @property
    def pnl_twd(self) -> float:
        return self.total_value_twd - self.total_cost_twd

    @property
    def pnl_pct(self) -> float | None:
        if self.total_cost_twd == 0:
            return None
        return self.pnl_twd / self.total_cost_twd


def build_positions(
    holdings: list[Holding],
    prices: dict[str, float],
    fx_to_twd: dict[str, float],
) -> list[Position]:
    """Combine holdings with prices. Raises KeyError if a price or rate is missing."""
    positions = []
    for h in holdings:
        if h.symbol not in prices:
            raise KeyError(f"缺少 {h.symbol} 的價格")
        if h.currency not in fx_to_twd:
            raise KeyError(f"缺少 {h.currency} 匯率")
        positions.append(Position(h, prices[h.symbol], fx_to_twd[h.currency]))
    return positions


def summarize(positions: list[Position]) -> Summary:
    total_cost = sum(p.cost_twd for p in positions)
    total_value = sum(p.value_twd for p in positions)
    weights: dict[str, float] = {}
    if total_value > 0:
        # The same symbol may appear in several lots; merge them.
        for p in positions:
            weights[p.holding.symbol] = weights.get(p.holding.symbol, 0.0) + p.value_twd / total_value
    return Summary(total_cost, total_value, weights)


def cost_warning(position: Position, ratio: float = 3.0) -> str | None:
    """Flag an average cost that is far above the current price.

    The usual cause is typing the total cost into the per-share field, which
    makes the loss look like -99%. Returns a message, or None if it looks fine.
    """
    avg = position.holding.avg_cost
    if position.price <= 0 or avg <= position.price * ratio:
        return None
    implied = avg / position.holding.shares
    return (
        f"平均成本 {avg:,.2f} 是現價 {position.price:,.2f} 的 {avg / position.price:.0f} 倍。"
        f"如果 {avg:,.0f} 其實是總成本，每股成本應為 {implied:,.2f}，"
        "請到「編輯或刪除持股」修正。"
    )
