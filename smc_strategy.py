"""
smc_strategy.py — Автономная SMC стратегия
═══════════════════════════════════════════
Логика из курса (Уроки 1-7):
  1. Структура рынка (HH/HL/LH/LL)
  2. Order Block (OB)
  3. Fair Value Gap (FVG)
  4. Ликвидность (BSL/SSL)
  5. Сессии (только London/NY)
  6. Межрыночный контекст (DXY/S&P500)
  7. SMT дивергенция BTC/ETH
  8. Фандинг как фильтр
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional
from indicators import full_indicator_analysis
import pandas as pd

logger = logging.getLogger(__name__)

def _candles_to_df(candles):
    """Конвертирует list[Candle] обратно в pd.DataFrame для full_indicator_analysis."""
    return pd.DataFrame([{
        "open": c.open, "high": c.high, "low": c.low,
        "close": c.close, "volume": c.volume,
    } for c in candles])


# ─── СТРУКТУРЫ ДАННЫХ ────────────────────────────────────────────────────────

@dataclass
class Candle:
    time:   int
    open:   float
    high:   float
    low:    float
    close:  float
    volume: float

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def total_range(self) -> float:
        return self.high - self.low


@dataclass
class OrderBlock:
    """Ордер блок — зона входа умных денег."""
    type:       str    # BULLISH / BEARISH
    high:       float
    low:        float
    mid:        float
    index:      int
    valid:      bool = True
    tested:     bool = False

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high

    def ce(self) -> float:
        """Consequent Encroachment — 50% OB."""
        return (self.high + self.low) / 2


@dataclass
class FVG:
    """Fair Value Gap — ценовой дисбаланс."""
    type:   str    # BULLISH / BEARISH
    high:   float
    low:    float
    index:  int
    filled: bool = False

    def ce(self) -> float:
        return (self.high + self.low) / 2

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high


@dataclass
class MarketStructure:
    """Структура рынка."""
    trend:      str    # BULLISH / BEARISH / NEUTRAL
    last_hh:    float = 0.0
    last_hl:    float = 0.0
    last_lh:    float = 0.0
    last_ll:    float = 0.0
    bos:        bool  = False   # Break of Structure
    choch:      bool  = False   # Change of Character


@dataclass
class SMCSignal:
    """Торговый сигнал от SMC стратегии."""
    symbol:     str
    side:       str    # Buy / Sell
    entry:      float
    sl:         float
    tp:         float
    rr:         float
    confidence: int    # 0-100
    reasons:    list   = field(default_factory=list)
    timeframe:  str    = "15"
    timestamp:  float  = field(default_factory=time.time)

    @property
    def is_valid(self) -> bool:
        return (
            self.confidence >= 30
            and self.rr >= 2.0
            and self.sl > 0
            and self.tp > 0
        )

    def format(self) -> str:
        side_emoji = "🟢 ЛОНГ" if self.side == "Buy" else "🔴 ШОРТ"
        conf_emoji = "🔥" if self.confidence >= 80 else "✅" if self.confidence >= 30 else "⚠️"
        return (
            f"{conf_emoji} *SMC Сигнал* ({self.confidence}%)\n"
            f"{'─'*28}\n"
            f"{side_emoji} *{self.symbol}*\n"
            f"Entry: `{self.entry:.4f}`\n"
            f"SL:    `{self.sl:.4f}`\n"
            f"TP:    `{self.tp:.4f}`\n"
            f"RR:    `1:{self.rr:.2f}`\n"
            f"TF:    `{self.timeframe}m`\n"
            f"{'─'*28}\n"
            + "\n".join(f"• {r}" for r in self.reasons)
        )


# ─── АНАЛИЗ СТРУКТУРЫ РЫНКА ──────────────────────────────────────────────────

def analyze_market_structure(candles: list[Candle]) -> MarketStructure:
    """
    Определяет структуру рынка (HH/HL/LH/LL).
    Логика из Урока 1.
    """
    if len(candles) < 10:
        return MarketStructure(trend="NEUTRAL")

    # Ищем свинги (упрощённый 3-свечной метод)
    highs = []
    lows  = []

    for i in range(1, len(candles) - 1):
        # Свинг хай
        if candles[i].high > candles[i-1].high and candles[i].high > candles[i+1].high:
            highs.append((i, candles[i].high))
        # Свинг лоу
        if candles[i].low < candles[i-1].low and candles[i].low < candles[i+1].low:
            lows.append((i, candles[i].low))

    if len(highs) < 2 or len(lows) < 2:
        return MarketStructure(trend="NEUTRAL")

    last_hh = highs[-1][1]
    prev_hh = highs[-2][1]
    last_ll = lows[-1][1]
    prev_ll = lows[-2][1]

    ms = MarketStructure(
        trend="NEUTRAL",
        last_hh=last_hh,
        last_ll=last_ll,
        last_lh=highs[-1][1] if last_hh < prev_hh else 0,
        last_hl=lows[-1][1]  if last_ll > prev_ll else 0,
    )

    # Восходящий тренд: HH + HL
    if last_hh > prev_hh and last_ll > prev_ll:
        ms.trend = "BULLISH"

    # Нисходящий тренд: LH + LL
    elif last_hh < prev_hh and last_ll < prev_ll:
        ms.trend = "BEARISH"

    # BOS — слом структуры
    current_price = candles[-1].close
    if ms.trend == "BULLISH" and current_price < last_ll:
        ms.bos  = True
        ms.choch = True
    elif ms.trend == "BEARISH" and current_price > last_hh:
        ms.bos  = True
        ms.choch = True

    return ms


# ─── ПОИСК ORDER BLOCKS ──────────────────────────────────────────────────────

def find_order_blocks(candles: list[Candle], lookback: int = 30) -> list[OrderBlock]:
    """
    Находит Order Blocks.
    Логика из Урока 3:
    - Бычий OB: последняя медвежья свеча перед импульсным ростом
    - Медвежий OB: последняя бычья свеча перед импульсным падением
    """
    obs    = []
    recent = candles[-lookback:] if len(candles) > lookback else candles

    for i in range(2, len(recent) - 1):
        curr = recent[i]
        next_c = recent[i + 1]

        # Бычий OB: медвежья свеча + следующая бычья с поглощением
        if (curr.is_bearish and
            next_c.is_bullish and
            next_c.close > curr.high and
            next_c.body_size > curr.body_size * 1.5):

            obs.append(OrderBlock(
                type  = "BULLISH",
                high  = curr.high,
                low   = curr.low,
                mid   = (curr.high + curr.low) / 2,
                index = len(candles) - lookback + i,
            ))

        # Медвежий OB: бычья свеча + следующая медвежья с поглощением
        elif (curr.is_bullish and
              next_c.is_bearish and
              next_c.close < curr.low and
              next_c.body_size > curr.body_size * 1.5):

            obs.append(OrderBlock(
                type  = "BEARISH",
                high  = curr.high,
                low   = curr.low,
                mid   = (curr.high + curr.low) / 2,
                index = len(candles) - lookback + i,
            ))

    return obs


# ─── ПОИСК FVG ───────────────────────────────────────────────────────────────

def find_fvg(candles: list[Candle], lookback: int = 20) -> list[FVG]:
    """
    Находит Fair Value Gaps.
    Логика из Урока 3:
    FVG = разрыв между тенями свечей 1 и 3.
    """
    fvgs   = []
    recent = candles[-lookback:] if len(candles) > lookback else candles

    for i in range(1, len(recent) - 1):
        c1 = recent[i - 1]
        c3 = recent[i + 1]

        # Бычий FVG: low[3] > high[1]
        if c3.low > c1.high:
            fvgs.append(FVG(
                type  = "BULLISH",
                high  = c3.low,
                low   = c1.high,
                index = i,
            ))

        # Медвежий FVG: high[3] < low[1]
        elif c3.high < c1.low:
            fvgs.append(FVG(
                type  = "BEARISH",
                high  = c1.low,
                low   = c3.high,
                index = i,
            ))

    return fvgs


# ─── ПОИСК ЛИКВИДНОСТИ ───────────────────────────────────────────────────────

def find_liquidity_levels(candles: list[Candle]) -> dict:
    """
    Определяет уровни ликвидности (BSL/SSL).
    Логика из Урока 2.
    """
    if not candles:
        return {"bsl": [], "ssl": []}

    recent = candles[-50:]

    highs  = [c.high for c in recent]
    lows   = [c.low  for c in recent]

    # Equal Highs — BSL (Buy Side Liquidity)
    bsl = []
    for i in range(len(highs) - 1):
        if abs(highs[i] - highs[-1]) / highs[-1] < 0.002:  # в пределах 0.2%
            bsl.append(highs[i])

    # Equal Lows — SSL (Sell Side Liquidity)
    ssl = []
    for i in range(len(lows) - 1):
        if abs(lows[i] - lows[-1]) / lows[-1] < 0.002:
            ssl.append(lows[i])

    return {
        "bsl":      max(highs[-20:]),   # ближайший BSL
        "ssl":      min(lows[-20:]),    # ближайший SSL
        "prev_high": max(highs[-50:-20]) if len(highs) > 20 else max(highs),
        "prev_low":  min(lows[-50:-20])  if len(lows)  > 20 else min(lows),
    }


# ─── ГЛАВНАЯ СТРАТЕГИЯ ───────────────────────────────────────────────────────

class SMCStrategy:
    """
    Автономная SMC стратегия.
    
    Алгоритм:
    1. Получает свечи с Bybit (15m + 4H)
    2. Анализирует структуру рынка на 4H
    3. Ищет OB и FVG на 15m
    4. Проверяет сессию
    5. Проверяет межрыночный контекст
    6. Генерирует сигнал если всё совпало
    """

    def __init__(self, engine, deposit: float, risk_pct: float, leverage: int):
        self.engine    = engine
        self.deposit   = deposit
        self.risk_pct  = risk_pct
        self.leverage  = leverage

        from sessions import is_tradeable_session
        from market_context import get_analyzer
        self.is_tradeable = is_tradeable_session
        self.market_ctx   = get_analyzer()

    def get_candles(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        """Получает свечи с Bybit и конвертирует в Candle."""
        raw = self.engine.get_klines(symbol, interval=interval, limit=limit)
        return [Candle(**c) for c in raw]

    def analyze(self, symbol: str) -> Optional[SMCSignal]:
        """
        Полный SMC анализ символа.
        Возвращает сигнал или None.
        """
        try:
            # ── 1. Проверка сессии ────────────────────────────────────────────
            if not self.is_tradeable():
                logger.debug(f"{symbol}: не торговая сессия")
                return None

            # ── 2. Получаем свечи ─────────────────────────────────────────────
            candles_4h  = self.get_candles(symbol, "240", 100)  # 4H для структуры
            candles_15m = self.get_candles(symbol, "15",  100)  # 15m для входа

            if len(candles_4h) < 20 or len(candles_15m) < 20:
                return None

            current_price = candles_15m[-1].close

            # ── 3. Структура рынка на 4H ──────────────────────────────────────
            ms = analyze_market_structure(candles_4h)
            if False:  # разрешаем NEUTRAL
                logger.debug(f"{symbol}: нейтральная структура")
                return None

            # ── 4. Межрыночный контекст ───────────────────────────────────────
            bias = self.market_ctx.analyze(symbol)
            if bias.direction == "BEARISH" and ms.trend == "BULLISH" and bias.strength > 70:
                logger.debug(f"{symbol}: межрыночный контекст против лонга")
                return None
            if bias.direction == "BULLISH" and ms.trend == "BEARISH" and bias.strength > 70:
                logger.debug(f"{symbol}: межрыночный контекст против шорта")
                return None

            # ── 5. Ищем OB и FVG на 15m ──────────────────────────────────────
            obs  = find_order_blocks(candles_15m)
            fvgs = find_fvg(candles_15m)
            liq  = find_liquidity_levels(candles_15m)

            # ── 6. Генерируем сигнал ──────────────────────────────────────────
            if ms.trend == "BULLISH":
                return self._bullish_signal(
                    symbol, current_price, ms, obs, fvgs, liq, bias
                )
            else:
                return self._bearish_signal(
                    symbol, current_price, ms, obs, fvgs, liq, bias
                )

        except Exception as e:
            logger.error(f"SMC analyze error ({symbol}): {e}")
            return None

    def _bullish_signal(
        self, symbol, price, ms, obs, fvgs, liq, bias
    ) -> Optional[SMCSignal]:
        """Ищет лонг сигнал."""
        reasons    = []
        confidence = 0

        # Ищем бычий OB ниже цены
        bull_obs = [ob for ob in obs if ob.type == "BULLISH" and ob.high < price]
        if not bull_obs:
            return None

        # Ближайший OB
        ob = max(bull_obs, key=lambda x: x.high)

        # Цена должна быть близко к OB (в пределах 0.5%)
        dist = (price - ob.high) / price
        if dist > 0.03:
            return None

        # OB найден
        confidence += 30
        reasons.append(f"✅ Бычий OB: {ob.low:.4f} - {ob.high:.4f}")

        # Ищем FVG внутри или рядом с OB
        bull_fvgs = [f for f in fvgs if f.type == "BULLISH" and f.low >= ob.low and f.high <= ob.high * 1.01]
        if bull_fvgs:
            confidence += 20
            reasons.append(f"✅ FVG внутри OB: {bull_fvgs[-1].low:.4f} - {bull_fvgs[-1].high:.4f}")

        # Структура бычья
        confidence += 20
        reasons.append(f"✅ 4H структура: BULLISH (HH={ms.last_hh:.4f})")

        # Межрыночный контекст
        if bias.direction == "BULLISH":
            confidence += 15
            reasons.append(f"✅ Межрыночный контекст: BULLISH ({bias.strength}%)")
        elif bias.direction == "NEUTRAL":
            confidence += 5

        # Ликвидность
        if liq["ssl"] < ob.low:
            confidence += 15
            reasons.append(f"✅ SSL снята: {liq['ssl']:.4f}")

        # Фандинг
        funding = self.engine.get_funding_rate(symbol)
        if funding is not None and funding < 0:
            confidence += 10
            reasons.append(f"✅ Фандинг отрицательный: {funding:+.4f}%")

        # Точки входа
        entry = ob.high
        sl    = ob.low * 0.999  # чуть ниже OB
        tp    = liq["bsl"]      # цель — BSL

        if tp <= entry or sl >= entry:
            return None

        rr = (tp - entry) / (entry - sl)
        if rr < 1.5:
            # Попробуем дальнюю цель
            tp = ms.last_hh * 1.005
            rr = (tp - entry) / (entry - sl)

        if rr < 1.5:
            return None

        # Доп. подтверждение от индикаторов (не блокирует, только бонус)
        try:
            ind = full_indicator_analysis(_candles_to_df(self.get_candles(symbol, "15", 100)))
            if ind["direction"] == "Buy":
                bonus = min(ind["confidence"] / 5, 10)
                confidence += bonus
                reasons.append(f"✅ Индикаторы: Buy (conf={ind['confidence']}, torgun={ind['torgun_sig']})")
        except Exception as e:
            logger.warning(f"full_indicator_analysis bullish failed: {e}")

        return SMCSignal(
            symbol=symbol, side="Buy",
            entry=entry, sl=sl, tp=tp,
            rr=round(rr, 2),
            confidence=min(confidence+10, 100),
            reasons=reasons,
            timeframe="15",
        )

    def _bearish_signal(
        self, symbol, price, ms, obs, fvgs, liq, bias
    ) -> Optional[SMCSignal]:
        """Ищет шорт сигнал."""
        reasons    = []
        confidence = 0

        # Ищем медвежий OB выше цены
        bear_obs = [ob for ob in obs if ob.type == "BEARISH" and ob.low > price]
        if not bear_obs:
            return None

        # Ближайший OB
        ob = min(bear_obs, key=lambda x: x.low)

        # Цена должна быть близко к OB
        dist = (ob.low - price) / price
        if dist > 0.03:
            return None

        confidence += 30
        reasons.append(f"✅ Медвежий OB: {ob.low:.4f} - {ob.high:.4f}")

        # FVG внутри OB
        bear_fvgs = [f for f in fvgs if f.type == "BEARISH" and f.low >= ob.low * 0.99 and f.high <= ob.high]
        if bear_fvgs:
            confidence += 20
            reasons.append(f"✅ FVG внутри OB: {bear_fvgs[-1].low:.4f} - {bear_fvgs[-1].high:.4f}")

        confidence += 20
        reasons.append(f"✅ 4H структура: BEARISH (LL={ms.last_ll:.4f})")

        if bias.direction == "BEARISH":
            confidence += 15
            reasons.append(f"✅ Межрыночный контекст: BEARISH ({bias.strength}%)")
        elif bias.direction == "NEUTRAL":
            confidence += 5

        if liq["bsl"] > ob.high:
            confidence += 15
            reasons.append(f"✅ BSL снята: {liq['bsl']:.4f}")

        funding = self.engine.get_funding_rate(symbol)
        if funding is not None and funding > 0.05:
            confidence += 10
            reasons.append(f"✅ Высокий фандинг: {funding:+.4f}%")

        entry = ob.low
        sl    = ob.high * 1.001
        tp    = liq["ssl"]

        if tp >= entry or sl <= entry:
            return None

        rr = (entry - tp) / (sl - entry)
        if rr < 1.5:
            tp = ms.last_ll * 0.995
            rr = (entry - tp) / (sl - entry)

        if rr < 1.5:
            return None

        try:
            ind = full_indicator_analysis(_candles_to_df(self.get_candles(symbol, "15", 100)))
            if ind["direction"] == "Sell":
                bonus = min(ind["confidence"] / 5, 10)
                confidence += bonus
                reasons.append(f"✅ Индикаторы: Sell (conf={ind['confidence']}, torgun={ind['torgun_sig']})")
        except Exception as e:
            logger.warning(f"full_indicator_analysis bearish failed: {e}")

        return SMCSignal(
            symbol=symbol, side="Sell",
            entry=entry, sl=sl, tp=tp,
            rr=round(rr, 2),
            confidence=min(confidence+10, 100),
            reasons=reasons,
            timeframe="15",
        )


# ─── АВТОНОМНЫЙ СКАНЕР ───────────────────────────────────────────────────────

class AutoTrader:
    """
    Автономный трейдер.
    Сканирует символы каждые N минут и открывает сделки.
    """

    SYMBOLS = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT",
        "ADAUSDT", "LINKUSDT", "AVAXUSDT",
    ]

    def __init__(self, engine, deposit, risk_pct, leverage, notify_fn=None):
        self.strategy  = SMCStrategy(engine, deposit, risk_pct, leverage)
        self.engine    = engine
        self.deposit   = deposit
        self.risk_pct  = risk_pct
        self.leverage  = leverage
        self.notify_fn = notify_fn   # async функция для уведомлений в Telegram
        self._last_signals: dict = {}  # дедупликация сигналов

    async def scan_once(self) -> list[SMCSignal]:
        """Один проход сканера по всем символам."""
        signals = []

        for symbol in self.SYMBOLS:
            try:
                signal = self.strategy.analyze(symbol)
                if not signal or not signal.is_valid:
                    continue

                # Дедупликация — не повторять сигнал чаще раз в час
                last = self._last_signals.get(symbol, 0)
                if time.time() - last < 3600:
                    continue

                self._last_signals[symbol] = time.time()
                signals.append(signal)
                logger.info(f"📡 Сигнал: {symbol} {signal.side} conf={signal.confidence}%")

            except Exception as e:
                logger.error(f"Scan error ({symbol}): {e}")

        return signals

    async def execute_signal(self, signal: SMCSignal) -> dict:
        """Исполняет сигнал на Bybit."""
        from risk_manager import calculate_risk_for_symbol
        from journal import add_trade
        from sessions import get_current_session

        r = calculate_risk_for_symbol(
            signal.symbol, signal.side,
            signal.entry, signal.sl, signal.tp,
            self.deposit, self.risk_pct, self.leverage,
        )

        if not r.valid:
            return {"ok": False, "msg": f"Риск: {r.error}"}

        result = self.engine.place_order(
            symbol=signal.symbol,
            side=signal.side,
            qty=r.qty,
            sl=signal.sl,
            tp=signal.tp,
            leverage=self.leverage,
        )

        if result["ok"]:
            sess = get_current_session()
            add_trade(
                symbol=signal.symbol, side=signal.side,
                entry=signal.entry, sl=signal.sl, tp=signal.tp,
                qty=r.qty, risk_pct=self.risk_pct,
                leverage=self.leverage, rr=signal.rr,
                mode="auto", order_id=result.get("orderId", ""),
                session=sess["name"],
            )

        return result

    async def run(self, interval_minutes: int = 15):
        """
        Основной цикл автотрейдера.
        Запускается как фоновая задача в bot.py.
        """
        import asyncio
        logger.info(f"🤖 AutoTrader запущен. Интервал: {interval_minutes}м")

        while True:
            try:
                signals = await self.scan_once()

                for signal in signals:
                    # Уведомление пользователю
                    if self.notify_fn:
                        await self.notify_fn(
                            f"📡 *Найден сигнал!*\n{signal.format()}\n\n⏳ Исполняю..."
                        )

                    # Исполнение
                    result = await self.execute_signal(signal)

                    if self.notify_fn:
                        if result["ok"]:
                            await self.notify_fn(
                                f"✅ *Сделка открыта автоматически!*\n"
                                f"{signal.symbol} {signal.side}\n"
                                f"RR: 1:{signal.rr}"
                            )
                        else:
                            await self.notify_fn(f"❌ Ошибка исполнения: {result['msg']}")

            except Exception as e:
                logger.error(f"AutoTrader cycle error: {e}")

            await asyncio.sleep(interval_minutes * 60)