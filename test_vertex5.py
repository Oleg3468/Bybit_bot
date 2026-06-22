"""
test_vertex5.py — сравнение оригинального Vertex_5 (SMA+BB на сырых данных)
против zero-lag версии (T3+BB на сглаженной линии).
"""
import sys
from dotenv import load_dotenv
import os
load_dotenv()
import numpy as np
import pandas as pd

from trade_engine import BybitEngine
from indicators import vertex5, _t3_smooth  # noqa: F401


def vertex5_original(df: pd.DataFrame, control_period: int = 14, signal_period: int = 5,
                      bb_period: int = 12, bb_dev: float = 2.0,
                      level_ob: float = 6, level_os: float = -6) -> dict:
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    n = len(df)
    raw = np.zeros(n)

    for idx in range(n):
        start = max(0, idx - control_period + 1)
        window_high = high[start:idx+1]
        window_low = low[start:idx+1]
        window_close = close[start:idx+1]
        sum_up = 0.0
        sum_dn = 0.0
        trigger_high = -np.inf
        trigger_low = np.inf
        for j in range(len(window_high)):
            if window_high[j] > trigger_high:
                trigger_high = window_high[j]
                sum_up += window_close[j]
            if window_low[j] < trigger_low:
                trigger_low = window_low[j]
                sum_dn += window_close[j]
        if sum_dn != 0.0 and sum_up != 0.0:
            raw[idx] = sum_dn / sum_up - sum_up / sum_dn

    raw_series = pd.Series(raw, index=df.index)
    signal = raw_series.rolling(signal_period).mean()

    trend1 = pd.Series(0, index=df.index)
    trend1[signal > level_ob] = -1
    trend1[signal < level_os] = 1
    trend1 = trend1.replace(0, np.nan).ffill().fillna(0)

    return {'raw': raw_series, 'signal': signal, 'trend1': trend1}


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df['high'], df['low'], df['close']
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def count_flips(trend: pd.Series, mask: pd.Series) -> int:
    diffs = trend.diff().fillna(0) != 0
    return int((diffs & mask).sum())


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    interval = sys.argv[2] if len(sys.argv) > 2 else "15"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 300

    engine = BybitEngine(os.getenv("BYBIT_DEMO_KEY", ""), os.getenv("BYBIT_DEMO_SECRET", ""), mode="demo")
    klines = engine.get_klines(symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)

    print(f"Свечей загружено: {len(df)} | {symbol} {interval}m")

    atr = compute_atr(df, period=14)
    atr_mean = atr.rolling(50, min_periods=10).mean()
    trending_mask = (atr > atr_mean).fillna(False)
    flat_mask = (~trending_mask) & atr.notna()

    n_trend_bars = int(trending_mask.sum())
    n_flat_bars = int(flat_mask.sum())
    print(f"Трендовых баров (ATR выше своей MA): {n_trend_bars}")
    print(f"Флэтовых баров (ATR ниже своей MA):  {n_flat_bars}")
    print()

    orig = vertex5_original(df)
    new = vertex5(df)

    orig_flips_trend = count_flips(orig['trend1'], trending_mask)
    orig_flips_flat = count_flips(orig['trend1'], flat_mask)
    new_flips_trend = count_flips(new['trend1'], trending_mask)
    new_flips_flat = count_flips(new['trend1'], flat_mask)

    print("=" * 50)
    print(f"{'':20s} {'ОРИГИНАЛ (SMA)':>15s} {'НОВЫЙ (T3)':>15s}")
    print(f"{'Флипов в тренде:':20s} {orig_flips_trend:>15d} {new_flips_trend:>15d}")
    print(f"{'Флипов во флэте:':20s} {orig_flips_flat:>15d} {new_flips_flat:>15d}")
    print("=" * 50)

    if n_flat_bars > 0:
        orig_rate = orig_flips_flat / n_flat_bars * 100
        new_rate = new_flips_flat / n_flat_bars * 100
        print(f"\nЧастота ложных флипов во флэте:")
        print(f"  Оригинал: {orig_rate:.1f}% баров с переключением")
        print(f"  Новый:    {new_rate:.1f}% баров с переключением")
        if new_rate < orig_rate:
            improvement = (1 - new_rate/orig_rate) * 100 if orig_rate > 0 else 0
            print(f"  → Улучшение: -{improvement:.0f}% ложных сигналов во флэте")
        else:
            print(f"  → Улучшения не видно, нужно подстроить параметры")


if __name__ == "__main__":
    main()