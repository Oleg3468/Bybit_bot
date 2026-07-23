"""
journal_audit.py — аудит trades.db перед тем, как обучать ML-модель на этих данных.

Проверяет:
1. Реальный (реализованный) R-мультипликатор по каждой закрытой сделке,
   в отличие от "rr" в БД, который является ПЛАНОВЫМ соотношением на
   момент открытия (см. signal.rr в smc_strategy.py) — отсюда и парадокс
   "средний RR 1:3.73 при Profit Factor 0.72" в /статистика.
2. Дубликаты сделок (одинаковый symbol+side+entry+opened_at, либо
   повторяющийся непустой order_id) — привет миграции из JSON.
3. Нестыковки result vs pnl (result='WIN' при pnl<=0 и наоборот).
4. Сделки без sl (нельзя посчитать реализованный R).

Запуск:
    python3 journal_audit.py
Ничего не пишет в БД — только читает и печатает отчёт.
Дополнительно сохраняет trades_audited.csv с реальным R по каждой сделке —
пригодится как чистый датасет для будущего train_classifier.py.
"""
from __future__ import annotations
import csv
import os
import sqlite3
from collections import defaultdict

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades.db")


def realized_r(side: str, entry: float, sl: float, close_price: float) -> float | None:
    """Реальный R-мультипликатор: сколько единиц риска реально заработали/потеряли.
    +1.0 значит "заработали ровно столько же, сколько было риска", -1.0 значит
    "потеряли ровно весь запланированный риск" (классический стоп)."""
    if not sl or entry == sl:
        return None
    risk = abs(entry - sl)
    if risk == 0:
        return None
    if side == "Buy":
        return (close_price - entry) / risk
    else:  # Sell
        return (entry - close_price) / risk


def main():
    if not os.path.exists(DB_FILE):
        print(f"❌ Не найден {DB_FILE}. Запускай скрипт из папки бота (~/bybit_bot).")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM trades WHERE status='CLOSED' ORDER BY id"
    ).fetchall()
    conn.close()

    if not rows:
        print("Закрытых сделок нет — аудировать нечего.")
        return

    total = len(rows)
    print(f"Всего закрытых сделок: {total}\n")

    # --- 1. Дубликаты ---
    seen_key = defaultdict(list)
    seen_orderid = defaultdict(list)
    for t in rows:
        key = (t["symbol"], t["side"], round(t["entry"], 6), t["opened_at"])
        seen_key[key].append(t["id"])
        if t["order_id"]:
            seen_orderid[t["order_id"]].append(t["id"])

    dup_keys = {k: ids for k, ids in seen_key.items() if len(ids) > 1}
    dup_orderids = {k: ids for k, ids in seen_orderid.items() if len(ids) > 1}

    print("=" * 50)
    print("1. ДУБЛИКАТЫ")
    print("=" * 50)
    if not dup_keys and not dup_orderids:
        print("✅ Дубликатов не найдено (ни по symbol+side+entry+opened_at, ни по order_id)")
    else:
        if dup_keys:
            print(f"⚠️  Найдено {len(dup_keys)} групп с одинаковым symbol+side+entry+opened_at:")
            for key, ids in list(dup_keys.items())[:10]:
                print(f"   {key} -> id {ids}")
        if dup_orderids:
            print(f"⚠️  Найдено {len(dup_orderids)} повторяющихся order_id:")
            for oid, ids in list(dup_orderids.items())[:10]:
                print(f"   order_id={oid} -> id {ids}")
    print()

    # --- 2. Нестыковки result vs pnl ---
    print("=" * 50)
    print("2. НЕСТЫКОВКИ result vs pnl")
    print("=" * 50)
    mismatches = []
    for t in rows:
        pnl = t["pnl"] or 0
        result = t["result"]
        expected = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BE")
        if result and result != expected:
            mismatches.append((t["id"], t["symbol"], pnl, result, expected))
    if not mismatches:
        print("✅ Все result соответствуют знаку pnl")
    else:
        print(f"⚠️  Найдено {len(mismatches)} несостыковок:")
        for m in mismatches[:15]:
            print(f"   id={m[0]} {m[1]} pnl={m[2]:+.2f} result={m[3]!r} (ожидался {m[4]!r})")
    print()

    # --- 3. Сделки без sl ---
    print("=" * 50)
    print("3. СДЕЛКИ БЕЗ SL (нельзя посчитать реализованный R)")
    print("=" * 50)
    no_sl = [t["id"] for t in rows if not t["sl"]]
    if not no_sl:
        print("✅ У всех закрытых сделок есть sl")
    else:
        print(f"⚠️  {len(no_sl)} сделок без sl: id {no_sl[:20]}{' ...' if len(no_sl) > 20 else ''}")
    print()

    # --- 4. Реальная статистика на основе realized R, а не planned rr ---
    print("=" * 50)
    print("4. РЕАЛЬНАЯ СТАТИСТИКА (реализованный R, не плановый)")
    print("=" * 50)

    audited = []
    for t in rows:
        r = realized_r(t["side"], t["entry"], t["sl"], t["close_price"])
        audited.append({**dict(t), "realized_r": r})

    valid = [a for a in audited if a["realized_r"] is not None]
    skipped = total - len(valid)

    wins = sum(1 for a in valid if a["pnl"] > 0)
    losses = sum(1 for a in valid if a["pnl"] < 0)
    win_rate = wins / len(valid) * 100 if valid else 0

    gross_profit = sum(a["pnl"] for a in valid if a["pnl"] > 0)
    gross_loss = abs(sum(a["pnl"] for a in valid if a["pnl"] < 0))
    pf = gross_profit / gross_loss if gross_loss else float("inf")

    avg_realized_r = sum(a["realized_r"] for a in valid) / len(valid) if valid else 0
    avg_planned_rr = sum((a["rr"] or 0) for a in valid) / len(valid) if valid else 0

    print(f"Сделок учтено: {len(valid)} (пропущено без sl: {skipped})")
    print(f"WinRate: {win_rate:.1f}% | W: {wins} | L: {losses}")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Средний ПЛАНОВЫЙ RR (как в /статистика): 1:{avg_planned_rr:.2f}")
    print(f"Средний РЕАЛИЗОВАННЫЙ R (реальный исход): {avg_realized_r:+.2f}")
    print()
    print("Если РЕАЛИЗОВАННЫЙ R сильно ниже ПЛАНОВОГО — это нормально и ожидаемо:")
    print("большинство сделок не долетает до тейка. Именно поэтому для ML нужно")
    print("использовать realized_r как целевую переменную, а не поле rr из БД.")
    print()

    # --- 5. Экспорт для будущего train_classifier.py ---
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades_audited.csv")
    fieldnames = ["id", "symbol", "side", "entry", "sl", "tp", "close_price",
                  "pnl", "result", "rr", "realized_r", "session", "mode",
                  "opened_at", "closed_at"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for a in audited:
            writer.writerow(a)

    print("=" * 50)
    print(f"✅ Экспортирован чистый датасет: {out_path}")
    print("=" * 50)


if __name__ == "__main__":
    main()