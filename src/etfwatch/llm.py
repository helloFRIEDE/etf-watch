"""LLM briefing and Q&A about the user's holdings.

Design:
- `build_context` turns a Snapshot + news into plain text. Pure, tested.
- The model only sees numbers we computed, so it summarizes rather than
  inventing prices; the system prompt forbids buy/sell advice.
- `LLMClient` is an interface; tests use a fake, the app uses OpenAI.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Protocol

from .news import NewsItem
from .portfolio import cost_warning
from .service import Snapshot
from .symbols import display_code

SYSTEM_PROMPT = """你是一位謹慎的個人投資資訊助理，用繁體中文回答。
規則：
1. 只能使用「持股資料」與「新聞標題」中提供的數字和事實，不可自行編造價格、日期或數據。
2. 不提供買進、賣出、加碼、減碼等投資建議，也不預測未來價格；可以客觀描述走勢與風險。
3. 引用新聞時寫出標題中的關鍵事件與來源；新聞不足時直接說「本週相關新聞不多」。
4. 語氣平實、簡潔，避免誇張用語。"""

BRIEFING_INSTRUCTION = """請根據以上資料寫一份「本週持股簡報」，使用 Markdown，格式如下：

### 一句話總結
（整體帳面損益與本週大致方向）

### 各持股觀察
（每檔 2–3 句：近 1 週 / 1 月表現、趨勢、與哪些新聞可能相關）

### 值得留意
（2–3 點客觀的風險或觀察，例如集中度、回撤、匯率影響；不要給買賣建議）

最後一行固定寫：「以上為資訊整理，不構成投資建議。」"""


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


def _pct(x: float | None) -> str:
    return "無資料" if x is None else f"{x:+.2%}"


def build_context(
    snap: Snapshot,
    news: dict[str, list[NewsItem]] | None = None,
    today: date | None = None,
) -> str:
    """Plain-text description of the portfolio for the model."""
    today = today or date.today()
    news = news or {}
    s = snap.summary
    lines = [f"日期：{today.isoformat()}", "", "## 持股資料（金額單位：新台幣）"]
    lines.append(
        f"總市值 {s.total_value_twd:,.0f}，總成本 {s.total_cost_twd:,.0f}，"
        f"未實現損益 {s.pnl_twd:+,.0f}（{_pct(s.pnl_pct)}）"
    )
    if "USD" in snap.fx_to_twd:
        lines.append(f"美元兌台幣匯率 {snap.fx_to_twd['USD']:.3f}")
    lines.append("")

    # Merge lots of the same symbol so the model sees one line per holding.
    by_symbol: dict[str, list] = {}
    for p in snap.positions:
        by_symbol.setdefault(p.holding.symbol, []).append(p)

    for symbol, positions in by_symbol.items():
        code = display_code(symbol)
        t = snap.trends[symbol]
        shares = sum(p.holding.shares for p in positions)
        cost = sum(p.cost_twd for p in positions)
        value = sum(p.value_twd for p in positions)
        pnl_pct = (value / cost - 1) if cost else None
        weight = s.weights.get(symbol, 0.0)
        cur = positions[0].holding.currency
        lines.append(
            f"- {code}（{cur}）：持有 {shares:g} 股，現價 {t.last_price:,.2f}，"
            f"占組合 {weight:.1%}，帳面報酬 {_pct(pnl_pct)}；"
            f"近1週 {_pct(t.returns['1w'])}、近1月 {_pct(t.returns['1m'])}、"
            f"近3月 {_pct(t.returns['3m'])}；趨勢 {t.trend}；期間最大回撤 {t.max_drawdown:.1%}"
        )
        for p in positions:
            if cost_warning(p):
                lines.append(f"  ※ 注意：{code} 的成本資料可能輸入錯誤，損益數字僅供參考。")
                break

    for symbol, err in snap.errors.items():
        lines.append(f"- {display_code(symbol)}：價格取得失敗（{err}）")

    lines += ["", "## 近 7 日新聞標題"]
    any_news = False
    for symbol in by_symbol:
        items = news.get(symbol, [])
        if not items:
            continue
        any_news = True
        lines.append(f"{display_code(symbol)}：")
        for n in items:
            when = n.published.strftime("%m/%d") if n.published else "日期不明"
            src = f"（{n.source}）" if n.source else ""
            lines.append(f"  - [{when}] {n.title}{src}")
    if not any_news:
        lines.append("（無）")
    return "\n".join(lines)


def generate_briefing(client: LLMClient, context: str) -> str:
    return client.complete(SYSTEM_PROMPT, f"{context}\n\n{BRIEFING_INSTRUCTION}")


def answer_question(client: LLMClient, context: str, question: str) -> str:
    question = question.strip()
    if not question:
        raise ValueError("請輸入問題")
    if len(question) > 500:
        raise ValueError("問題請在 500 字以內")
    user = f"{context}\n\n## 使用者的問題\n{question}\n\n請根據上面的資料回答；資料裡沒有的就說不知道。"
    return client.complete(SYSTEM_PROMPT, user)


def explain_openai_error(exc: Exception, model: str) -> str:
    """Turn an OpenAI SDK exception into a Chinese message that says what to fix.

    Matches on class names in the MRO so it works across SDK versions and is
    testable without constructing real SDK exceptions.
    """
    names = {cls.__name__ for cls in type(exc).__mro__}
    detail = str(exc)
    if "AuthenticationError" in names:
        hint = (
            "API key 無效。請確認 key 完整複製、沒有引號或多餘空白，改完要重新啟動 streamlit。"
            "若用 Azure：key 要填在 AZURE_OPENAI_API_KEY，且必須和 AZURE_OPENAI_ENDPOINT 是同一個資源。"
        )
    elif "RateLimitError" in names and "insufficient_quota" in detail:
        hint = (
            "帳戶沒有 API 額度。ChatGPT Plus 訂閱不包含 API 費用，"
            "需要到 platform.openai.com 的 Billing 頁面儲值（最低 5 美元）。"
        )
    elif "RateLimitError" in names:
        hint = "呼叫太頻繁，被暫時限流。請等一分鐘再試。"
    elif "DeploymentNotFound" in detail or "model_not_found" in detail:
        hint = (
            f"找不到模型或部署「{model}」。OpenAI 請改 OPENAI_MODEL；"
            "Azure 請確認 AZURE_OPENAI_DEPLOYMENT 和 Azure 入口網站「部署」頁面上的名稱完全一致。"
        )
    elif "NotFoundError" in names:
        hint = (
            f"API 路徑不存在（部署「{model}」）。Azure 常見原因："
            "① AZURE_OPENAI_API_VERSION 太舊、不支援這個模型，請改成 v1；"
            "② 端點不是「金鑰與端點」頁面上的 https://<資源名稱>.openai.azure.com 或 "
            ".cognitiveservices.azure.com 網址；③ 部署名稱與入口網站不一致。"
        )
    elif "PermissionDeniedError" in names:
        hint = "這個 key 沒有權限呼叫此 API（可能是專案權限或地區限制），請到 OpenAI 後台檢查 key 的權限設定。"
    elif "APITimeoutError" in names:
        hint = "連線逾時，請稍後再試。"
    elif "APIConnectionError" in names:
        hint = "連不到 OpenAI。請確認網路正常；學校或公司網路可能擋掉 api.openai.com，可改用手機熱點試試。"
    else:
        hint = "未預期的錯誤。"
    return f"OpenAI 呼叫失敗：{hint}\n\n原始訊息：{detail}"


class OpenAIClient:
    """Calls the OpenAI Chat Completions API. Key comes from OPENAI_API_KEY."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", timeout: float = 60.0) -> None:
        from openai import OpenAI

        self.model = model
        self._client = OpenAI(api_key=api_key, timeout=timeout)

    def complete(self, system: str, user: str) -> str:
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except Exception as exc:  # auth, quota, network …
            raise LLMError(explain_openai_error(exc, self.model)) from exc
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            raise LLMError("模型沒有回傳內容")
        return text


