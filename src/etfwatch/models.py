"""Domain model for a holding."""

from __future__ import annotations

from dataclasses import dataclass

from .symbols import currency_of, normalize_symbol


@dataclass
class Holding:
    """One position the user owns.

    shares may be fractional (e.g. US fractional shares via 複委託).
    avg_cost is per share, in the asset's own trading currency.
    """

    symbol: str
    shares: float
    avg_cost: float
    note: str = ""
    id: int | None = None

    def __post_init__(self) -> None:
        self.symbol = normalize_symbol(self.symbol)
        try:
            self.shares = float(self.shares)
            self.avg_cost = float(self.avg_cost)
        except (TypeError, ValueError) as exc:
            raise ValueError("股數與成本必須是數字") from exc
        if self.shares <= 0:
            raise ValueError("股數必須大於 0")
        if self.avg_cost < 0:
            raise ValueError("平均成本不可為負數")
        self.note = (self.note or "").strip()

    @property
    def currency(self) -> str:
        return currency_of(self.symbol)

    @property
    def cost(self) -> float:
        """Total cost in the asset's own currency."""
        return self.shares * self.avg_cost


COST_MODE_PER_SHARE = "每股平均成本"
COST_MODE_TOTAL = "總成本（券商 App 的付出成本）"
COST_MODES = (COST_MODE_PER_SHARE, COST_MODE_TOTAL)


def to_avg_cost(amount: float, shares: float, mode: str) -> float:
    """Convert what the user typed into a per-share average cost."""
    if mode == COST_MODE_PER_SHARE:
        return float(amount)
    if mode == COST_MODE_TOTAL:
        if shares <= 0:
            raise ValueError("股數必須大於 0")
        return float(amount) / float(shares)
    raise ValueError(f"未知的成本輸入方式：{mode}")
