import pandas as pd
import pytest

from etfwatch.market import MarketDataError


def make_series(values, start="2026-01-01"):
    idx = pd.bdate_range(start=start, periods=len(values))
    return pd.Series([float(v) for v in values], index=idx)


class FakeProvider:
    """In-memory PriceProvider for tests: no network."""

    def __init__(self, data: dict[str, list[float]]):
        self.data = {k: make_series(v) for k, v in data.items()}
        self.calls: list[tuple[str, str]] = []

    def history(self, symbol, period="6mo"):
        self.calls.append((symbol, period))
        if symbol not in self.data:
            raise MarketDataError(f"查無 {symbol}")
        return self.data[symbol]


@pytest.fixture
def fake_provider():
    return FakeProvider(
        {
            "0050.TW": [180, 182, 185],
            "NVDA": [130, 135, 140],
            "TWD=X": [32.0, 32.4, 32.5],
        }
    )
