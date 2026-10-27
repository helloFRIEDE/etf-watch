# ETF Watch — 個人持股觀察站

追蹤自己手上的 ETF 與股票（例如 0050 元大台灣50、NVDA 輝達），在網頁上增刪持股，
自動抓價格、計算損益與走勢指標，之後會加上 LLM 每週簡報與 MCP server。

> 本工具只提供資訊整理，不構成投資建議。

## 功能（v0.1）

- 網頁上新增 / 編輯 / 刪除持股（存在本機 SQLite）
- 支援台股（輸入 `0050` 自動轉成 `0050.TW`）與美股（`NVDA`）
- 美元資產自動換算成台幣，計算總市值、總成本、未實現損益、配置比例
- 個股走勢：近 1 週 / 1 月 / 3 月報酬、MA20 / MA60、最大回撤、趨勢判斷

## 安裝與執行

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env             # 填入自己的 OpenAI key（之後的 LLM 功能用）
streamlit run src/etfwatch/app.py

# 沒網路或想展示時，用模擬價格：
ETFWATCH_DEMO=1 streamlit run src/etfwatch/app.py
```

## 測試

```bash
pytest --cov=etfwatch
```

外部資料（Yahoo Finance）在測試中以假的 `PriceProvider` 取代，所以測試不需要網路。

## API key 安全

- 真正的 key 只放在 `.env`，該檔已列在 `.gitignore`，不會被 commit。
- repo 中只有不含 key 的 `.env.example`。
- push 前可用 `git status` 確認沒有 `.env`。

## 專案結構

```
src/etfwatch/
  symbols.py     代號正規化（0050 → 0050.TW）、判斷幣別
  models.py      Holding 資料結構與驗證
  storage.py     SQLite 持股 CRUD
  market.py      價格來源介面 + Yahoo Finance 實作
  portfolio.py   損益、匯率換算、配置比例（純函式）
  indicators.py  報酬、均線、回撤、趨勢判斷（純函式）
  service.py     串接儲存、行情與計算（網頁與 MCP 共用）
  app.py         Streamlit 網頁
tests/           pytest 單元測試
```
