"""
config.py — именованные константы стратегии и автотрейдера.
"""

# --- Order Block: насколько цена должна быть близко к OB
OB_MAX_DISTANCE_PCT = 0.08

# --- Стоп-лосс: буфер за телом Order Block
BULLISH_SL_BUFFER_PCT = 0.999   
BEARISH_SL_BUFFER_PCT = 1.001   

# --- Тейк-профит: запасная цель
BULLISH_TP_FALLBACK_PCT = 1.005   
BEARISH_TP_FALLBACK_PCT = 0.995   

# --- Минимальное приемлемое соотношение риск/прибыль
# Было 1.0 — это ошибка, при RR=1 комиссия Bybit съест весь профит.
MIN_RR = 1.5

# --- Автотрейдер: сканирование рынка
SCAN_INTERVAL_SEC = 15 * 60     
IDLE_POLL_SEC = 5               

# --- Дедупликация сигналов
SIGNAL_DEDUP_SEC = 15 * 60





