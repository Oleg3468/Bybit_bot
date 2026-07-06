# smc_strategy.py — Автономная SMC стратегия
from __future__ import annotations

import logging
import time
import asyncio
from dataclasses import dataclass, field
from typing import Optional

from config import (
    OB_MAX_DISTANCE_PCT,
    BULLISH_SL_BUFFER_PCT,
    BEARISH_SL_BUFFER_PCT,
    BULLISH_TP_FALLBACK_PCT,
    BEARISH_TP_FALLBACK_PCT,
    MIN_RR,
    SIGNAL_DEDUP_SEC,
)
from indicators import full_indicator_analysis
import pandas as pd

logger = logging.getLogger(__name__)

def _candles_to_df(candles):
    return pd.DataFrame([{
        "open": c.open, "high": c.high, "low": c.low,
        "close": c.close, "volume": c.volume,
    } for c in candles])

@dataclass
class Candle:
    time:   int
    open:   float
    high:   float
    low:    float
    close:  float
    volume: float

    @property
    def is_bullish(self) -> bool: return self.close > self.open

    @property
    def is_bearish(self) -> bool: return self.close < self.open

    @property
    def body_size(self) -> float: return abs(self.close - self.open)

    @property
    def total_range(self) -> float: return self.high - self.low

@dataclass
class OrderBlock:
    type:       str
    high:       float
    low:        float
    mid:        float
    index:      int
    valid:      bool = True
    tested:     bool = False

    def contains(self, price: float) -> bool: return self.low <= price <= self.high
    def ce(self) -> float: return (self.high + self.low) / 2

@dataclass
class FVG:
    type:   str
    high:   float
    low:    float
    index:  int
    filled: bool = False

    def ce(self) -> float: return (self.high + self.low) / 2
    def contains(self, price: float) -> bool: return self.low <= price <= self.high

@dataclass
class MarketStructure:
    trend:      str
    last_hh:    float = 0.0
    last_hl:    float = 0.0
    last_lh:    float = 0.0
    last_ll:    float = 0.0
    bos:        bool  = False
    choch:      bool  = False

