"""
retrospective_resize.py — «а что если бы сайзинг был риск-based с самого начала?»

Работает НА УЖЕ ГОТОВОМ trades_audited.csv (результат journal_audit.py),
где для каждой закрытой сделки посчитан честный realized_r — сколько
единиц риска реально принесла сделка, независимо от того, как был
посчитан объём в тот момент.

Идея пересчёта простая и математически точная:
    новый_pnl = realized_r * (депозит * risk_pct / 100)
Потому что именно так работает риск-based сайзинг по определению:
в убытке -1R теряешь ровно risk_pct% от депозита, в прибыли +3R —
получаешь ровно 3 * risk_pct% от депозита. Старый qty при этом
никак не участвует — берём только сам исход сделки (realized_r).

Не переигрывает ничего на бирже. Не трогает trades.db. Только читает
trades_audited.csv и печатает сравнение "было / было бы".

Запуск:
    python3 retrospective_resize.py
    python3 retrospective_resize.py --deposit 1000 --risk_pct 1.0
"""
from __future__ import annotations
import argparse
import csv
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deposit", type=float, default=1000.0)
    parser.add_argument("--risk_pct", type=float, default=1.0)
    args = parser.parse_args()

    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades_audited.csv")
    if not os.path.exists(csv_path):
        print(f"❌ Не найден {csv_path}. Сначала запусти journal_audit.py — он его создаёт.")
        return

    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)

    risk_usdt = args.deposit * (args.risk_pct / 100)

    old_pnls, new_pnls = [], []
    skipped = 0
    for r in rows:
        try:
            realized_r = float(r["realized_r"]) if r["realized_r"] not in ("", None) else None
            old_pnl = float(r["pnl"]) if r["pnl"] not in ("", None) else None
        except (ValueError, KeyError):
            realized_r, old_pnl = None, None

        if realized_r is None or old_pnl is None:
            skipped += 1
            continue

        old_pnls.append(old_pnl)
        new_pnls.append(realized_r * risk_usdt)

    if not old_pnls:
        print("Нет сделок с посчитанным realized_r — нечего сравнивать.")
        return

    def stats(pnls):
        total = sum(pnls)
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        pf = gross_profit / gross_loss if gross_loss else float("inf")
        wins = sum(1 for p in pnls if p > 0)
        win_rate = wins / len(pnls) * 100
        return total, pf, win_rate

    old_total, old_pf, old_wr = stats(old_pnls)
    new_total, new_pf, new_wr = stats(new_pnls)

    print(f"Сделок в сравнении: {len(old_pnls)} (пропущено без realized_r/pnl: {skipped})")
    print(f"Параметры риск-based пересчёта: депозит={args.deposit} USDT, риск={args.risk_pct}% "
          f"(= {risk_usdt:.2f} USDT на сделку)")
    print()
    print(f"{'':20}{'КАК БЫЛО':>15}{'КАК БЫЛО БЫ':>18}")
    print(f"{'PnL, USDT':20}{old_total:>+15.2f}{new_total:>+18.2f}")
    print(f"{'Profit Factor':20}{old_pf:>15.2f}{new_pf:>18.2f}")
    print(f"{'WinRate, %':20}{old_wr:>15.1f}{new_wr:>18.1f}")
    print()
    diff = new_total - old_total
    if diff > 0:
        print(f"✅ С риск-based сайзингом результат был бы на {diff:+.2f} USDT ЛУЧШЕ.")
    elif diff < 0:
        print(f"⚠️  С риск-based сайзингом результат был бы на {diff:+.2f} USDT хуже "
              f"(значит проблема не только в сайзинге).")
    else:
        print("Разницы нет — сайзинг и раньше был риск-based (или совпало случайно).")


if __name__ == "__main__":
    main()