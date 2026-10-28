"""Recent news headlines per holding, from Google News RSS (Traditional Chinese).

`NewsProvider` is an interface so tests and demo mode never hit the network.
"""

from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Protocol

from .symbols import display_code

# Better search terms for common holdings; anything else falls back to the code.
SEARCH_TERMS = {
    "0050.TW": "元大台灣50 0050",
    "0056.TW": "元大高股息 0056",
    "00878.TW": "國泰永續高股息 00878",
    "006208.TW": "富邦台50 006208",
    "00919.TW": "群益台灣精選高息 00919",
    "2330.TW": "台積電",
    "NVDA": "輝達 NVIDIA",
    "TSM": "台積電 ADR",
    "AAPL": "蘋果 Apple 股價",
    "VOO": "VOO ETF 標普500",
    "QQQ": "QQQ ETF 那斯達克",
}

RSS_URL = "https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"


@dataclass(frozen=True)
class NewsItem:
    title: str
    source: str
    published: datetime | None
    link: str


class NewsError(RuntimeError):
    pass


class NewsProvider(Protocol):
    def headlines(self, symbol: str, limit: int = 5) -> list[NewsItem]: ...


def search_term(symbol: str) -> str:
    return SEARCH_TERMS.get(symbol.upper(), f"{display_code(symbol)} 股價")


def parse_rss(xml_text: str, limit: int = 5) -> list[NewsItem]:
    """Parse a Google News RSS document into NewsItems (newest first)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise NewsError(f"新聞資料格式錯誤：{exc}") from exc
    items: list[NewsItem] = []
    for node in root.iter("item"):
        title = (node.findtext("title") or "").strip()
        if not title:
            continue
        source = (node.findtext("source") or "").strip()
        # Google appends " - 來源" to titles; drop it since we keep source separately.
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3].rstrip()
        published = None
        if raw_date := node.findtext("pubDate"):
            try:
                published = parsedate_to_datetime(raw_date)
            except (TypeError, ValueError):
                published = None
        items.append(NewsItem(title, source, published, (node.findtext("link") or "").strip()))
    items.sort(key=lambda n: n.published.timestamp() if n.published else 0, reverse=True)
    return items[:limit]


class GoogleNewsProvider:
    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def headlines(self, symbol: str, limit: int = 5) -> list[NewsItem]:
        q = urllib.parse.quote(f"{search_term(symbol)} when:7d")
        req = urllib.request.Request(RSS_URL.format(q=q), headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
        except OSError as exc:
            raise NewsError(f"無法取得 {display_code(symbol)} 的新聞：{exc}") from exc
        return parse_rss(text, limit)


class DemoNewsProvider:
    """Fixed headlines for offline demos and tests (ETFWATCH_DEMO=1)."""

    def headlines(self, symbol: str, limit: int = 5) -> list[NewsItem]:
        code = display_code(symbol)
        return [
            NewsItem(f"（示範新聞）{code} 本週成交量放大", "示範來源", None, ""),
            NewsItem(f"（示範新聞）法人調整 {code} 相關持股", "示範來源", None, ""),
        ][:limit]


def collect_news(
    provider: NewsProvider, symbols: list[str], limit: int = 5
) -> tuple[dict[str, list[NewsItem]], dict[str, str]]:
    """Headlines for each symbol, plus per-symbol error messages (never raises)."""
    news: dict[str, list[NewsItem]] = {}
    errors: dict[str, str] = {}
    for s in dict.fromkeys(symbols):
        try:
            news[s] = provider.headlines(s, limit)
        except NewsError as exc:
            news[s] = []
            errors[s] = str(exc)
    return news, errors