# "v1" = Azure's version-less v1 API (/openai/v1/), which supports the newest
# models such as gpt-5.x. Any other value (e.g. "2024-10-21") uses the legacy
# /openai/deployments/{name}?api-version=... route.
AZURE_DEFAULT_API_VERSION = "v1"


def normalize_azure_endpoint(raw: str) -> str:
    """Keep only scheme + host of an Azure endpoint.

    People often paste the full "Target URI" from the Azure portal, e.g.
    https://x.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=...
    while the SDK wants just https://x.openai.azure.com/
    """
    from urllib.parse import urlparse

    raw = (raw or "").strip().strip('"').strip("'")
    if not raw:
        raise ValueError("AZURE_OPENAI_ENDPOINT 不可為空")
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    if not parsed.netloc:
        raise ValueError(f"無法辨識的 Azure 端點：{raw}")
    return f"{parsed.scheme}://{parsed.netloc}/"


class AzureOpenAIClient(OpenAIClient):
    """Azure OpenAI: endpoint, key and deployment name (+ optional API version).

    On Azure the `model` argument is the *deployment name* you created in the
    portal, which may differ from the underlying model name.
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str = AZURE_DEFAULT_API_VERSION,
        timeout: float = 60.0,
    ) -> None:
        if not deployment.strip():
            raise ValueError("請在 .env 設定 AZURE_OPENAI_DEPLOYMENT（Azure 上的部署名稱）")
        self.model = deployment.strip()
        self.endpoint = normalize_azure_endpoint(endpoint)
        self.api_version = (api_version or "").strip() or AZURE_DEFAULT_API_VERSION
        if self.api_version.lower() == "v1":
            from openai import OpenAI

            self.base_url = self.endpoint + "openai/v1/"
            self._client = OpenAI(base_url=self.base_url, api_key=api_key.strip(), timeout=timeout)
        else:
            from openai import AzureOpenAI

            self.base_url = self.endpoint
            self._client = AzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=api_key.strip(),
                api_version=self.api_version,
                timeout=timeout,
            )


class DemoLLM:
    """Canned output for offline demos and UI tests (ETFWATCH_DEMO=1, no key)."""

    def complete(self, system: str, user: str) -> str:
        return "### 一句話總結\n（示範模式）這是模擬的 AI 回覆，設定 OPENAI_API_KEY 後會改用真正的模型。"


def default_llm() -> LLMClient | None:
    """Azure OpenAI if AZURE_OPENAI_ENDPOINT is set, else OpenAI if a key is set;
    demo stub in demo mode; otherwise None."""
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    if azure_endpoint:
        return AzureOpenAIClient(
            endpoint=azure_endpoint,
            api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", ""),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", AZURE_DEFAULT_API_VERSION),
        )
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key and not key.startswith("sk-your"):
        return OpenAIClient(key, os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    if os.getenv("ETFWATCH_DEMO") == "1":
        return DemoLLM()
    return None
