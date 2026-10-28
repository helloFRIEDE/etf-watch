"""MCP server exposing ETF Watch to AI agents (Claude Desktop, VS Code, …).

Run:   python -m etfwatch.mcp_server          (stdio transport)
Debug: npx @modelcontextprotocol/inspector python -m etfwatch.mcp_server

The server shares the web app's database, so holdings added on the website
are visible to the agent and vice versa.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Literal, TypeVar

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import tools
from .market import PriceProvider
from .news import DemoNewsProvider, GoogleNewsProvider, NewsProvider
from .service import default_provider
from .storage import PROJECT_ROOT, HoldingStore, default_db_path

INSTRUCTIONS = """ETF Watch 是使用者個人的台股／美股持股觀察工具。
- 回答「我的持股／損益／配置」時，先呼叫 portfolio_summary，用回傳的數字回答，不要自己估算。
- 比例欄位（weight、pnl_pct、return_*、max_drawdown）是小數，0.05 代表 5%。
- 金額欄位是新台幣；price 與 avg_cost 是該商品原幣（台股 TWD、美股 USD）。
- 新增或刪除持股前，先跟使用者確認內容。
- 不要提供買賣建議；可以客觀描述表現、趨勢與風險。"""

F = TypeVar("F", bound=Callable[..., Any])


def expected_errors(fn: F) -> F:
    """Report our validation errors to the agent instead of a generic crash.

    MCP 2.x hides the text of ordinary exceptions ("Error executing tool");
    raising ToolError passes the message through so the model can fix its call
    (e.g. use '2330' instead of '台積電').
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except (ValueError, KeyError) as exc:
            raise ToolError(str(exc).strip("'\"")) from exc

    return wrapper  # type: ignore[return-value]


READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
READ_ONLY_WEB = ToolAnnotations(readOnlyHint=True, openWorldHint=True)


def build_server(
    store: HoldingStore,
    provider: PriceProvider,
    news: NewsProvider,
) -> MCPServer:
    """Create the server with injected dependencies (tests pass fakes)."""
    mcp = MCPServer(name="etf-watch", instructions=INSTRUCTIONS)

    @mcp.tool(annotations=READ_ONLY)
    @expected_errors
    def list_holdings() -> list[dict[str, Any]]:
        """列出使用者記錄的所有持股（含 id、代號、股數、每股平均成本、幣別、備註）。"""
        return tools.list_holdings(store)

    @mcp.tool(annotations=READ_ONLY_WEB)
    @expected_errors
    def portfolio_summary() -> dict[str, Any]:
        """取得投資組合即時摘要：總市值、總成本、未實現損益（新台幣）、各持股的配置比例、
        近 1 週／1 月／3 月報酬與趨勢。同一代號的多筆會合併。warnings 列出可能填錯的成本。"""
        return tools.portfolio_summary(store, provider)

    @mcp.tool(annotations=READ_ONLY_WEB)
    @expected_errors
    def analyze_symbol(
        symbol: str, period: Literal["1mo", "3mo", "6mo", "1y"] = "6mo"
    ) -> dict[str, Any]:
        """分析任一檔股票或 ETF 的走勢（不一定要持有）。symbol 例：'0050'、'00878'、'NVDA'。
        回傳最新價、期間報酬、最大回撤與均線趨勢（多頭排列／空頭排列／盤整）。"""
        return tools.analyze_symbol(provider, symbol, period)

    @mcp.tool(annotations=READ_ONLY_WEB)
    @expected_errors
    def get_news(symbol: str, limit: int = 5) -> dict[str, Any]:
        """取得某檔股票或 ETF 近 7 日的中文新聞標題（Google News），limit 最多 10。"""
        return tools.get_news(news, symbol, limit)

    @mcp.tool(annotations=READ_ONLY)
    @expected_errors
    def latest_briefing() -> dict[str, Any]:
        """讀取使用者在網頁上最近一次產生的 AI 每週簡報（沒有則 content 為 null）。"""
        return tools.latest_briefing(store)

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
    )
    @expected_errors
    def add_holding(
        symbol: str,
        shares: float,
        cost: float,
        cost_type: Literal["per_share", "total"] = "per_share",
        note: str = "",
    ) -> dict[str, Any]:
        """新增一筆持股。cost_type='per_share' 時 cost 是每股成本；
        'total' 時 cost 是總付出成本（會自動除以股數）。成本以該商品原幣計。"""
        return tools.add_holding(store, symbol, shares, cost, cost_type, note)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
    @expected_errors
    def remove_holding(holding_id: int) -> dict[str, Any]:
        """依 id 刪除一筆持股（id 可從 list_holdings 取得）。刪除前請先跟使用者確認。"""
        return tools.remove_holding(store, holding_id)

    return mcp


def main() -> None:
    import os

    load_dotenv(PROJECT_ROOT / ".env")
    news: NewsProvider = (
        DemoNewsProvider() if os.getenv("ETFWATCH_DEMO") == "1" else GoogleNewsProvider()
    )
    server = build_server(HoldingStore(default_db_path()), default_provider(), news)
    server.run("stdio")


if __name__ == "__main__":
    main()
