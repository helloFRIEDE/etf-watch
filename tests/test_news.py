import pytest

from etfwatch.news import (
    DemoNewsProvider,
    NewsError,
    collect_news,
    parse_rss,
    search_term,
)

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>0050 配息創新高 - 經濟日報</title>
    <link>https://example.com/a</link>
    <pubDate>Mon, 26 Oct 2026 08:00:00 GMT</pubDate>
    <source url="https://money.udn.com">經濟日報</source>
  </item>
  <item>
    <title>台股 ETF 規模持續成長 - 鉅亨網</title>
    <link>https://example.com/b</link>
    <pubDate>Tue, 27 Oct 2026 02:00:00 GMT</pubDate>
    <source url="https://news.cnyes.com">鉅亨網</source>
  </item>
  <item><title></title></item>
  <item>
    <title>沒有日期的新聞</title>
    <pubDate>not a date</pubDate>
  </item>
</channel></rss>"""


def test_parse_rss_strips_source_and_sorts_newest_first():
    items = parse_rss(RSS)
    assert [i.title for i in items] == ["台股 ETF 規模持續成長", "0050 配息創新高", "沒有日期的新聞"]
    assert items[0].source == "鉅亨網"
    assert items[0].link == "https://example.com/b"
    assert items[2].published is None


def test_parse_rss_limit():
    assert len(parse_rss(RSS, limit=1)) == 1


def test_parse_rss_bad_xml():
    with pytest.raises(NewsError):
        parse_rss("<rss><unclosed>")


def test_search_term():
    assert search_term("0050.TW") == "元大台灣50 0050"
    assert search_term("nvda") == "輝達 NVIDIA"
    assert search_term("2454.TW") == "2454 股價"


class _Flaky:
    def headlines(self, symbol, limit=5):
        if symbol == "BAD":
            raise NewsError("boom")
        return DemoNewsProvider().headlines(symbol, limit)


def test_collect_news_keeps_going_after_errors():
    news, errors = collect_news(_Flaky(), ["0050.TW", "BAD", "0050.TW"], limit=1)
    assert list(news) == ["0050.TW", "BAD"]
    assert len(news["0050.TW"]) == 1
    assert news["BAD"] == []
    assert errors == {"BAD": "boom"}
