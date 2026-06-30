"""
bot.py v4 — SMC Trade Bot + AutoTrader
Bybit Futures | Telegram | Demo + Live
Автономная торговля через smc_strategy.py
"""
import logging, os, asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from trade_engine import BybitEngine
from risk_manager import can_open_trade, build_trade_plan, MARGIN_PER_TRADE, LEVERAGE
from journal import add_trade, close_trade, format_open_trades, format_stats, count_trades_today, count_losing_trades_today, daily_net_pnl
from sessions import format_session_message, check_session_changed, format_session_alert, get_current_session
from market_context import get_analyzer
from smc_strategy import AutoTrader

load_dotenv()
TG_TOKEN        = os.getenv("TG_TOKEN","")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID","0"))
DEPOSIT         = float(os.getenv("DEPOSIT","1000"))
RISK_PCT        = float(os.getenv("RISK_PCT","1.0"))

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

engines      = {"demo": BybitEngine(os.getenv("BYBIT_DEMO_KEY",""), os.getenv("BYBIT_DEMO_SECRET",""), mode="demo"), "live": BybitEngine(os.getenv("BYBIT_LIVE_KEY",""), os.getenv("BYBIT_LIVE_SECRET",""), mode="live")}
current_mode = {"mode": "demo"}
market_ctx   = get_analyzer()
auto_enabled = {"enabled": False}  # автоторговля вкл/выкл

def engine(): return engines[current_mode["mode"]]
def mode_badge(): return "🧪 DEMO" if current_mode["mode"] == "demo" else "💰 LIVE"
def auto_badge(): return "🤖 АВТО" if auto_enabled["enabled"] else "👤 РУЧНОЙ"

ALIAS = {"ada":"ADAUSDT","uni":"UNIUSDT","crv":"CRVUSDT","sol":"SOLUSDT","bnb":"BNBUSDT","eth":"ETHUSDT","btc":"BTCUSDT","link":"LINKUSDT","dot":"DOTUSDT","avax":"AVAXUSDT","xrp":"XRPUSDT","atom":"ATOMUSDT"}

def parse_symbol(raw):
    raw = raw.lower().replace("/","").replace("-","").replace("usdt","")
    return ALIAS.get(raw, raw.upper()+"USDT")

def is_allowed(update): return ALLOWED_USER_ID == 0 or update.effective_user.id == ALLOWED_USER_ID
async def deny(update): await update.message.reply_text("⛔ Нет доступа.")

# ─── УВЕДОМЛЕНИЕ ─────────────────────────────────────────────────────────────
async def notify(app, text: str):
    """Отправляет уведомление пользователю."""
    if ALLOWED_USER_ID:
        try:
            await app.bot.send_message(chat_id=ALLOWED_USER_ID, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"notify error: {e}")

# ─── ФОНОВЫЕ ЗАДАЧИ ───────────────────────────────────────────────────────────
async def session_watcher(app):
    if not ALLOWED_USER_ID: return
    check_session_changed()
    while True:
        await asyncio.sleep(60)
        try:
            new_sess = check_session_changed()
            if new_sess:
                await notify(app, format_session_alert(new_sess))
        except Exception as e: logger.error(f"Session watcher: {e}")

