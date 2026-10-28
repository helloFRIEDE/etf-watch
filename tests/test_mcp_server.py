"""End-to-end tests: a real MCP client talks to the server in-process."""

import anyio
import pytest
from mcp.client.client import Client

from etfwatch.market import DemoProvider
from etfwatch.mcp_server import build_server
from etfwatch.models import Holding
from etfwatch.news import DemoNewsProvider
from etfwatch.storage import HoldingStore

EXPECTED_TOOLS = {
    "list_holdings",
    "portfolio_summary",
    "analyze_symbol",
    "get_news",
    "latest_briefing",
    "add_holding",
    "remove_holding",
}


@pytest.fixture
def store():
    s = HoldingStore(":memory:")
    s.add(Holding("0050", 100, 55))
    s.add(Holding("NVDA", 0.5, 120))
    yield s
    s.close()


@pytest.fixture
def server(store):
    return build_server(store, DemoProvider(), DemoNewsProvider())


def call(server, name, args=None):
    async def go():
        async with Client(server) as c:
            return await c.call_tool(name, args or {})

    return anyio.run(go)


def error_text(result):
    assert result.is_error
    return " ".join(c.text for c in result.content)


def test_tools_are_listed_with_annotations(server):
    async def go():
        async with Client(server) as c:
            return (await c.list_tools()).tools

    tools = {t.name: t for t in anyio.run(go)}
    assert set(tools) == EXPECTED_TOOLS
    assert tools["portfolio_summary"].annotations.read_only_hint is True
    assert tools["remove_holding"].annotations.destructive_hint is True
    assert tools["add_holding"].annotations.read_only_hint is False
    # every tool tells the agent what it does
    assert all(t.description for t in tools.values())
    # Literal type hints become enums in the input schema
    assert tools["add_holding"].input_schema["properties"]["cost_type"]["enum"] == ["per_share", "total"]


def test_portfolio_summary(server):
    r = call(server, "portfolio_summary")
    assert not r.is_error
    data = r.structured_content
    assert [h["code"] for h in data["holdings"]] == ["0050", "NVDA"]
    assert data["usd_twd"] is not None
    assert data["total_value"] > 0


def test_add_then_remove_via_agent(server, store):
    r = call(server, "add_holding", {"symbol": "00878", "shares": 1000, "cost": 21500, "cost_type": "total"})
    assert not r.is_error
    new_id = r.structured_content["id"]
    assert store.get(new_id).avg_cost == pytest.approx(21.5)
    r = call(server, "remove_holding", {"holding_id": new_id})
    assert not r.is_error
    assert store.get(new_id) is None


def test_validation_errors_reach_the_agent(server):
    # The agent must see *why* it failed so it can retry with a ticker code.
    assert "無法辨識的代號" in error_text(call(server, "analyze_symbol", {"symbol": "台積電"}))
    assert "找不到持股" in error_text(call(server, "remove_holding", {"holding_id": 999}))
    assert "股數必須大於 0" in error_text(
        call(server, "add_holding", {"symbol": "0050", "shares": 0, "cost": 1})
    )


def test_schema_rejects_bad_enum(server):
    r = call(server, "add_holding", {"symbol": "0050", "shares": 1, "cost": 1, "cost_type": "avg"})
    assert r.is_error


def test_get_news_and_briefing(server, store):
    r = call(server, "get_news", {"symbol": "0050", "limit": 1})
    assert len(r.structured_content["items"]) == 1
    assert call(server, "latest_briefing").structured_content["content"] is None
    store.save_briefing("本週簡報")
    assert call(server, "latest_briefing").structured_content["content"] == "本週簡報"


def test_stdio_launch_like_claude_desktop(tmp_path):
    """Start `python -m etfwatch.mcp_server` as a subprocess, as an MCP client would."""
    import os
    import sys

    from mcp.client.client import StdioServerParameters

    env = {
        **os.environ,
        "ETFWATCH_DEMO": "1",
        "ETFWATCH_DB": str(tmp_path / "stdio.db"),
        "OPENAI_API_KEY": "",
        "AZURE_OPENAI_ENDPOINT": "",
    }
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "etfwatch.mcp_server"], env=env, cwd=str(tmp_path)
    )

    async def go():
        async with Client(params) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            added = await c.call_tool("add_holding", {"symbol": "0050", "shares": 10, "cost": 50})
            listed = await c.call_tool("list_holdings", {})
            return names, added, listed

    names, added, listed = anyio.run(go)
    assert names == EXPECTED_TOOLS
    assert not added.is_error
    assert listed.structured_content["result"][0]["code"] == "0050"
    # the server wrote to the configured DB, not one in its working directory
    assert (tmp_path / "stdio.db").exists()
