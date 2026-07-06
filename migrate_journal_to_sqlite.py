"""
migrate_journal_to_sqlite.py — разовый перенос trades.json -> trades.db
Запустить один раз ПОСЛЕ замены journal.py на SQLite-версию и ДО первого
запуска bot.py: python3 migrate_journal_to_sqlite.py
"""
import json, os, sqlite3
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(BASE, "trades.json")
DB_FILE = os.path.join(BASE, "trades.db")


def normalize(t: dict) -> dict:
    is_old_schema = "coin" in t or "direction" in t
    if is_old_schema:
        symbol = t.get("coin", "UNKNOWN")
        side = "Buy" if str(t.get("direction", "")).lower() in ("long", "buy") else "Sell"
        sl = t.get("stop_loss"); tp = t.get("take_profit"); qty = t.get("qty")
        raw_result = str(t.get("result", "")).lower()
        status = "OPEN" if raw_result == "open" else "CLOSED"
        result = "" if status == "OPEN" else raw_result.upper()
    else:
        symbol = t.get("symbol", "UNKNOWN")
        side = t.get("side", "Buy")
        sl = t.get("sl"); tp = t.get("tp"); qty = t.get("qty")
        status = t.get("status", "OPEN")
        result = t.get("result", "")

    date_raw = t.get("date", "")
    date_only = date_raw[:10] if date_raw else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    opened_at = date_raw if len(date_raw) > 10 else f"{date_only} 00:00"

    return {
        "symbol": symbol, "side": side, "entry": t.get("entry", 0.0) or 0.0,
        "sl": sl, "tp": tp, "qty": qty,
        "risk_pct": t.get("risk_pct"), "leverage": t.get("leverage"),
        "rr": t.get("rr", 0.0) or 0.0, "mode": t.get("mode", ""),
        "order_id": t.get("order_id", ""), "session": t.get("session", ""),
        "status": status, "result": result,
        "close_price": t.get("close_price", 0.0) or 0.0,
        "pnl": t.get("pnl", 0.0) or 0.0, "pnl_pct": t.get("pnl_pct", 0.0) or 0.0,
        "date": date_only, "opened_at": opened_at, "closed_at": t.get("closed_at", ""),
    }


def main():
    if not os.path.exists(JSON_FILE):
        print("trades.json не найден — миграция не нужна.")
        return
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        raw_trades = json.load(f)
    print(f"Найдено {len(raw_trades)} записей в trades.json")
    import journal  # noqa: F401
    conn = sqlite3.connect(DB_FILE)
    inserted = 0
    for raw in raw_trades:
        row = normalize(raw)
        conn.execute(
            """INSERT INTO trades
               (symbol, side, entry, sl, tp, qty, risk_pct, leverage, rr, mode,
                order_id, session, status, result, close_price, pnl, pnl_pct,
                date, opened_at, closed_at)
               VALUES (:symbol,:side,:entry,:sl,:tp,:qty,:risk_pct,:leverage,:rr,
                       :mode,:order_id,:session,:status,:result,:close_price,
                       :pnl,:pnl_pct,:date,:opened_at,:closed_at)""",
            row,
        )
        inserted += 1
    conn.commit(); conn.close()
    backup_name = JSON_FILE + ".migrated.bak"
    os.rename(JSON_FILE, backup_name)
    print(f"Перенесено {inserted} сделок в trades.db")
    print(f"trades.json переименован в {os.path.basename(backup_name)}")


if __name__ == "__main__":
    main()
