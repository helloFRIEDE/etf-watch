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
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
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


# --- friendly error messages ---
from etfwatch.llm import explain_openai_error


def _err(name, msg=""):
    return type(name, (Exception,), {})(msg)


@pytest.mark.parametrize(
    "exc, expected",
    [
        (_err("AuthenticationError", "Incorrect API key provided"), "API key 無效"),
        (_err("RateLimitError", "Error code: 429 - insufficient_quota"), "沒有 API 額度"),
        (_err("RateLimitError", "Rate limit reached"), "限流"),
        (_err("NotFoundError", "model_not_found: The model does not exist"), "OPENAI_MODEL"),
        (_err("NotFoundError", "Error code: 404 - Resource not found"), "改成 v1"),
        (_err("PermissionDeniedError", "forbidden"), "權限"),
        (_err("APITimeoutError"), "逾時"),
        (_err("APIConnectionError", "Connection error."), "連不到 OpenAI"),
        (ValueError("weird"), "未預期"),
    ],
)
def test_explain_openai_error(exc, expected):
    msg = explain_openai_error(exc, "gpt-test")
    assert expected in msg
    assert str(exc) in msg  # original text kept for debugging


def test_timeout_subclass_of_connection_error_reports_timeout():
    # In the SDK, APITimeoutError subclasses APIConnectionError.
    conn = type("APIConnectionError", (Exception,), {})
    timeout = type("APITimeoutError", (conn,), {})
    assert "逾時" in explain_openai_error(timeout("t"), "m")


def test_client_wraps_sdk_error_with_hint():
    comp = _Completions(exc=_err("AuthenticationError", "401"))
    with pytest.raises(LLMError, match="API key 無效"):
        _client_with(comp).complete("S", "U")


# --- Azure OpenAI ---
from etfwatch.llm import AzureOpenAIClient, normalize_azure_endpoint


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://amy-ai.openai.azure.com/", "https://amy-ai.openai.azure.com/"),
        ("https://amy-ai.openai.azure.com", "https://amy-ai.openai.azure.com/"),
        (
            "https://amy-ai.openai.azure.com/openai/deployments/gpt-4o/chat/completions"
            "?api-version=2024-10-21",
            "https://amy-ai.openai.azure.com/",
        ),
        ('"https://amy-ai.cognitiveservices.azure.com/"', "https://amy-ai.cognitiveservices.azure.com/"),
        ("amy-ai.openai.azure.com", "https://amy-ai.openai.azure.com/"),
    ],
)
def test_normalize_azure_endpoint(raw, expected):
    assert normalize_azure_endpoint(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "https://"])
def test_normalize_azure_endpoint_rejects_empty(raw):
    with pytest.raises(ValueError):
        normalize_azure_endpoint(raw)


def test_default_llm_prefers_azure(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    monkeypatch.setenv(
        "AZURE_OPENAI_ENDPOINT",
        "https://amy-ai.openai.azure.com/openai/deployments/x/chat/completions?api-version=1",
    )
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "my-gpt4o")
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
    client = default_llm()
    assert isinstance(client, AzureOpenAIClient)
    assert client.model == "my-gpt4o"
    assert client.endpoint == "https://amy-ai.openai.azure.com/"


def test_azure_requires_deployment():
    with pytest.raises(ValueError, match="AZURE_OPENAI_DEPLOYMENT"):
        AzureOpenAIClient("https://a.openai.azure.com", "k", deployment=" ")


def test_azure_deployment_not_found_hint():
    msg = explain_openai_error(_err("NotFoundError", "DeploymentNotFound"), "my-gpt4o")
    assert "AZURE_OPENAI_DEPLOYMENT" in msg and "my-gpt4o" in msg


def test_no_temperature_sent():
    # reasoning models (o-series / gpt-5) reject a custom temperature
    comp = _Completions(content="ok")
    _client_with(comp).complete("S", "U")
    assert "temperature" not in comp.kwargs


def test_azure_v1_is_default(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
    c = AzureOpenAIClient("https://amy-ai.openai.azure.com", "k", "gpt-5.1")
    assert c.api_version == "v1"
    assert c.base_url == "https://amy-ai.openai.azure.com/openai/v1/"
    assert str(c._client.base_url).rstrip("/") == "https://amy-ai.openai.azure.com/openai/v1"


@pytest.mark.parametrize("version", ["", "  ", "V1"])
def test_azure_blank_or_uppercase_version_means_v1(version):
    c = AzureOpenAIClient("https://a.openai.azure.com", "k", "d", api_version=version)
    assert c.base_url.endswith("/openai/v1/")


def test_azure_legacy_api_version():
    from openai import AzureOpenAI

    c = AzureOpenAIClient("https://a.openai.azure.com", "k", "d", api_version="2024-10-21")
    assert isinstance(c._client, AzureOpenAI)
    assert c.api_version == "2024-10-21"
