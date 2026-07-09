"""
risk_manager.py v2 — Управление рисками
Правила: макс 5 сделок/день, макс 2 убытка/день,
после 2 лоссов ждать Asia, force не обходит лимиты,
фикс маржа 10 USDT, плечо 20x.
"""
from __future__ import annotations
from config import MIN_RR
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

MARGIN_PER_TRADE = 10.0
LEVERAGE         = 20
MAX_TRADES_DAY   = 5
MAX_LOSSES_DAY   = 2
ROI_TARGET       = 0.35

SYMBOL_PARAMS = {
    "BTCUSDT":  {"step": 0.001, "min": 0.001},
    "ETHUSDT":  {"step": 0.01,  "min": 0.01},
    "SOLUSDT":  {"step": 0.1,   "min": 0.1},
    "ADAUSDT":  {"step": 1.0,   "min": 1.0},
    "BNBUSDT":  {"step": 0.01,  "min": 0.01},
    "XRPUSDT":  {"step": 1.0,   "min": 1.0},
    "DOTUSDT":  {"step": 0.1,   "min": 0.1},
    "LINKUSDT": {"step": 0.1,   "min": 0.1},
    "AVAXUSDT": {"step": 0.1,   "min": 0.1},
    "ATOMUSDT": {"step": 0.1,   "min": 0.1},
    "UNIUSDT":  {"step": 0.1,   "min": 0.1},
    "CRVUSDT":  {"step": 1.0,   "min": 1.0},
}
DEFAULT_PARAMS = {"step": 0.01, "min": 0.01}

def get_qty_params(symbol: str) -> dict:
    return SYMBOL_PARAMS.get(symbol, DEFAULT_PARAMS)

def is_asia_session() -> bool:
    hour = datetime.now(timezone.utc).hour
    return 0 <= hour < 8

def is_tradeable_now() -> bool:
    hour = datetime.now(timezone.utc).hour
    return 7 <= hour < 22

def calc_position_qty(symbol: str, entry: float, margin: float = MARGIN_PER_TRADE, leverage: int = LEVERAGE) -> float:
    if entry <= 0:
        return 0.0
    raw_qty = (margin * leverage) / entry
    params  = get_qty_params(symbol)
    step    = params["step"]
    qty     = round(int(raw_qty / step) * step, 8)
    return qty if qty >= params["min"] else 0.0

def calc_sl_tp(side: str, entry: float, roi: float = ROI_TARGET) -> tuple[float, float]:
    price_move = roi / LEVERAGE
    sl_move    = price_move / 2
    if side == "Buy":
        return round(entry * (1 - sl_move), 6), round(entry * (1 + price_move), 6)
    else:
        return round(entry * (1 + sl_move), 6), round(entry * (1 - price_move), 6)

@dataclass
class RiskDecision:
    allowed:  bool
    reason:   str   = ""
    qty:      float = 0.0
    entry:    float = 0.0
    sl:       float = 0.0
    tp:       float = 0.0
    rr:       float = 0.0
    margin:   float = MARGIN_PER_TRADE
    leverage: int   = LEVERAGE

    def format(self) -> str:
        if not self.allowed:
            return f"⛔ *Сделка запрещена*\n{self.reason}"
        rr_emoji = "✅" if self.rr >= 2 else "⚠️"
        return (
            f"📊 *План сделки*\n{'─'*28}\n"
            f"Маржа:  `{self.margin} USDT`\n"
            f"Плечо:  `{self.leverage}x`\n"
            f"Объём:  `{self.qty}`\n"
            f"Entry:  `{self.entry}`\n"
            f"SL:     `{self.sl}`\n"
            f"TP:     `{self.tp}`\n"
            f"{rr_emoji} RR: `1:{self.rr:.2f}`"
        )

def can_open_trade(symbol: str, side: str, entry: float, sl: float = 0.0, tp: float = 0.0, margin: float = MARGIN_PER_TRADE, leverage: int = LEVERAGE) -> RiskDecision:
    from journal import count_trades_today, count_losing_trades_today

    trades_today = count_trades_today()
    if trades_today >= MAX_TRADES_DAY:
        return RiskDecision(allowed=False, reason=f"Лимит сделок: {trades_today}/{MAX_TRADES_DAY} в день")

    losses_today = count_losing_trades_today()
    if losses_today >= MAX_LOSSES_DAY:
        return RiskDecision(allowed=False, reason=f"🔴 Лимит убытков: {losses_today}/{MAX_LOSSES_DAY}\nЖди Asia сессии (00:00 UTC)")

    if not is_tradeable_now():
        return RiskDecision(allowed=False, reason="😴 Не торговое время. London (07-16 UTC) и NY (13-22 UTC)")

    qty = calc_position_qty(symbol, entry, margin, leverage)
    if qty <= 0:
        return RiskDecision(allowed=False, reason=f"Размер позиции = 0 при entry={entry}")

    if not sl or not tp:
        sl, tp = calc_sl_tp(side, entry)

    if side == "Buy":
        if sl >= entry:
            return RiskDecision(allowed=False, reason=f"SL ({sl}) должен быть ниже Entry ({entry})")
        if tp <= entry:
            return RiskDecision(allowed=False, reason=f"TP ({tp}) должен быть выше Entry ({entry})")
    else:
        if sl <= entry:
            return RiskDecision(allowed=False, reason=f"SL ({sl}) должен быть выше Entry ({entry})")
        if tp >= entry:
            return RiskDecision(allowed=False, reason=f"TP ({tp}) должен быть ниже Entry ({entry})")

    sl_dist = abs(entry - sl)
    tp_dist = abs(tp - entry)
    rr      = tp_dist / sl_dist if sl_dist > 0 else 0

    if rr < MIN_RR:
        return RiskDecision(allowed=False, reason=f"RR слишком низкий: 1:{rr:.2f} (минимум 1:1.5)")

    return RiskDecision(
        allowed=True,
        reason=f"✅ Сделок: {trades_today}/{MAX_TRADES_DAY} | Убытков: {losses_today}/{MAX_LOSSES_DAY}",
        qty=qty, entry=entry, sl=sl, tp=tp,
        rr=round(rr, 2), margin=margin, leverage=leverage,
    )

def build_trade_plan(symbol: str, side: str, entry: float, sl: float = 0.0, tp: float = 0.0) -> RiskDecision:
    return can_open_trade(symbol, side, entry, sl, tp)

def calculate_risk_for_symbol(symbol, side, entry, sl, tp, deposit=1000, risk_pct=1.0, leverage=LEVERAGE):
    decision = can_open_trade(symbol, side, entry, sl, tp)
    class RiskResult:
        def __init__(self, d):
            self.valid = d.allowed; self.qty = d.qty; self.rr = d.rr
            self.error = d.reason; self.entry = d.entry; self.sl = d.sl; self.tp = d.tp
        def format(self): return decision.format()
    return RiskResult(decision)