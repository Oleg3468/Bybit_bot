"""
indicators.py — портированные MT4 индикаторы для Bybit бота
1. Fractals_Trend  — свинг хай/лоу (фракталы)
2. Extremum        — экстремумы цены
3. Super_ATR       — ATR + сигнальная линия
4. Torgun_Profit   — T3 осциллятор momentum/дивергенции
"""
import numpy as np
import pandas as pd
from typing import Optional

# ─── 1. FRACTALS ──────────────────────────────────────────────────────────────
def fractals(high: pd.Series, low: pd.Series, period: int = 10) -> tuple:
    """
    Fractals_Trend: определяет свинг хай и свинг лоу.
    period должен быть нечётным.
    Возвращает (swing_highs, swing_lows) — Series с ценами или NaN.
    """
    if period % 2 == 0:
        period += 1
    half = period // 2

    n = len(high)
    swing_highs = pd.Series(np.nan, index=high.index)
    swing_lows  = pd.Series(np.nan, index=low.index)

    for i in range(half, n - half):
        # Свинг хай
        h = high.iloc[i]
        if all(high.iloc[i-k] < h for k in range(1, half+1)) and \
           all(high.iloc[i+k] < h for k in range(1, half+1)):
            swing_highs.iloc[i] = h

        # Свинг лоу
        l = low.iloc[i]
        if all(low.iloc[i-k] > l for k in range(1, half+1)) and \
           all(low.iloc[i+k] > l for k in range(1, half+1)):
            swing_lows.iloc[i] = l

    return swing_highs, swing_lows


def get_last_swings(high: pd.Series, low: pd.Series, period: int = 10, n: int = 3):
    """
    Возвращает последние n свинг хаёв и лоёв.
    """
    sh, sl = fractals(high, low, period)
    highs = sh.dropna().tail(n).values.tolist()
    lows  = sl.dropna().tail(n).values.tolist()
    return highs, lows


# ─── 2. EXTREMUM ──────────────────────────────────────────────────────────────
def extremum(high: pd.Series, low: pd.Series, nbars: int = 20) -> pd.Series:
    """
    Extremum: мера экстремальности текущей свечи.
    n = расстояние от максимума до минимума в диапазоне nbars.
    Положительное → бычий экстремум, отрицательное → медвежий.
    """
    n_total = len(high)
    result = pd.Series(0.0, index=high.index)

    for k in range(n_total):
        end = min(k + nbars, n_total)
        window_h = high.iloc[k:end]
        window_l = low.iloc[k:end]

        h_k = high.iloc[k]
        l_k = low.iloc[k]

        # n = макс расстояние вверх от текущего хая
        n_val = 0.0
        for h in window_h:
            if h_k > h and h_k - h > n_val:
                n_val = h_k - h

        # m = макс расстояние вниз от текущего лоу
        m_val = 0.0
        for l in window_l:
            if l_k < l and l_k - l < m_val:
                m_val = l_k - l

        result.iloc[k] = n_val + m_val  # положит = бычий, отриц = медвежий

    return result


def extremum_signal(high: pd.Series, low: pd.Series, nbars: int = 20) -> str:
    """
    Возвращает 'bullish', 'bearish' или 'neutral' по последнему значению.
    """
    ext = extremum(high, low, nbars)
    last = ext.iloc[-1]
    if last > 0:
        return "bullish"
    elif last < 0:
        return "bearish"
    return "neutral"


# ─── 3. SUPER ATR ─────────────────────────────────────────────────────────────
def super_atr(high: pd.Series, low: pd.Series, close: pd.Series,
              atr_period: int = 14, signal_period: int = 6) -> dict:
    """
    Super_ATR: ATR + сигнальная линия (MA от ATR).
    Возвращает dict с:
      - atr: Series
      - signal: Series (MA от ATR)
      - trend: 'up' если ATR > Signal (растущая волатильность), иначе 'down'
      - sl_multiplier: множитель для стоп-лосса
    """
    # True Range
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs()
    ], axis=1).max(axis=1)

    atr    = tr.rolling(atr_period).mean()
    signal = atr.rolling(signal_period).mean()
    diff   = atr - signal

    trend = "up" if diff.iloc[-1] > 0 else "down"

    # Динамический SL: ATR * 1.5 (стандарт ICT)
    sl_mult = 1.5

    return {
        "atr":        atr,
        "signal":     signal,
        "diff":       diff,
        "trend":      trend,
        "current_atr": atr.iloc[-1],
        "sl_distance": atr.iloc[-1] * sl_mult,
    }


