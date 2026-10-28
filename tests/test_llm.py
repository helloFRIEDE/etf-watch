from datetime import date, datetime, timezone

import pytest

from etfwatch.llm import (
    SYSTEM_PROMPT,
    DemoLLM,
    LLMError,
    OpenAIClient,
    answer_question,
    build_context,
    default_llm,
    generate_briefing,
)
from etfwatch.models import Holding
from etfwatch.news import NewsItem
from etfwatch.service import load_snapshot
from tests.conftest import FakeProvider


class FakeLLM:
    def __init__(self, reply="好的"):
        self.reply = reply
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        return self.reply


@pytest.fixture
def snap(fake_provider):
    holdings = [Holding("0050", 100, 150), Holding("0050", 10, 160), Holding("NVDA", 1, 100)]
    return load_snapshot(holdings, fake_provider)


NEWS = {
    "0050.TW": [
        NewsItem("0050 配息創新高", "經濟日報", datetime(2026, 10, 26, tzinfo=timezone.utc), ""),
    ]
}


def test_context_has_numbers_and_news(snap):
    ctx = build_context(snap, NEWS, today=date(2026, 10, 28))
    assert "日期：2026-10-28" in ctx
    assert "美元兌台幣匯率 32.500" in ctx
    # two 0050 lots merged into one line with 110 shares
    assert ctx.count("- 0050（TWD）") == 1
    assert "持有 110 股" in ctx
    assert "- NVDA（USD）" in ctx
    assert "[10/26] 0050 配息創新高（經濟日報）" in ctx


def test_context_without_news(snap):
    ctx = build_context(snap, {}, today=date(2026, 10, 28))
    assert "（無）" in ctx


def test_context_flags_suspicious_cost_and_errors():
    provider = FakeProvider({"0050.TW": [100.0]})
    snap = load_snapshot([Holding("0050", 1000, 50000), Holding("9999", 1, 1)], provider)
    ctx = build_context(snap, {}, today=date(2026, 10, 28))
    assert "成本資料可能輸入錯誤" in ctx
    assert "9999：價格取得失敗" in ctx


def test_generate_briefing_sends_rules_and_context(snap):
    llm = FakeLLM("簡報內容")
    out = generate_briefing(llm, "CONTEXT")
    assert out == "簡報內容"
    system, user = llm.calls[0]
    assert system == SYSTEM_PROMPT
    assert "不提供買進" in system
    assert user.startswith("CONTEXT")
    assert "本週持股簡報" in user


def test_answer_question(snap):
    llm = FakeLLM("回答")
    assert answer_question(llm, "CTX", " 0050 最近怎樣？ ") == "回答"
    assert "0050 最近怎樣？" in llm.calls[0][1]


@pytest.mark.parametrize("q", ["", "   ", "x" * 501])
def test_answer_question_validates(q):
    with pytest.raises(ValueError):
        answer_question(FakeLLM(), "CTX", q)


def test_default_llm(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ETFWATCH_DEMO", raising=False)
    assert default_llm() is None
    monkeypatch.setenv("OPENAI_API_KEY", "sk-your-key-here")  # placeholder from .env.example
    assert default_llm() is None
    monkeypatch.setenv("ETFWATCH_DEMO", "1")
    assert isinstance(default_llm(), DemoLLM)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    client = default_llm()
    assert isinstance(client, OpenAIClient)
    assert client.model == "gpt-4o-mini"


# --- OpenAIClient with the SDK call mocked out (no network, no key) ---

class _Msg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _Completions:
    def __init__(self, content=None, exc=None):
        self.content, self.exc, self.kwargs = content, exc, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.exc:
            raise self.exc
        return type("R", (), {"choices": [_Msg(self.content)]})()


def _client_with(completions):
    c = OpenAIClient("sk-test", model="gpt-test")
    c._client = type("C", (), {"chat": type("Chat", (), {"completions": completions})()})()
    return c


def test_openai_client_success():
    comp = _Completions(content="  hi  ")
    assert _client_with(comp).complete("SYS", "USER") == "hi"
    assert comp.kwargs["model"] == "gpt-test"
    assert comp.kwargs["messages"][0] == {"role": "system", "content": "SYS"}


@pytest.mark.parametrize("comp", [_Completions(exc=RuntimeError("401")), _Completions(content="")])
def test_openai_client_errors(comp):
    with pytest.raises(LLMError):
        _client_with(comp).complete("S", "U")
