import pytest

from etfwatch.symbols import currency_of, display_code, normalize_symbol


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("0050", "0050.TW"),
        (" 0050 ", "0050.TW"),
        ("00878", "00878.TW"),
        ("00679b", "00679B.TW"),
        ("0050.tw", "0050.TW"),
        ("6488.TWO", "6488.TWO"),
        ("nvda", "NVDA"),
        ("BRK-B", "BRK-B"),
    ],
)
def test_normalize_symbol(raw, expected):
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", None, "台積電", "AB.TW", "$$$"])
def test_normalize_symbol_rejects_garbage(raw):
    with pytest.raises(ValueError):
        normalize_symbol(raw)


def test_currency_of():
    assert currency_of("0050.TW") == "TWD"
    assert currency_of("6488.TWO") == "TWD"
    assert currency_of("NVDA") == "USD"


def test_display_code():
    assert display_code("0050.TW") == "0050"
    assert display_code("6488.TWO") == "6488"
    assert display_code("NVDA") == "NVDA"
