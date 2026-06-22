import subprocess
from telegram import Update
from telegram.ext import ApplicationBuilder,MessageHandler,filters,ContextTypes,CommandHandler

TOKEN='8138415576:AAEY6-m9sPogteVGp7ZFiN8ITHZ2Ar09FmE'

async def start(update,ctx):
    await update.message.reply_text('Bot ready!\nExample: long ada\nor: short btc 20')

async def handle(update,ctx):
    text=update.message.text.lower().strip()
    words=text.split()
    if len(words)>=2 and words[0] in ['long','short','long','short']:
        r=subprocess.run(['python3','trade.py']+words,capture_output=True,text=True,cwd='/home/jon68/bybit_bot')
        await update.message.reply_text(r.stdout or r.stderr or 'Error')
    else:
        await update.message.reply_text('Send: long ada or short btc')

app=ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler('start',start))
app.add_handler(MessageHandler(filters.TEXT&~filters.COMMAND,handle))
print('Bot started!')
app.run_polling()
