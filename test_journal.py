"""
test_journal.py — regression-тесты для journal.py

Фикстура temp_db (autouse) подменяет journal.DB_FILE на временный файл перед
КАЖДЫМ тестом, чтобы прогон тестов не писал мусорные записи (TESTUSDT и т.п.)
в боевой trades.db. Без этого /статистика и /позиции в Telegram начинают
показывать тестовые сделки вперемешку с реальными.
"""
import pytest
import journal


@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test_trades.db"
    monkeypatch.setattr(journal, "DB_FILE", str(db_file))
    journal._init_db()
    yield


def test_add_and_close_trade_cycle():
    t = journal.add_trade(symbol="TESTUSDT", side="Buy", entry=1.0, sl=0.9,
                           tp=1.3, qty=1, risk_pct=1.0, leverage=10, rr=3.0, mode="demo")
    assert t["status"] == "OPEN"
    closed = journal.close_trade("TESTUSDT", close_price=1.3, pnl=0.3, deposit=1000)
    assert closed["result"] == "WIN"


def test_format_stats_does_not_crash_on_empty_or_mixed_data():
    result = journal.format_stats()
    assert isinstance(result, str)


def test_format_open_trades_does_not_crash():
    result = journal.format_open_trades()
    assert isinstance(result, str)


def test_tests_do_not_pollute_real_db():
    journal.add_trade(symbol="ISOLATIONUSDT", side="Buy", entry=1.0, sl=0.9,
                       tp=1.1, qty=1, risk_pct=1.0, leverage=10, rr=1.0, mode="demo")
    assert journal.count_trades_today() >= 1
    assert "trades.db" in journal.DB_FILE and str(journal.DB_FILE) != "trades.db"