def dynamic_sl_tp(entry: float, side: str, atr_val: float,
                  sl_mult: float = 1.5, rr: float = 2.0) -> tuple:
    """
    Рассчитывает SL и TP на основе ATR.
    side: 'Buy' или 'Sell'
    Возвращает (sl, tp)
    """
    sl_dist = atr_val * sl_mult
    tp_dist = sl_dist * rr

    if side == "Buy":
        sl = round(entry - sl_dist, 4)
        tp = round(entry + tp_dist, 4)
    else:
        sl = round(entry + sl_dist, 4)
        tp = round(entry - tp_dist, 4)

    return sl, tp


# ─── 4. TORGUN PROFIT (T3 осциллятор) ────────────────────────────────────────
def t3_oscillator(close: pd.Series, period: int = 27,
                  additionally: int = 4, try_val: float = 0.5) -> pd.Series:
    """
    Torgun_Profit: T3-сглаженный осциллятор отклонения цены от средней.
    Значения около +130 = перекупленность, -130 = перепроданность.
    """
    a = try_val
    ots = -a**3
    loz =  3*(a**2 + a**3)
    yik = -3*(2*a**2 + a + a**3)
    tad =  1 + 3*a + a**3 + 3*a**2

    tpls = 2.0 / (1.0 + additionally)

    n = len(close)
    prices = close.values.astype(float)

    # Вычисляем отклонение от средней
    nastr = np.zeros(n)
    dolm  = np.zeros((n, 6))

    for i in range(n):
        start = max(0, i - period + 1)
        window = prices[start:i+1]
        avg = window.mean()
        dev = np.abs(window - avg).mean()

        raw = (prices[i] - avg) / (0.015 * dev) if dev != 0 else 0.0

        # T3 smoothing
        if i == 0:
            dolm[i] = raw
        else:
            dolm[i][0] = dolm[i-1][0] + tpls*(raw        - dolm[i-1][0])
            dolm[i][1] = dolm[i-1][1] + tpls*(dolm[i][0] - dolm[i-1][1])
            dolm[i][2] = dolm[i-1][2] + tpls*(dolm[i][1] - dolm[i-1][2])
            dolm[i][3] = dolm[i-1][3] + tpls*(dolm[i][2] - dolm[i-1][3])
            dolm[i][4] = dolm[i-1][4] + tpls*(dolm[i][3] - dolm[i-1][4])
            dolm[i][5] = dolm[i-1][5] + tpls*(dolm[i][4] - dolm[i-1][5])

        nastr[i] = ots*dolm[i][5] + loz*dolm[i][4] + yik*dolm[i][3] + tad*dolm[i][2]

    return pd.Series(nastr, index=close.index)


def torgun_signal(close: pd.Series, period: int = 27) -> dict:
    """
    Возвращает сигнал Torgun_Profit:
      - value: текущее значение
      - signal: 'overbought' / 'oversold' / 'neutral'
      - divergence: 'bullish' / 'bearish' / None
    """
    t3 = t3_oscillator(close, period)
    val = t3.iloc[-1]

    if val > 130:
        sig = "overbought"
    elif val < -130:
        sig = "oversold"
    else:
        sig = "neutral"

    # Дивергенция: цена растёт, осциллятор падает = медвежья
    div = None
    if len(t3) >= 5:
        price_trend = close.iloc[-1] > close.iloc[-5]
        t3_trend    = t3.iloc[-1]    > t3.iloc[-5]
        if price_trend and not t3_trend:
            div = "bearish"
        elif not price_trend and t3_trend:
            div = "bullish"

    return {"value": val, "signal": sig, "divergence": div}


