"""UI smoke tests with Streamlit's AppTest, using demo prices (no network)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from etfwatch.models import Holding
from etfwatch.storage import HoldingStore

APP = str(Path(__file__).resolve().parents[1] / "src" / "etfwatch" / "app.py")


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "ui.db"
    monkeypatch.setenv("ETFWATCH_DEMO", "1")
    monkeypatch.setenv("ETFWATCH_DB", str(db))
    # An empty value stops load_dotenv() from reading a real key out of .env,
    # so running the tests never calls (or bills) the OpenAI API.
    monkeypatch.setenv("OPENAI_API_KEY", "")
    return db


def run_app():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def test_empty_state(env):
    at = run_app()
    assert any("還沒有持股" in i.value for i in at.info)


def test_add_holding_via_form(env):
    at = run_app()
    at.text_input[0].set_value("0050")
    at.number_input[0].set_value(1000.0)
    at.number_input[1].set_value(150.0)
    at.button[0].click().run()
    assert not at.exception
    store = HoldingStore(env)
    assert [h.symbol for h in store.list()] == ["0050.TW"]
    store.close()


def test_dashboard_renders_with_holdings(env):
    s = HoldingStore(env)
    s.add(Holding("0050", 1000, 150))
    s.add(Holding("NVDA", 0.5, 120))
    s.close()
    at = run_app()
    labels = [m.label for m in at.metric]
    assert "總市值" in labels and "美元匯率" in labels
    tab_labels = [tab.label for tab in at.tabs]
    assert {"0050", "NVDA", "本週簡報", "問問 AI"} <= set(tab_labels)


def test_add_holding_with_total_cost(env):
    at = run_app()
    at.text_input[0].set_value("0050")
    at.number_input[0].set_value(1945.0)
    at.radio[0].set_value("總成本（券商 App 的付出成本）")
    at.number_input[1].set_value(108714.0)
    at.button[0].click().run()
    assert not at.exception
    store = HoldingStore(env)
    [h] = store.list()
    store.close()
    assert h.avg_cost == pytest.approx(108714 / 1945)


def test_warns_when_total_cost_entered_as_per_share(env):
    s = HoldingStore(env)
    s.add(Holding("0050", 1945, 108714))  # the mistake from the screenshot
    s.close()
    at = run_app()
    assert any("總成本" in w.value for w in at.warning)


def _seed(env):
    s = HoldingStore(env)
    s.add(Holding("0050", 1000, 150))
    s.close()


def _button(at, label):
    return next(b for b in at.button if b.label == label)


def test_generate_briefing_is_saved_and_reused(env):
    _seed(env)
    at = run_app()
    _button(at, "產生新簡報").click().run()
    assert not at.exception
    assert any("示範模式" in m.value for m in at.markdown)
    store = HoldingStore(env)
    assert store.latest_briefing() is not None
    store.close()
    # a fresh page load shows the saved briefing without clicking again
    at2 = run_app()
    assert any("示範模式" in m.value for m in at2.markdown)


def test_ask_question(env):
    _seed(env)
    at = run_app()
    q = next(t for t in at.text_input if t.label == "問題")
    q.set_value("0050 最近怎樣？")
    _button(at, "送出").click().run()
    assert not at.exception
    assert any("0050 最近怎樣？" in m.value for m in at.markdown)


def test_no_api_key_shows_setup_hint(env, monkeypatch):
    import etfwatch.llm

    _seed(env)
    monkeypatch.setattr(etfwatch.llm, "default_llm", lambda: None)
    at = run_app()
    assert any("OPENAI_API_KEY" in i.value for i in at.info)
