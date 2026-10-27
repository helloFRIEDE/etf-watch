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
    assert len(at.tabs) == 2