@dataclass
class SMCSignal:
    symbol:     str
    side:       str
    entry:      float
    sl:         float
    tp:         float
    rr:         float
    confidence: int
    reasons:    list   = field(default_factory=list)
    timeframe:  str    = "15"
    timestamp:  float  = field(default_factory=time.time)

    @property
    def is_valid(self) -> bool:
        return (
            self.confidence >= 30
            and self.rr >= MIN_RR
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

def analyze_market_structure(candles: list[Candle]) -> MarketStructure:
    if len(candles) < 10: return MarketStructure(trend="NEUTRAL")
    highs, lows = [], []
    for i in range(1, len(candles) - 1):
        if candles[i].high > candles[i-1].high and candles[i].high > candles[i+1].high:
            highs.append((i, candles[i].high))
        if candles[i].low < candles[i-1].low and candles[i].low < candles[i+1].low:
            lows.append((i, candles[i].low))
    if len(highs) < 2 or len(lows) < 2: return MarketStructure(trend="NEUTRAL")
    last_hh, prev_hh = highs[-1][1], highs[-2][1]
    last_ll, prev_ll = lows[-1][1], lows[-2][1]
    ms = MarketStructure(trend="NEUTRAL", last_hh=last_hh, last_ll=last_ll,
                         last_lh=highs[-1][1] if last_hh < prev_hh else 0,
                         last_hl=lows[-1][1]  if last_ll > prev_ll else 0)
    if last_hh > prev_hh and last_ll > prev_ll: ms.trend = "BULLISH"
    elif last_hh < prev_hh and last_ll < prev_ll: ms.trend = "BEARISH"
    current_price = candles[-1].close
    if ms.trend == "BULLISH" and current_price < last_ll: ms.bos, ms.choch = True, True
    elif ms.trend == "BEARISH" and current_price > last_hh: ms.bos, ms.choch = True, True
    return ms

def find_order_blocks(candles: list[Candle], lookback: int = 30) -> list[OrderBlock]:
    obs, recent = [], candles[-lookback:] if len(candles) > lookback else candles
    for i in range(2, len(recent) - 1):
        curr, next_c = recent[i], recent[i + 1]
        if (curr.is_bearish and next_c.is_bullish and next_c.close > curr.high and next_c.body_size > curr.body_size * 1.5):
            obs.append(OrderBlock(type="BULLISH", high=curr.high, low=curr.low, mid=(curr.high + curr.low) / 2, index=len(candles) - lookback + i))
        elif (curr.is_bullish and next_c.is_bearish and next_c.close < curr.low and next_c.body_size > curr.body_size * 1.5):
            obs.append(OrderBlock(type="BEARISH", high=curr.high, low=curr.low, mid=(curr.high + curr.low) / 2, index=len(candles) - lookback + i))
    return obs

def find_fvg(candles: list[Candle], lookback: int = 20) -> list[FVG]:
    fvgs, recent = [], candles[-lookback:] if len(candles) > lookback else candles
    for i in range(1, len(recent) - 1):
        c1, c3 = recent[i - 1], recent[i + 1]
        if c3.low > c1.high: fvgs.append(FVG(type="BULLISH", high=c3.low, low=c1.high, index=i))
        elif c3.high < c1.low: fvgs.append(FVG(type="BEARISH", high=c1.low, low=c3.high, index=i))
    return fvgs

def find_liquidity_levels(candles: list[Candle]) -> dict:
    if not candles: return {"bsl": [], "ssl": []}
    recent = candles[-50:]
    highs, lows = [c.high for c in recent], [c.low for c in recent]
    bsl = [highs[i] for i in range(len(highs)-1) if abs(highs[i] - highs[-1]) / highs[-1] < 0.002]
    ssl = [lows[i] for i in range(len(lows)-1) if abs(lows[i] - lows[-1]) / lows[-1] < 0.002]
    return {
        "bsl": max(highs[-20:]), "ssl": min(lows[-20:]),
        "prev_high": max(highs[-50:-20]) if len(highs) > 20 else max(highs),
        "prev_low":  min(lows[-50:-20])  if len(lows)  > 20 else min(lows),
    }

class SMCStrategy:
    def __init__(self, engine_fn, deposit: float, risk_pct: float, leverage: int):
        self.engine_fn = engine_fn
        self.deposit   = deposit
        self.risk_pct  = risk_pct
        self.leverage  = leverage
        from sessions import is_tradeable_session
        from market_context import get_analyzer
        self.is_tradeable = is_tradeable_session
        self.market_ctx   = get_analyzer()

    def get_candles(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        raw = self.engine_fn().get_klines(symbol, interval=interval, limit=limit)
        return [Candle(**c) for c in raw]

    def analyze(self, symbol: str) -> Optional[SMCSignal]:
        try:
            if not self.is_tradeable():
                logger.debug(f"{symbol}: не торговая сессия")
                return None
            candles_4h  = self.get_candles(symbol, "240", 100)
            candles_15m = self.get_candles(symbol, "15",  100)
            if len(candles_4h) < 20 or len(candles_15m) < 20: return None
            current_price = candles_15m[-1].close
            ms = analyze_market_structure(candles_4h)
            if ms.trend == "NEUTRAL": return None
            bias = self.market_ctx.analyze(symbol)
            if bias.direction == "BEARISH" and ms.trend == "BULLISH" and bias.strength > 70: return None
            if bias.direction == "BULLISH" and ms.trend == "BEARISH" and bias.strength > 70: return None
            obs  = find_order_blocks(candles_15m)
            fvgs = find_fvg(candles_15m)
            liq  = find_liquidity_levels(candles_15m)
            if ms.trend == "BULLISH":
                return self._bullish_signal(symbol, current_price, ms, obs, fvgs, liq, bias, candles_15m)
            elif ms.trend == "BEARISH":
                return self._bearish_signal(symbol, current_price, ms, obs, fvgs, liq, bias, candles_15m)
        except Exception as e:
            logger.error(f"SMC analyze error ({symbol}): {e}")
        return None

    def _bullish_signal(self, symbol, price, ms, obs, fvgs, liq, bias, candles_15m) -> Optional[SMCSignal]:
        reasons, confidence = [], 0
        bull_obs = [ob for ob in obs if ob.type == "BULLISH" and ob.high < price]
        if not bull_obs: return None
        ob = max(bull_obs, key=lambda x: x.high)
        dist = (price - ob.high) / price
        if dist > OB_MAX_DISTANCE_PCT: return None
        confidence += 30; reasons.append(f"✅ Бычий OB: {ob.low:.4f} - {ob.high:.4f}")
        bull_fvgs = [f for f in fvgs if f.type == "BULLISH" and f.low >= ob.low and f.high <= ob.high * 1.01]
        if bull_fvgs: confidence += 20; reasons.append(f"✅ FVG внутри OB: {bull_fvgs[-1].low:.4f} - {bull_fvgs[-1].high:.4f}")
        confidence += 20; reasons.append(f"✅ 4H структура: BULLISH (HH={ms.last_hh:.4f})")
        if bias.direction == "BULLISH": confidence += 15; reasons.append(f"✅ Межрыночный контекст: BULLISH ({bias.strength}%)")
        elif bias.direction == "NEUTRAL": confidence += 5
        if liq["ssl"] < ob.low: confidence += 15; reasons.append(f"✅ SSL снята: {liq['ssl']:.4f}")
        funding = self.engine_fn().get_funding_rate(symbol)
        if funding is not None and funding < 0: confidence += 10; reasons.append(f"✅ Фандинг отрицательный: {funding:+.4f}%")
        entry = ob.high; sl = ob.low * BULLISH_SL_BUFFER_PCT; tp = liq["bsl"]
        if tp <= entry or sl >= entry: return None
        rr = (tp - entry) / (entry - sl)
        if rr < MIN_RR: tp = ms.last_hh * BULLISH_TP_FALLBACK_PCT; rr = (tp - entry) / (entry - sl)
        if rr < MIN_RR: return None
        try:
            ind = full_indicator_analysis(_candles_to_df(candles_15m))
            if ind["direction"] == "Buy": bonus = min(ind["confidence"] / 5, 10); confidence += bonus; reasons.append(f"✅ Индикаторы: Buy")
        except Exception as e: logger.warning(f"full_indicator_analysis bullish failed: {e}")
        return SMCSignal(symbol=symbol, side="Buy", entry=entry, sl=sl, tp=tp, rr=round(rr, 2), confidence=min(confidence+10, 100), reasons=reasons, timeframe="15")

    def _bearish_signal(self, symbol, price, ms, obs, fvgs, liq, bias, candles_15m) -> Optional[SMCSignal]:
        reasons, confidence = [], 0
        bear_obs = [ob for ob in obs if ob.type == "BEARISH" and ob.low > price]
        if not bear_obs: return None
        ob = min(bear_obs, key=lambda x: x.low)
        dist = (ob.low - price) / price
        if dist > OB_MAX_DISTANCE_PCT: return None
        confidence += 30; reasons.append(f"✅ Медвежий OB: {ob.low:.4f} - {ob.high:.4f}")
        bear_fvgs = [f for f in fvgs if f.type == "BEARISH" and f.low >= ob.low * 0.99 and f.high <= ob.high]
        if bear_fvgs: confidence += 20; reasons.append(f"✅ FVG внутри OB: {bear_fvgs[-1].low:.4f} - {bear_fvgs[-1].high:.4f}")
        confidence += 20; reasons.append(f"✅ 4H структура: BEARISH (LL={ms.last_ll:.4f})")
        if bias.direction == "BEARISH": confidence += 15; reasons.append(f"✅ Межрыночный контекст: BEARISH ({bias.strength}%)")
        elif bias.direction == "NEUTRAL": confidence += 5
        if liq["bsl"] > ob.high: confidence += 15; reasons.append(f"✅ BSL снята: {liq['bsl']:.4f}")
        funding = self.engine_fn().get_funding_rate(symbol)
        if funding is not None and funding > 0.05: confidence += 10; reasons.append(f"✅ Высокий фандинг: {funding:+.4f}%")
        entry = ob.low; sl = ob.high * BEARISH_SL_BUFFER_PCT; tp = liq["ssl"]
        if tp >= entry or sl <= entry: return None
        rr = (entry - tp) / (sl - entry)
        if rr < MIN_RR: tp = ms.last_ll * BEARISH_TP_FALLBACK_PCT; rr = (entry - tp) / (sl - entry)
        if rr < MIN_RR: return None
        try:
            ind = full_indicator_analysis(_candles_to_df(candles_15m))
            if ind["direction"] == "Sell": bonus = min(ind["confidence"] / 5, 10); confidence += bonus; reasons.append(f"✅ Индикаторы: Sell")
        except Exception as e: logger.warning(f"full_indicator_analysis bearish failed: {e}")
        return SMCSignal(symbol=symbol, side="Sell", entry=entry, sl=sl, tp=tp, rr=round(rr, 2), confidence=min(confidence+10, 100), reasons=reasons, timeframe="15")

class AutoTrader:
    SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT"]

    def __init__(self, engine_fn, deposit, risk_pct, leverage, notify_fn=None):
        self.strategy  = SMCStrategy(engine_fn, deposit, risk_pct, leverage)
        self.engine_fn = engine_fn
        self.deposit   = deposit
        self.risk_pct  = risk_pct
        self.leverage  = leverage
        self.notify_fn = notify_fn
        self._last_signals: dict = {}

    async def scan_once(self) -> list[SMCSignal]:
        signals, loop = [], asyncio.get_event_loop()
        for symbol in self.SYMBOLS:
            try:
                signal = await loop.run_in_executor(None, self.strategy.analyze, symbol)
                if not signal or not signal.is_valid: continue
                last = self._last_signals.get(symbol, 0)
                if time.time() - last < SIGNAL_DEDUP_SEC: continue
                self._last_signals[symbol] = time.time()
                signals.append(signal)
                logger.info(f"📡 Сигнал: {symbol} {signal.side} conf={signal.confidence}%")
            except Exception as e:
                logger.error(f"Scan error ({symbol}): {e}")
        return signals

    async def execute_signal(self, signal: SMCSignal) -> dict:
        from risk_manager import calculate_risk_for_symbol
        from journal import add_trade
        from sessions import get_current_session
        eng = self.engine_fn()
        loop = asyncio.get_event_loop()
        def _execute_sync():
            r = calculate_risk_for_symbol(signal.symbol, signal.side, signal.entry, signal.sl, signal.tp, self.deposit, self.risk_pct, self.leverage)
            if not r.valid: return {"ok": False, "msg": f"Риск: {r.error}"}
            result = eng.place_order(symbol=signal.symbol, side=signal.side, qty=r.qty, sl=signal.sl, tp=signal.tp, leverage=self.leverage)
            if result["ok"]:
                sess = get_current_session()
                add_trade(symbol=signal.symbol, side=signal.side, entry=signal.entry, sl=signal.sl, tp=signal.tp, qty=r.qty, risk_pct=self.risk_pct, leverage=self.leverage, rr=signal.rr, mode="auto", order_id=result.get("orderId", ""), session=sess["name"])
            return result
        return await loop.run_in_executor(None, _execute_sync)
