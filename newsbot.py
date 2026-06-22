import asyncio
import logging,requests
from telethon import TelegramClient,events
from telegram.ext import ApplicationBuilder,CommandHandler
from telegram import Update
from telegram.ext import ApplicationBuilder,CommandHandler logging.basicConfig(level=logging.WARNING)
API_ID=31302205
API_HASH='f8050c118642ca3b4a92414798136ed5'
BOT_TOKEN='8138415576:AAEY6-m9sPogteVGp7ZFiN8ITHZ2Ar09FmE'
CMC_KEY='30dd4f5838d84656afc425ed4e3e18e1'
CHANNELS=[]
MY_CHAT_ID=None
news_buffer=[]
COINS={'BTC':['btc','bitcoin'],'ETH':['eth','ethereum'],'SOL':['sol','solana'],'ADA':['ada','cardano'],'BNB':['bnb','binance']}
BULLISH=['bull','bullish','pump','moon','green','buy','growth','long','накопление','рост']
BEARISH=['bear','bearish','dump','sell','crash','red','down','drop','short','падение','обвал']
SESSION={'asia':[0,8],'london':[8,16],'newyork':[13,22]}

def get_session():
    h=datetime.now().hour
    if 0<=h<8:return 'Asia'
    elif 8<=h<16:return 'London'
    else:return 'NewYork'

def analyze(text):
    t=text.lower()
    bull=sum(1 for w in BULLISH if w in t)
    bear=sum(1 for w in BEARISH if w in t)
    coins=[c for c,keys in COINS.items() if any(k in t for k in keys)]
    return bull,bear,coins

def get_prices(symbols):
    try:
        url='https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
        headers={'X-CMC_PRO_API_KEY':CMC_KEY}
        params={'symbol':','.join(symbols),'convert':'USD'}
        r=requests.get(url,headers=headers,params=params,timeout=10)
        data=r.json()
        result={}
        for sym in symbols:
            if sym in data.get('data',{}):
                q=data['data'][sym]['quote']['USD']
                result[sym]={'price':q['price'],'change':q['percent_change_24h']}
        return result
    except:
        return {}

async def start(update,context):
    global MY_CHAT_ID
    MY_CHAT_ID=update.effective_chat.id
    await update.message.reply_text('Bot ready!
/add @channel
/forecast
/price BTC
/list
/clear')

async def add_channel(update,context):
    if not context.args:
        await update.message.reply_text('Example: /add @crypto_news')
        return
    ch=context.args[0]
    if not ch.startswith('@'):ch='@'+ch
    if ch not in CHANNELS:
        CHANNELS.append(ch)
        await update.message.reply_text('Added: '+ch)
    else:
        await update.message.reply_text('Already exists')

async def list_channels(update,context):
    await update.message.reply_text('
'.join(CHANNELS) if CHANNELS else 'No channels. /add @channel')

async def price_cmd(update,context):
    symbols=[s.upper() for s in context.args] if context.args else ['BTC','ETH','SOL']
    prices=get_prices(symbols)
    msg='Prices:
'
    for coin,data in prices.items():
        arrow='up' if data['change']>0 else 'down'
        msg+=f'{coin}: {data["price"]:,.2f} ({data["change"]:+.2f}%) {arrow}
'
    await update.message.reply_text(msg or 'Error')

async def forecast_cmd(update,context):
    if not news_buffer:
        await update.message.reply_text('No news yet')
        return
    bull=sum(1 for t in news_buffer for w in BULLISH if w in t.lower())
    bear=sum(1 for t in news_buffer for w in BEARISH if w in t.lower())
    if bull>bear*1.3:s='BULLISH - consider LONG'
    elif bear>bull*1.3:s='BEARISH - consider SHORT'
    else:s='NEUTRAL - wait'
    session=get_session()
    await update.message.reply_text(f'Forecast from {len(news_buffer)} news
Session: {session}
{s}
Bull:{bull} Bear:{bear}')

async def clear_cmd(update,context):
    news_buffer.clear()
    await update.message.reply_text('Cleared')

async def run_bot():
    app=ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start',start))
    app.add_handler(CommandHandler('add',add_channel))
    app.add_handler(CommandHandler('list',list_channels))
    app.add_handler(CommandHandler('price',price_cmd))
    app.add_handler(CommandHandler('forecast',forecast_cmd))
    app.add_handler(CommandHandler('clear',clear_cmd))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    client=TelegramClient('session',API_ID,API_HASH)
    await client.start()
    @client.on(events.NewMessage())
    async def handler(event):
        if MY_CHAT_ID is None:return
        try:
            chat=await event.get_chat()
            username=getattr(chat,'username',None)
            if not username or f'@{username}' not in CHANNELS:return
            text=event.message.text or ''
            if not text:return
            bull,bear,coins=analyze(text)
            news_buffer.append(text)
            if len(news_buffer)>100:news_buffer.pop(0)
            if bull>0 or bear>0:
                tone='BULLISH' if bull>bear else 'BEARISH' if bear>bull else 'NEUTRAL'
                coins_str=','.join(coins) if coins else 'market'
                session=get_session()
                msg=f'News @{username}
Session:{session} {tone}
Coins:{coins_str}
{text[:200]}
/forecast'
                await app.bot.send_message(chat_id=MY_CHAT_ID,text=msg)
        except Exception as e:
            logging.error(e)
    print('Newsbot started!')
    await client.run_until_disconnected()

asyncio.run(run_bot())
