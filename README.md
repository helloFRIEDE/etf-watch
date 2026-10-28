# ETF Watch — 個人持股觀察站

追蹤自己手上的 ETF 與股票（例如 0050 元大台灣50、NVDA 輝達），在網頁上增刪持股，
自動抓價格、計算損益與走勢指標，並用 LLM 結合近期新聞產生每週持股簡報、回答關於持股的問題。

> 本工具只提供資訊整理，不構成投資建議。

## 功能（v0.1）

- 網頁上新增 / 編輯 / 刪除持股（存在本機 SQLite）
- 支援台股（輸入 `0050` 自動轉成 `0050.TW`）與美股（`NVDA`）
- 美元資產自動換算成台幣，計算總市值、總成本、未實現損益、配置比例
- 個股走勢：近 1 週 / 1 月 / 3 月報酬、MA20 / MA60、最大回撤、趨勢判斷
- 🤖 AI 每週簡報：把計算好的數字與 Google News 近 7 日新聞標題交給 OpenAI 模型整理成簡報
- 🤖 問問 AI：例如「輝達占我的組合多少？」「0050 最近表現如何？」
- 🔌 MCP server：把上述功能包成 7 個工具，Claude Desktop、VS Code Copilot 等 AI 代理可以直接呼叫

### LLM 設計重點

- 模型只拿到程式算好的數字與新聞標題（`llm.build_context`），被要求不得自行編造數據
- System prompt 禁止給買賣建議或預測價格
- 簡報存在 SQLite，重新整理頁面不會重複呼叫 API、不會重複花錢
- 測試用假的 LLM 與 mock 掉的 OpenAI SDK，跑測試不需要 key、不會產生費用

## 安裝與執行

**Windows（PowerShell）**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1     # 若出現「已停用指令碼執行」，先跑：Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -e ".[dev]"

copy .env.example .env          # 填入自己的 OpenAI key（之後的 LLM 功能用）
streamlit run src/etfwatch/app.py

# 沒網路或想展示時，用模擬價格：
$env:ETFWATCH_DEMO="1"; streamlit run src/etfwatch/app.py
```

**macOS / Linux**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
streamlit run src/etfwatch/app.py
ETFWATCH_DEMO=1 streamlit run src/etfwatch/app.py   # 模擬價格
```

### 設定 LLM（Azure OpenAI 或 OpenAI）

編輯 `.env`。使用 **Azure OpenAI** 時填這四個（有填 `AZURE_OPENAI_ENDPOINT` 就會優先使用 Azure）：

```
AZURE_OPENAI_ENDPOINT=https://<你的資源名稱>.openai.azure.com/
AZURE_OPENAI_API_KEY=<金鑰與端點頁面上的 KEY 1>
AZURE_OPENAI_DEPLOYMENT=<部署名稱>
AZURE_OPENAI_API_VERSION=v1
```

端點貼入口網站的完整「目標 URI」也可以，程式會自動只取網域部分。
`v1` 是 Azure 的新版 API（`/openai/v1/`），支援 gpt-5.x 等新模型；填日期版本（如 `2024-10-21`）則走舊路徑。
使用 OpenAI 官方則只要填 `OPENAI_API_KEY`（與選填的 `OPENAI_MODEL`）。

### 輸入成本

新增持股時可選「每股平均成本」或「總成本」。直接抄券商 App 的「付出成本」就選總成本，
系統會自動除以股數。若平均成本高於現價 3 倍以上，頁面會提醒你可能填錯欄位。

## MCP server（給 AI 代理用）

`python -m etfwatch.mcp_server` 以 stdio 啟動，與網頁共用同一個資料庫。

| 工具 | 用途 | 類型 |
|---|---|---|
| `list_holdings` | 列出所有持股 | 唯讀 |
| `portfolio_summary` | 總市值、損益、配置、各檔報酬與趨勢 | 唯讀（抓行情） |
| `analyze_symbol` | 分析任一代號的走勢（不必持有） | 唯讀（抓行情） |
| `get_news` | 某代號近 7 日新聞標題 | 唯讀（抓新聞） |
| `latest_briefing` | 網頁上最近一次的 AI 簡報 | 唯讀 |
| `add_holding` | 新增持股（每股或總成本） | 寫入 |
| `remove_holding` | 刪除持股 | 破壞性 |

設計：MCP server **不呼叫自己的 LLM**，只提供算好的數字；推理交給呼叫它的 AI 代理。
工具都帶 MCP annotations（唯讀／破壞性），代理在刪除前會先徵詢使用者。

### 接上 Claude Desktop（Windows）

Claude Desktop →「設定」→「開發者」→「編輯設定」，打開 `claude_desktop_config.json`，加入
（路徑換成你的專案位置，反斜線要寫兩次）：

```json
{
  "mcpServers": {
    "etf-watch": {
      "command": "C:\\Users\\你的名字\\etf-watch\\.venv\\Scripts\\python.exe",
      "args": ["-m", "etfwatch.mcp_server"]
    }
  }
}
```

存檔後**完全關閉** Claude Desktop（含系統匣圖示）再開啟，就能問「我的持股現在賺多少？」。

### 接上 VS Code（Copilot agent 模式）

在專案根目錄建立 `.vscode/mcp.json`：

```json
{
  "servers": {
    "etf-watch": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": ["-m", "etfwatch.mcp_server"]
    }
  }
}
```

### 除錯

```powershell
npx @modelcontextprotocol/inspector .venv\Scripts\python.exe -m etfwatch.mcp_server
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
  news.py        Google News RSS 新聞標題
  llm.py         prompt 組裝、OpenAI / Azure 呼叫、簡報與問答
  tools.py       代理可呼叫的操作（純函式，回傳 dict）
  mcp_server.py  MCP server，把 tools 註冊成 MCP 工具
  app.py         Streamlit 網頁
tests/           pytest 單元測試
```
