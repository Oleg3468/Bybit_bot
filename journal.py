"""
journal.py v2 — Торговый журнал
Хранит сделки в JSON. Считает дневные лимиты.
"""
from __future__ import annotations
import json, logging, os
from datetime import datetime, timezone
from typing import Optional

logger      = logging.getLogger(__name__)
JOURNAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades.json")

def _load() -> list[dict]:
    if not os.path.exists(JOURNAL_FILE):
        return []
    try:
        with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Journal load error: {e}")
        return []

def _save(trades: list[dict]):
    try:
        with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
            json.dump(trades, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Journal save error: {e}")

def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def count_trades_today() -> int:
    today = _today_str()
    return sum(1 for t in _load() if t.get("date") == today)

def count_losing_trades_today() -> int:
    today = _today_str()
    return sum(1 for t in _load() if t.get("date") == today and t.get("result") == "LOSS")

def daily_net_pnl() -> float:
    today = _today_str()
    return sum(t.get("pnl", 0) for t in _load() if t.get("date") == today and t.get("status") == "CLOSED")

def add_trade(symbol, side, entry, sl, tp, qty, risk_pct, leverage, rr, mode, order_id="", session="") -> dict:
    trades = _load()
    trade  = {
        "id":          len(trades) + 1,
        "symbol":      symbol,
        "side":        side,
        "entry":       entry,
        "sl":          sl,
        "tp":          tp,
        "qty":         qty,
        "risk_pct":    risk_pct,
        "leverage":    leverage,
        "rr":          round(rr, 2),
        "mode":        mode,
        "order_id":    order_id,
        "session":     session,
        "status":      "OPEN",
        "result":      "",
        "close_price": 0.0,
        "pnl":         0.0,
        "pnl_pct":     0.0,
        "date":        _today_str(),
        "opened_at":   datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "closed_at":   "",
    }
    trades.append(trade)
    _save(trades)
    logger.info(f"📝 Добавлена сделка #{trade['id']} {symbol} {side}")
    return trade

def close_trade(symbol: str, close_price: float, pnl: float, deposit: float = 1000, result: str = "") -> Optional[dict]:
    trades = _load()
    trade  = None
    for t in reversed(trades):
        if t["symbol"] == symbol and t["status"] == "OPEN":
            trade = t
            break
    if not trade:
        return None

    trade["status"]      = "CLOSED"
    trade["close_price"] = close_price
    trade["pnl"]         = round(pnl, 4)
    trade["pnl_pct"]     = round(pnl / deposit * 100, 2) if deposit else 0
    trade["closed_at"]   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    trade["result"]      = result if result else ("WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BE")
    _save(trades)
    logger.info(f"📝 Закрыта сделка #{trade['id']} {symbol} PnL={pnl:+.4f}")
    return trade

def format_open_trades() -> str:
    trades = [t for t in _load() if t["status"] == "OPEN"]
    if not trades:
        return "📋 *Журнал пуст* — нет открытых сделок"
    lines = [f"📋 *Открытые сделки* ({len(trades)})\n{'─'*28}"]
    for t in trades:
        side_emoji = "🟢" if t["side"] == "Buy" else "🔴"
        lines.append(
            f"{side_emoji} #{t['id']} *{t['symbol']}*\n"
            f"  Entry: `{t['entry']}` | Qty: `{t['qty']}`\n"
            f"  SL: `{t['sl'] or '—'}` | TP: `{t['tp'] or '—'}`\n"
            f"  RR: `1:{t['rr']}` | {t['opened_at']}"
        )
    return "\n\n".join(lines)

def format_stats(n: int = 0) -> str:
    all_trades = _load()
    closed     = [t for t in all_trades if t["status"] == "CLOSED"]
    if not closed:
        return "📊 *Статистика*\nЗакрытых сделок нет"
    if n > 0:
        closed = closed[-n:]
    total     = len(closed)
    wins      = sum(1 for t in closed if t["result"] == "WIN")
    losses    = sum(1 for t in closed if t["result"] == "LOSS")
    win_rate  = wins / total * 100 if total else 0
    total_pnl = sum(t["pnl"] for t in closed)
    avg_rr    = sum(t["rr"] for t in closed) / total if total else 0
    gross_profit = sum(t["pnl"] for t in closed if t["pnl"] > 0)
    gross_loss   = abs(sum(t["pnl"] for t in closed if t["pnl"] < 0))
    pf           = gross_profit / gross_loss if gross_loss else float("inf")
    pnl_emoji    = "🟢" if total_pnl >= 0 else "🔴"
    wr_emoji     = "✅" if win_rate >= 50 else "⚠️"

    # Дневная статистика
    today_pnl    = daily_net_pnl()
    trades_today = count_trades_today()
    losses_today = count_losing_trades_today()

    period = f"последние {n}" if n else "все"
    return (
        f"📊 *Статистика* ({period})\n{'─'*28}\n"
        f"Всего: `{total}` | {wr_emoji} WinRate: `{win_rate:.1f}%`\n"
        f"W: `{wins}` | L: `{losses}`\n"
        f"{'─'*28}\n"
        f"{pnl_emoji} PnL: `{total_pnl:+.2f}` USDT\n"
        f"Profit Factor: `{pf:.2f}`\n"
        f"Средний RR: `1:{avg_rr:.2f}`\n"
        f"{'─'*28}\n"
        f"*Сегодня:*\n"
        f"Сделок: `{trades_today}/5` | Убытков: `{losses_today}/2`\n"
        f"PnL сегодня: `{today_pnl:+.2f}` USDT\n"
        f"Открытых: `{len([t for t in all_trades if t['status'] == 'OPEN'])}`"
    )