# ─── COMBINED ANALYSIS ────────────────────────────────────────────────────────
def full_indicator_analysis(df: pd.DataFrame) -> dict:
    """
    Запускает все 4 индикатора на DataFrame с колонками:
    open, high, low, close, volume
    Возвращает сводный анализ.
    """
    high  = df["high"]
    low   = df["low"]
    close = df["close"]

    # 1. Фракталы
    sh, sl = fractals(high, low, period=10)
    last_highs = sh.dropna().tail(3).values.tolist()
    last_lows  = sl.dropna().tail(3).values.tolist()

    # Структура рынка по фракталам
    structure = "neutral"
    if len(last_highs) >= 2 and len(last_lows) >= 2:
        if last_highs[-1] > last_highs[-2] and last_lows[-1] > last_lows[-2]:
            structure = "bullish"  # HH + HL
        elif last_highs[-1] < last_highs[-2] and last_lows[-1] < last_lows[-2]:
            structure = "bearish"  # LH + LL

    # 2. Экстремум
    ext_sig = extremum_signal(high, low, nbars=20)

    # 3. Super ATR
    atr_data = super_atr(high, low, close)

    # 4. Torgun
    torg = torgun_signal(close)

    # Общий сигнал
    # Vertex_5 (zero-lag T3 версия)
    v5 = vertex5(df)
    v5_trend1 = int(v5["trend1"].iloc[-1])
    v5_trend2 = int(v5["trend2"].iloc[-1])
    v5_dir = "bullish" if v5_trend1 == 1 else "bearish" if v5_trend1 == -1 else "neutral"

    bull_score = 0
    bear_score = 0

    if v5_trend1 == 1:    bull_score += 2
    if v5_trend1 == -1:   bear_score += 2
    if v5_trend2 == 1:    bull_score += 1
    if v5_trend2 == -1:   bear_score += 1

    if structure == "bullish":   bull_score += 2
    if structure == "bearish":   bear_score += 2
    if ext_sig == "bullish":     bull_score += 1
    if ext_sig == "bearish":     bear_score += 1
    if torg["signal"] == "oversold":    bull_score += 1
    if torg["signal"] == "overbought":  bear_score += 1
    if torg["divergence"] == "bullish": bull_score += 2
    if torg["divergence"] == "bearish": bear_score += 2

    total = bull_score + bear_score
    confidence = max(bull_score, bear_score) / total if total > 0 else 0

    direction = "Buy" if bull_score > bear_score else "Sell" if bear_score > bull_score else "flat"

    return {
        "direction":    direction,
        "confidence":   round(confidence, 2),
        "structure":    structure,
        "extremum":     ext_sig,
        "atr":          round(atr_data["current_atr"], 6),
        "sl_distance":  round(atr_data["sl_distance"], 6),
        "atr_trend":    atr_data["trend"],
        "torgun_val":   round(torg["value"], 2),
        "torgun_sig":   torg["signal"],
        "divergence":   torg["divergence"],
        "last_highs":   last_highs,
        "last_lows":    last_lows,
        "bull_score":   bull_score,
        "bear_score":   bear_score,
        "vertex5_dir":    v5_dir,
        "vertex5_trend1": v5_trend1,
        "vertex5_trend2": v5_trend2,
    }
def _t3_smooth(series, period: int = 5, additionally: int = 4, try_val: float = 0.5):
    """
    Базовый T3-сглаживатель (6-каскадный EMA, формула Tillson).
    Вынесен отдельно, чтобы переиспользовать в torgun_signal и в vertex5.
    """
    a = try_val
    ots = -a**3
    loz = 3*(a**2 + a**3)
    yik = -3*(2*a**2 + a + a**3)
    tad = 1 + 3*a + a**3 + 3*a**2

    tpls = 2.0 / (1.0 + additionally)

    n = len(series)
    prices = series.values.astype(float)
    dolm = np.zeros((n, 6))
    out = np.zeros(n)

    for i in range(n):
        if i == 0:
            dolm[i] = prices[i]
        else:
            dolm[i][0] = dolm[i-1][0] + tpls*(prices[i] - dolm[i-1][0])
            for k in range(1, 6):
                dolm[i][k] = dolm[i-1][k] + tpls*(dolm[i][k-1] - dolm[i-1][k])
        out[i] = ots*dolm[i][5] + loz*dolm[i][4] + yik*dolm[i][3] + tad*dolm[i][2]

    return pd.Series(out, index=series.index)


def vertex5(df: pd.DataFrame, control_period: int = 14, signal_period: int = 5,
            bb_period: int = 12, bb_dev: float = 2.0,
            level_ob: float = 6, level_os: float = -6,
            extreme_ob: float = 10, extreme_os: float = -10) -> dict:
    """
    Vertex_5: zero-lag версия (T3 вместо SMA для сигнальной линии и Bollinger Bands).
    """
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
    signal = _t3_smooth(raw_series, period=signal_period)

    bb_mid = signal.rolling(bb_period).mean()
    bb_std = signal.rolling(bb_period).std()
    band_up = bb_mid + bb_dev * bb_std
    band_dn = bb_mid - bb_dev * bb_std

    trend1 = pd.Series(0, index=df.index)
    trend1[signal > level_ob] = -1
    trend1[signal < level_os] = 1
    trend1 = trend1.replace(0, np.nan).ffill().fillna(0)

    trend2 = pd.Series(0, index=df.index)
    trend2[signal > extreme_ob] = -1
    trend2[signal < extreme_os] = 1
    trend2 = trend2.replace(0, np.nan).ffill().fillna(0)

    return {
        'raw': raw_series,
        'signal': signal,
        'band_up': band_up,
        'band_dn': band_dn,
        'trend1': trend1,
        'trend2': trend2,
    }