async def auto_trader_loop(app):
    """Автотрейдер — сканирует рынок каждые 15 минут."""
    trader = AutoTrader(
        engine=engine(),
        deposit=DEPOSIT,
        risk_pct=RISK_PCT,
        leverage=LEVERAGE,
        notify_fn=lambda text: notify(app, text),
    )
    logger.info("🤖 AutoTrader инициализирован.")

    while True:
        while True:
            try:
                if not auto_enabled["enabled"]:
                    await asyncio.sleep(5)
                    continue

                logger.info("Scanning market...")
                signals = await trader.scan_once()

                if not signals:
                    logger.info("No signals found.")
                else:
                    for signal in signals:
                        try:
                            result = await trader.execute_signal(signal)
                            if result.get("ok"):
                                logger.info(f"Trade opened: {signal.symbol}")
                            else:
                                logger.warning(f'Trade failed: {result.get("msg")}')
                        except Exception as se:
                            logger.error(f"Signal error: {se}")


                await asyncio.sleep(15 * 60)
            except Exception as e:
                logger.error(f"AutoTrader error: {e}")
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update): await deny(update); return
    text  = update.message.text.strip()
    parts = text.split()
    cmd   = parts[0].lower() if parts else ""

    if cmd in ("лонг","long","шорт","short"):
        side = "Buy" if cmd in ("лонг","long") else "Sell"
        await handle_trade(update, parts, side)
    elif cmd in ("закрыть","close","закрой"): await handle_close(update, parts)
    elif cmd in ("позиции","позы","positions","pos"): await handle_positions(update)
    elif cmd in ("баланс","balance","бал"): await handle_balance(update)
    elif cmd in ("цена","price","p") and len(parts) >= 2:
        sym = parse_symbol(parts[1]); price = engine().get_price(sym); sess = get_current_session()
        if price: await update.message.reply_text(f"💹 *{sym}*: `{price}`\n{sess['emoji']} {sess['name']}", parse_mode="Markdown")
        else: await update.message.reply_text(f"❌ Нет цены {sym}")
    elif cmd in ("риск","risk") and len(parts) >= 2:
        sym   = parse_symbol(parts[1])
        side  = "Buy" if len(parts) > 2 and parts[2].lower() in ("buy","лонг","long") else "Sell"
        entry = float(parts[3]) if len(parts) > 3 else (engine().get_price(sym) or 0)
        sl    = float(parts[4]) if len(parts) > 4 else 0.0
        tp    = float(parts[5]) if len(parts) > 5 else 0.0
        d     = build_trade_plan(sym, side, entry, sl, tp)
        await update.message.reply_text(d.format(), parse_mode="Markdown")
    elif cmd in ("авто","auto"):
        await handle_auto(update, parts)
    elif cmd in ("сессия","session"):
        side = parts[1].lower() if len(parts) > 1 else ""
        await update.message.reply_text(format_session_message(side), parse_mode="Markdown")
    elif cmd in ("контекст","context","рынок"):
        sym = parse_symbol(parts[1]) if len(parts) > 1 else "BTCUSDT"
        await update.message.reply_text("⏳ Анализирую...")
        try: await update.message.reply_text(market_ctx.format_summary(sym), parse_mode="Markdown")
        except Exception as e: await update.message.reply_text(f"❌ {e}")
    elif cmd in ("фандинг","funding"):
        sym  = parse_symbol(parts[1]) if len(parts) > 1 else "BTCUSDT"
        rate = engine().get_funding_rate(sym)
        if rate is not None: await update.message.reply_text(f"💰 Фандинг *{sym}*: `{rate:+.4f}%`", parse_mode="Markdown")
        else: await update.message.reply_text("❌ Нет данных")
    elif cmd in ("стата","stats","статистика"):
        n = int(parts[1]) if len(parts) > 1 else 0
        await update.message.reply_text(format_stats(n), parse_mode="Markdown")
    elif cmd in ("журнал","journal"): await update.message.reply_text(format_open_trades(), parse_mode="Markdown")
    elif cmd in ("лимиты","limits"):
        t = count_trades_today(); l = count_losing_trades_today(); p = daily_net_pnl()
        await update.message.reply_text(
            f"📊 *Дневные лимиты*\n{'─'*28}\n"
            f"Сделок: `{t}/5`\nУбытков: `{l}/2`\n"
            f"{'🟢' if p>=0 else '🔴'} PnL сегодня: `{p:+.2f}` USDT",
            parse_mode="Markdown")
    elif cmd in ("режим","mode") and len(parts) >= 2:
        m = parts[1].lower()
        if m in ("demo","демо"): current_mode["mode"]="demo"; await update.message.reply_text("🧪 Режим: *DEMO*", parse_mode="Markdown")
        elif m in ("live","реал","лайв"): current_mode["mode"]="live"; await update.message.reply_text("💰 Режим: *LIVE* ⚠️", parse_mode="Markdown")
    elif cmd in ("помощь","help","хелп","/help"): await handle_help(update)
    else: await update.message.reply_text("❓ Неизвестная команда. Напиши *помощь*.", parse_mode="Markdown")


