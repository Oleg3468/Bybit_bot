import journal

def test_add_and_close_trade_cycle():
    t = journal.add_trade(symbol="TESTUSDT", side="Buy", entry=1.0, sl=0.9,
                           tp=1.3, qty=1, risk_pct=1.0, leverage=10, rr=3.0, mode="demo")
    assert t["status"] == "OPEN"
    closed = journal.close_trade("TESTUSDT", close_price=1.3, pnl=0.3, deposit=1000)
    assert closed["result"] == "WIN"

def test_format_stats_does_not_crash_on_empty_or_mixed_data():
    # Регресс-тест на баг с KeyError на старых записях
    result = journal.format_stats()
    assert isinstance(result, str)

def test_format_open_trades_does_not_crash():
    result = journal.format_open_trades()
    assert isinstance(result, str)
