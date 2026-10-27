"""Ticker normalization: turn what a user types into a Yahoo Finance symbol."""

from __future__ import annotations

import re

# Taiwan listed codes: 4-6 digits, optionally followed by one letter (e.g. 00679B, 00632R)
_TW_CODE = re.compile(r"^\d{4,6}[A-Z]?$")
_US_TICKER = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def normalize_symbol(raw: str) -> str:
    """Return a Yahoo Finance symbol.

    >>> normalize_symbol(" 0050 ")
    '0050.TW'
    >>> normalize_symbol("nvda")
    'NVDA'
    """
    if raw is None:
        raise ValueError("代號不可為空")
    s = raw.strip().upper()
    if not s:
        raise ValueError("代號不可為空")
    if s.endswith(".TW") or s.endswith(".TWO"):
        base = s.rsplit(".", 1)[0]
        if not _TW_CODE.match(base):
            raise ValueError(f"無法辨識的台股代號：{raw}")
        return s
    if _TW_CODE.match(s):
        return f"{s}.TW"
    if _US_TICKER.match(s):
        return s
    raise ValueError(f"無法辨識的代號：{raw}")


def currency_of(symbol: str) -> str:
    """Trading currency of a normalized symbol."""
    s = symbol.upper()
    if s.endswith(".TW") or s.endswith(".TWO"):
        return "TWD"
    return "USD"


def display_code(symbol: str) -> str:
    """Short code for UI, e.g. '0050.TW' -> '0050'."""
    s = symbol.upper()
    for suffix in (".TWO", ".TW"):
        if s.endswith(suffix):
            return s[: -len(suffix)]
    return s
