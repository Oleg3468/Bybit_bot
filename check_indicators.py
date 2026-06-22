"""
check_indicators.py — быстрая проверка full_indicator_analysis() на нескольких
монетах/таймфреймах.
"""
from dotenv import load_dotenv
load_dotenv()
import os
import pandas as pd
from trade_engine import BybitEngine
from indicators import full_indicator_analysis

engine = BybitEngine(os.getenv('BYBIT_DEMO_KEY', ''), os.getenv('BYBIT_DEMO_SECRET', ''), mode='demo')

symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
intervals = ["15", "60", "240"]

print(f"{'Symbol':10s} {'TF':4s} {'Dir':6s} {'Conf':6s} {'Bull':5s} {'Bear':5s} "
      f"{'Struct':9s} {'Extrem':9s} {'Vertex5':9s} {'V5_t1':6s} {'V5_t2':6s} "
      f"{'Torgun':12s} {'Diverg':10s}")
print("-" * 110)

for symbol in symbols:
    for interval in intervals:
        try:
            klines = engine.get_klines(symbol, interval=interval, limit=200)
            df = pd.DataFrame(klines)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['close'] = df['close'].astype(float)

            r = full_indicator_analysis(df)

            print(f"{symbol:10s} {interval:4s} {r['direction']:6s} {r['confidence']:<6.2f} "
                  f"{r['bull_score']:<5d} {r['bear_score']:<5d} "
                  f"{r['structure']:9s} {r['extremum']:9s} {r['vertex5_dir']:9s} "
                  f"{r['vertex5_trend1']:<6d} {r['vertex5_trend2']:<6d} "
                  f"{r['torgun_sig']:12s} {str(r['divergence']):10s}")
        except Exception as e:
            print(f"{symbol:10s} {interval:4s} ОШИБКА: {e}")

print("\nНа что смотреть:")
print("- Direction/Structure/Vertex5 не должны быть ОДНИМ И ТЕМ ЖЕ значением")
print("  на всех 15 строках подряд (если так — индикатор не реагирует на данные).")
print("- Confidence не должен быть всегда 1.0 или всегда 0 — должен варьироваться.")
print("- Бычьи/медвежьи сигналы должны примерно соответствовать видимому тренду")
print("  (если знаешь, что BTC сейчас падает — Direction чаще должен быть Sell).")