# ─── АВТОТОРГОВЛЯ ────────────────────────────────────────────────────────────
async def handle_auto(update: Update, parts: list):
    if len(parts) < 2:
        status = "✅ Включена" if auto_enabled["enabled"] else "❌ Выключена"
        await update.message.reply_text(
            f"🤖 *Автоторговля*\nСтатус: {status}\n\n"
            f"`авто вкл` — включить\n"
            f"`авто выкл` — выключить\n"
            f"`авто скан` — один проход сейчас",
            parse_mode="Markdown")
        return

    cmd2 = parts[1].lower()
    if cmd2 in ("вкл","on","включить","start"):
        auto_enabled["enabled"] = True
        await update.message.reply_text(
            f"🤖 *Автоторговля включена!*\n"
            f"Сканирую каждые 15 минут.\n"
            f"Символы: 20 топ монет (BTC, ETH, SOL, BNB, XRP...)\n"
            f"Стратегия: SMC (OB + FVG + структура)\n"
            f"Лимиты: 5 сделок/день | 2 убытка/день",
            parse_mode="Markdown")

    elif cmd2 in ("выкл","off","выключить","stop"):
        auto_enabled["enabled"] = False
        await update.message.reply_text("⏸ *Автоторговля выключена*", parse_mode="Markdown")

    elif cmd2 in ("скан","scan"):
        await update.message.reply_text("🔍 Запускаю ручной скан...")
        try:
            from smc_strategy import AutoTrader
            trader = AutoTrader(engine=engine(), deposit=DEPOSIT, risk_pct=RISK_PCT, leverage=LEVERAGE)
            signals = await trader.scan_once()
            if not signals:
                await update.message.reply_text("📭 Сигналов не найдено. Рынок не даёт входа.")
            else:
                for sig in signals:
                    await update.message.reply_text(sig.format(), parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка скана: {e}")


# ─── ОТКРЫТИЕ СДЕЛКИ ─────────────────────────────────────────────────────────
async def handle_trade(update: Update, parts: list, side: str):
    if len(parts) < 2:
        await update.message.reply_text("❌ Формат: `лонг ada` или `лонг ada 0.385 0.370 0.430`", parse_mode="Markdown")
        return

    sym   = parse_symbol(parts[1])
    eng   = engine()
    mode  = current_mode["mode"]
    entry = eng.get_price(sym)
    if not entry: await update.message.reply_text(f"❌ Нет цены {sym}"); return

    if len(parts) > 2: entry = float(parts[2])
    sl = float(parts[3]) if len(parts) > 3 else 0.0
    tp = float(parts[4]) if len(parts) > 4 else 0.0

    decision = can_open_trade(sym, side, entry, sl, tp)
    if not decision.allowed:
        await update.message.reply_text(decision.format(), parse_mode="Markdown")
        return

    await update.message.reply_text(decision.format(), parse_mode="Markdown")
    sess = get_current_session()
    await update.message.reply_text(f"⏳ Отправляю ордер... {mode_badge()}")

    result = eng.place_order(symbol=sym, side=side, qty=decision.qty, sl=decision.sl, tp=decision.tp, leverage=decision.leverage)
    if not result["ok"]: await update.message.reply_text(f"❌ Bybit:\n`{result['msg']}`", parse_mode="Markdown"); return

    trade = add_trade(symbol=sym, side=side, entry=decision.entry, sl=decision.sl, tp=decision.tp, qty=decision.qty, risk_pct=RISK_PCT, leverage=decision.leverage, rr=decision.rr, mode=mode, order_id=result.get("orderId",""), session=sess["name"])
    t = count_trades_today(); l = count_losing_trades_today()
    side_emoji = "🟢 ЛОНГ" if side == "Buy" else "🔴 ШОРТ"
    await update.message.reply_text(
        f"✅ *Ордер открыт!* {mode_badge()}\n{'─'*28}\n"
        f"{side_emoji} *{sym}*\n"
        f"Qty: `{decision.qty}` | Entry: `{decision.entry}`\n"
        f"SL: `{decision.sl}` | TP: `{decision.tp}`\n"
        f"RR: `1:{decision.rr:.2f}` | Маржа: `{decision.margin} USDT`\n"
        f"{sess['emoji']} {sess['name']}\n{'─'*28}\n"
        f"Сделок: `{t}/5` | Убытков: `{l}/2`\n#️⃣ #{trade['id']}",
        parse_mode="Markdown")


async def handle_close(update: Update, parts: list):
    if len(parts) < 2: await update.message.reply_text("❌ Формат: `закрыть ada`", parse_mode="Markdown"); return
    sym    = parse_symbol(parts[1])
    result = engine().close_position(sym)
    if not result["ok"]: await update.message.reply_text(f"❌ {result['msg']}"); return
    pnl = result.get("closed_pnl", 0)
    close_trade(sym, engine().get_price(sym) or 0, pnl, DEPOSIT)
    await update.message.reply_text(f"✅ *Позиция закрыта!*\n{sym} {'🟢' if pnl>=0 else '🔴'} PnL: `{pnl:+.4f}` USDT", parse_mode="Markdown")


async def handle_positions(update: Update):
    data = engine().get_positions()
    if not data["ok"]: await update.message.reply_text(f"❌ {data['msg']}"); return
    positions = data["positions"]
    if not positions:
        sess = get_current_session()
        await update.message.reply_text(f"📋 Нет позиций {mode_badge()}\n{sess['emoji']} {sess['name']}"); return
    lines = [f"📂 *Позиции* {mode_badge()}\n{'─'*28}"]; total_pnl = 0
    for p in positions:
        pnl = p["unrealisedPnl"]; total_pnl += pnl
        lines.append(f"{'🟢' if p['side']=='Buy' else '🔴'} *{p['symbol']}* x{p['leverage']}\nQty: `{p['size']}` | Entry: `{p['entry']}`\nSL: `{p['sl'] or '—'}` | TP: `{p['tp'] or '—'}`\nPnL: `{pnl:+.4f}` USDT")
    lines.append(f"\nИтого: `{total_pnl:+.4f}` USDT")
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def handle_balance(update: Update):
    data = engine().get_balance()
    if not data["ok"]: await update.message.reply_text(f"❌ {data['msg']}"); return
    sess = get_current_session(); p = daily_net_pnl(); t = count_trades_today(); l = count_losing_trades_today()
    await update.message.reply_text(
        f"💼 *Баланс* {mode_badge()}\n{'─'*28}\n"
        f"Эквити:   `{data['equity']:.2f}` USDT\n"
        f"Доступно: `{data['available']:.2f}` USDT\n"
        f"Откр.PnL: `{data['unrealisedPnl']:+.4f}` USDT\n{'─'*28}\n"
        f"PnL сегодня: `{p:+.2f}` USDT\n"
        f"Сделок: `{t}/5` | Убытков: `{l}/2`\n"
        f"Режим: {auto_badge()}\n{'─'*28}\n"
        f"{sess['emoji']} {sess['name']}",
        parse_mode="Markdown")


async def handle_help(update: Update):
    sess = get_current_session()
    await update.message.reply_text(
        f"🤖 *SMC Trade Bot v4* {mode_badge()}\n{'─'*32}\n\n"
        f"*🤖 Автоторговля:*\n"
        f"`авто вкл` — включить автотрейдер\n"
        f"`авто выкл` — выключить\n"
        f"`авто скан` — ручной скан рынка\n\n"
        f"*📈 Ручная торговля:*\n"
        f"`лонг ada` — лонг по рынку\n"
        f"`шорт sol 145 142 155` — шорт с SL/TP\n"
        f"`закрыть ada` — закрыть позицию\n\n"
        f"*📊 Анализ:*\n"
        f"`контекст` — межрыночный анализ\n"
        f"`сессия` — текущая сессия\n"
        f"`фандинг btc` — ставка финансирования\n"
        f"`риск ada buy 0.385 0.370 0.430`\n"
        f"`цена sol` — цена\n\n"
        f"*💼 Портфель:*\n"
        f"`баланс` | `позиции` | `лимиты`\n"
        f"`журнал` | `стата`\n\n"
        f"*⚙️ Настройки:*\n"
        f"`режим demo` / `режим live`\n\n"
        f"{'─'*32}\n"
        f"Маржа: `{MARGIN_PER_TRADE} USDT` | Плечо: `{LEVERAGE}x`\n"
        f"Режим: {auto_badge()} | {mode_badge()}\n"
        f"{sess['emoji']} {sess['name']}",
        parse_mode="Markdown")


async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update): await deny(update); return
    await handle_help(update)

async def post_init(app):
    asyncio.create_task(session_watcher(app))
    asyncio.create_task(auto_trader_loop(app))
    logger.info("🚀 Все фоновые задачи запущены.")

def main():
    if not TG_TOKEN: print("❌ TG_TOKEN не задан"); return
    sess = get_current_session()
    print(f"🚀 SMC Trade Bot v4 | {current_mode['mode'].upper()}")
    print(f"   Маржа: {MARGIN_PER_TRADE} USDT | Плечо: {LEVERAGE}x")
    print(f"   Автоторговля: {'ВКЛ' if auto_enabled['enabled'] else 'ВЫКЛ'}")
    print(f"   Сессия: {sess['emoji']} {sess['name']}")
    app = ApplicationBuilder().token(TG_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Бот запущен!\n")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()