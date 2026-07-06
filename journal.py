"""
journal.py v3 — Торговый журнал (SQLite)

Публичный API идентичен v2 (JSON-версии), поэтому bot.py / smc_strategy.py /
risk_manager.py менять не нужно:
    add_trade(...), close_trade(...), format_open_trades(), format_stats(n),
    count_trades_today(), count_losing_trades_today(), daily_net_pnl()

Почему SQLite вместо JSON:
- каждая запись/чтение больше не требует перечитывать и переписывать весь файл;
- атомарные транзакции — конкурентная запись из Telegram-хендлера и из
  автотрейдера больше не может повредить файл или потерять сделку;
- индексы по (symbol, status) и (date) — статистика считается без full-scan.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT NOT NULL,
    side         TEXT NOT NULL,
    entry        REAL NOT NULL,
    sl           REAL,
    tp           REAL,
    qty          REAL,
    risk_pct     REAL,
    leverage     REAL,
    rr           REAL,
    mode         TEXT,
    order_id     TEXT DEFAULT '',
    session      TEXT DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'OPEN',
    result       TEXT DEFAULT '',
    close_price  REAL DEFAULT 0,
    pnl          REAL DEFAULT 0,
    pnl_pct      REAL DEFAULT 0,
    date         TEXT NOT NULL,
    opened_at    TEXT NOT NULL,
    closed_at    TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_date   ON trades(date);
CREATE INDEX IF NOT EXISTS idx_trades_symbol_status ON trades(symbol, status);
"""


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _init_db():
    with _conn() as conn:
        conn.executescript(_SCHEMA)


_init_db()


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def count_trades_today() -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM trades WHERE date = ?", (_today_str(),)
        ).fetchone()
        return row["c"]


def count_losing_trades_today() -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM trades WHERE date = ? AND result = 'LOSS'",
            (_today_str(),),
        ).fetchone()
        return row["c"]


def daily_net_pnl() -> float:
    with _conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) AS s FROM trades "
            "WHERE date = ? AND status = 'CLOSED'",
            (_today_str(),),
        ).fetchone()
        return row["s"]


def add_trade(symbol, side, entry, sl, tp, qty, risk_pct, leverage, rr, mode,
              order_id="", session="") -> dict:
    now = datetime.now(timezone.utc)
    trade = {
        "symbol": symbol, "side": side, "entry": entry, "sl": sl, "tp": tp,
        "qty": qty, "risk_pct": risk_pct, "leverage": leverage,
        "rr": round(rr, 2), "mode": mode, "order_id": order_id, "session": session,
        "status": "OPEN", "result": "", "close_price": 0.0, "pnl": 0.0, "pnl_pct": 0.0,
        "date": now.strftime("%Y-%m-%d"), "opened_at": now.strftime("%Y-%m-%d %H:%M"),
        "closed_at": "",
    }
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO trades
               (symbol, side, entry, sl, tp, qty, risk_pct, leverage, rr, mode,
                order_id, session, status, result, close_price, pnl, pnl_pct,
                date, opened_at, closed_at)
               VALUES (:symbol,:side,:entry,:sl,:tp,:qty,:risk_pct,:leverage,:rr,
                       :mode,:order_id,:session,:status,:result,:close_price,
                       :pnl,:pnl_pct,:date,:opened_at,:closed_at)""",
            trade,
        )
        trade["id"] = cur.lastrowid
    logger.info(f"📝 Добавлена сделка #{trade['id']} {symbol} {side}")
    return trade


def close_trade(symbol: str, close_price: float, pnl: float, deposit: float = 1000,
                 result: str = "") -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM trades WHERE symbol = ? AND status = 'OPEN' "
            "ORDER BY id DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        if not row:
            return None

        pnl_pct = round(pnl / deposit * 100, 2) if deposit else 0
        result = result if result else ("WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BE")
        closed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

        conn.execute(
            """UPDATE trades SET status='CLOSED', close_price=?, pnl=?, pnl_pct=?,
               closed_at=?, result=? WHERE id=?""",
            (close_price, round(pnl, 4), pnl_pct, closed_at, result, row["id"]),
        )
        trade = dict(row)
        trade.update(status="CLOSED", close_price=close_price, pnl=round(pnl, 4),
                     pnl_pct=pnl_pct, closed_at=closed_at, result=result)
    logger.info(f"📝 Закрыта сделка #{trade['id']} {symbol} PnL={pnl:+.4f}")
    return trade


def format_open_trades() -> str:
    with _conn() as conn:
        trades = conn.execute(
            "SELECT * FROM trades WHERE status='OPEN' ORDER BY id"
        ).fetchall()
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
    with _conn() as conn:
        closed = conn.execute(
            "SELECT * FROM trades WHERE status='CLOSED' ORDER BY id"
        ).fetchall()
        open_count = conn.execute(
            "SELECT COUNT(*) AS c FROM trades WHERE status='OPEN'"
        ).fetchone()["c"]

    if not closed:
        return "📊 *Статистика*\nЗакрытых сделок нет"
    if n > 0:
        closed = closed[-n:]

    total     = len(closed)
    wins      = sum(1 for t in closed if t["result"] == "WIN")
    losses    = sum(1 for t in closed if t["result"] == "LOSS")
    win_rate  = wins / total * 100 if total else 0
    total_pnl = sum(t["pnl"] for t in closed)
    avg_rr    = sum((t["rr"] or 0) for t in closed) / total if total else 0
    gross_profit = sum(t["pnl"] for t in closed if t["pnl"] > 0)
    gross_loss   = abs(sum(t["pnl"] for t in closed if t["pnl"] < 0))
    pf           = gross_profit / gross_loss if gross_loss else float("inf")
    pnl_emoji    = "🟢" if total_pnl >= 0 else "🔴"
    wr_emoji     = "✅" if win_rate >= 50 else "⚠️"

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
        f"Открытых: `{open_count}`"
    )
