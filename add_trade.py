"""
add_trade.py — ручное добавление тестовой сделки в журнал.
Использует journal.add_trade(), чтобы не создавать несовместимую со схемой запись
(раньше скрипт писал напрямую в trades.json со своими полями — coin/direction/
take_profit и т.д., что ломало format_open_trades()/format_stats()).
"""
import journal

trade = journal.add_trade(
    symbol="ADAUSDT",
    side="Buy",
    entry=0.246,
    sl=0.2434,
    tp=0.2486,
    qty=810,
    risk_pct=1.0,
    leverage=20,
    rr=1.7,
    mode="demo",
    session="Europe",
)
print("Сделка сохранена:", trade)
