import pytest

from etfwatch.models import Holding
from etfwatch.storage import HoldingStore


@pytest.fixture
def store():
    s = HoldingStore(":memory:")
    yield s
    s.close()


def test_add_and_list(store):
    store.add(Holding("0050", 1000, 150.5, note="定期定額"))
    store.add(Holding("nvda", 0.5, 120))
    items = store.list()
    assert [h.symbol for h in items] == ["0050.TW", "NVDA"]
    assert items[0].id is not None
    assert items[0].note == "定期定額"
    assert items[1].shares == 0.5


def test_get_missing_returns_none(store):
    assert store.get(999) is None


def test_update(store):
    h = store.add(Holding("0050", 1000, 150))
    h.shares = 1500
    h.avg_cost = 160
    store.update(h)
    got = store.get(h.id)
    assert got.shares == 1500
    assert got.avg_cost == 160


def test_update_requires_existing_id(store):
    with pytest.raises(ValueError):
        store.update(Holding("0050", 1, 1))
    with pytest.raises(KeyError):
        store.update(Holding("0050", 1, 1, id=42))


def test_delete(store):
    h = store.add(Holding("0050", 1000, 150))
    store.delete(h.id)
    assert store.list() == []
    with pytest.raises(KeyError):
        store.delete(h.id)


def test_persists_to_file(tmp_path):
    db = tmp_path / "sub" / "p.db"
    s1 = HoldingStore(db)
    s1.add(Holding("0050", 10, 100))
    s1.close()
    s2 = HoldingStore(db)
    assert [h.symbol for h in s2.list()] == ["0050.TW"]
    s2.close()


from datetime import datetime


def test_briefings(store):
    assert store.latest_briefing() is None
    store.save_briefing("舊的", datetime(2026, 10, 20, 9, 0))
    store.save_briefing("新的", datetime(2026, 10, 27, 9, 0))
    when, content = store.latest_briefing()
    assert content == "新的"
    assert when == datetime(2026, 10, 27, 9, 0)
