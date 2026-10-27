"""Streamlit web UI.

Run with:  streamlit run src/etfwatch/app.py
Offline demo prices:  ETFWATCH_DEMO=1 streamlit run src/etfwatch/app.py
"""

from __future__ import annotations

import os

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from etfwatch.indicators import moving_average
from etfwatch.models import Holding
from etfwatch.service import default_provider, load_snapshot
from etfwatch.storage import HoldingStore
from etfwatch.symbols import display_code

load_dotenv()

st.set_page_config(page_title="ETF Watch", page_icon="📈", layout="wide")


@st.cache_resource
def get_store(path: str) -> HoldingStore:
    return HoldingStore(path)


@st.cache_data(ttl=600, show_spinner=False)
def cached_history(symbol: str, period: str, demo: bool) -> pd.Series:
    return default_provider().history(symbol, period=period)


class CachedProvider:
    """Wraps the real provider with Streamlit's 10-minute cache."""

    def history(self, symbol: str, period: str = "6mo") -> pd.Series:
        return cached_history(symbol, period, os.getenv("ETFWATCH_DEMO") == "1")


def fmt_twd(x: float) -> str:
    return f"NT$ {x:,.0f}"


def fmt_pct(x: float | None) -> str:
    return "—" if x is None else f"{x:+.2%}"


store = get_store(os.getenv("ETFWATCH_DB", "data/portfolio.db"))

# ---------------- Sidebar: add holding ----------------
with st.sidebar:
    st.header("新增持股")
    with st.form("add_form", clear_on_submit=True):
        code = st.text_input("代號", placeholder="0050 或 NVDA")
        shares = st.number_input("股數", min_value=0.0, step=1.0, format="%.4f")
        avg_cost = st.number_input("平均成本（原幣）", min_value=0.0, step=0.01, format="%.2f")
        note = st.text_input("備註", placeholder="例如：定期定額")
        submitted = st.form_submit_button("新增", use_container_width=True)
    if submitted:
        try:
            h = store.add(Holding(code, shares, avg_cost, note))
            st.success(f"已新增 {display_code(h.symbol)}")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    st.caption("台股輸入代號即可（0050），美股輸入 ticker（NVDA）。成本以該商品原幣計。")
    if os.getenv("ETFWATCH_DEMO") == "1":
        st.warning("示範模式：價格為模擬資料")

# ---------------- Main ----------------
st.title("📈 ETF Watch")
st.caption("個人持股觀察站 · 資料來源 Yahoo Finance，約有 15–20 分鐘延遲 · 不構成投資建議")

holdings = store.list()
if not holdings:
    st.info("還沒有持股。從左側新增第一筆，例如 0050 或 NVDA。")
    st.stop()

with st.spinner("抓取價格中…"):
    snap = load_snapshot(holdings, CachedProvider())

for symbol, msg in snap.errors.items():
    st.warning(f"{display_code(symbol)}：{msg}")

s = snap.summary
c1, c2, c3, c4 = st.columns(4)
c1.metric("總市值", fmt_twd(s.total_value_twd))
c2.metric("總成本", fmt_twd(s.total_cost_twd))
c3.metric("未實現損益", fmt_twd(s.pnl_twd), fmt_pct(s.pnl_pct))
if "USD" in snap.fx_to_twd:
    c4.metric("美元匯率", f"{snap.fx_to_twd['USD']:.3f}")

# ---------------- Holdings table + allocation ----------------
left, right = st.columns([3, 2])
with left:
    st.subheader("持股明細")
    rows = []
    for p in snap.positions:
        h = p.holding
        t = snap.trends[h.symbol]
        rows.append(
            {
                "代號": display_code(h.symbol),
                "股數": h.shares,
                "成本": h.avg_cost,
                "現價": p.price,
                "幣別": h.currency,
                "市值(TWD)": round(p.value_twd),
                "損益(TWD)": round(p.pnl_twd),
                "報酬率": fmt_pct(p.pnl_pct),
                "近1月": fmt_pct(t.returns["1m"]),
                "趨勢": t.trend,
                "備註": h.note,
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

with right:
    st.subheader("配置比例")
    if s.weights:
        wdf = pd.DataFrame(
            {"代號": [display_code(k) for k in s.weights], "比例": list(s.weights.values())}
        )
        donut = (
            alt.Chart(wdf)
            .mark_arc(innerRadius=60)
            .encode(
                theta="比例:Q",
                color=alt.Color("代號:N", legend=alt.Legend(orient="bottom")),
                tooltip=["代號", alt.Tooltip("比例:Q", format=".1%")],
            )
            .properties(height=280)
        )
        st.altair_chart(donut, use_container_width=True)

# ---------------- Edit / delete ----------------
with st.expander("編輯或刪除持股"):
    labels = {h.id: f"#{h.id}  {display_code(h.symbol)} · {h.shares:g} 股 · {h.note}" for h in holdings}
    selected_id = st.selectbox("選擇持股", options=list(labels), format_func=labels.get)
    current = next(h for h in holdings if h.id == selected_id)
    with st.form("edit_form"):
        e_shares = st.number_input("股數", min_value=0.0, value=float(current.shares), format="%.4f")
        e_cost = st.number_input("平均成本", min_value=0.0, value=float(current.avg_cost), format="%.2f")
        e_note = st.text_input("備註", value=current.note)
        col_a, col_b = st.columns(2)
        save = col_a.form_submit_button("儲存變更", use_container_width=True)
        remove = col_b.form_submit_button("刪除這筆", type="primary", use_container_width=True)
    if save:
        try:
            store.update(Holding(current.symbol, e_shares, e_cost, e_note, id=current.id))
            st.rerun()
        except (ValueError, KeyError) as exc:
            st.error(str(exc))
    if remove:
        store.delete(current.id)
        st.rerun()

# ---------------- Per-symbol trend ----------------
st.subheader("走勢")
symbols = list(snap.histories)
for tab, symbol in zip(st.tabs([display_code(x) for x in symbols]), symbols):
    with tab:
        closes = snap.histories[symbol]
        t = snap.trends[symbol]
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("最新價", f"{t.last_price:,.2f}")
        m2.metric("近1週", fmt_pct(t.returns["1w"]))
        m3.metric("近1月", fmt_pct(t.returns["1m"]))
        m4.metric("近3月", fmt_pct(t.returns["3m"]))
        m5.metric("最大回撤", f"{t.max_drawdown:.1%}", t.trend, delta_color="off")
        df = pd.DataFrame(
            {
                "收盤價": closes,
                "MA20": moving_average(closes, 20),
                "MA60": moving_average(closes, 60),
            }
        ).reset_index(names="日期")
        long = df.melt("日期", var_name="線", value_name="價格").dropna()
        line = (
            alt.Chart(long)
            .mark_line()
            .encode(
                x="日期:T",
                y=alt.Y("價格:Q", scale=alt.Scale(zero=False)),
                color=alt.Color("線:N", legend=alt.Legend(orient="top")),
                strokeDash=alt.condition(
                    alt.datum.線 == "收盤價", alt.value([1, 0]), alt.value([4, 3])
                ),
                tooltip=["日期:T", "線:N", alt.Tooltip("價格:Q", format=",.2f")],
            )
            .properties(height=320)
        )
        st.altair_chart(line, use_container_width=True)
