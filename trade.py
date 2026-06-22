import requests,time,hmac,hashlib,json,os,sys

API='NEvmxUBuvFZURKynoD'
SEC='1Bjmm1R05qzkvqjZvn4A5ThbeIs1VYA5AwnJ'
BASE='https://api-demo.bybit.com'

def sign(p):
    ts=str(int(time.time()*1000))
    b=json.dumps(p)
    s=hmac.new(SEC.encode(),(ts+API+'5000'+b).encode(),hashlib.sha256).hexdigest()
    return ts,s,b

def get_price(symbol):
    r=requests.get(f'{BASE}/v5/market/tickers?category=linear&symbol={symbol}').json()
    return float(r['result']['list'][0]['lastPrice'])

def order(symbol,side,usdt=10,tp=None,sl=None):
    price=get_price(symbol)
    qty=round(usdt*20/price)
    p={'category':'linear','symbol':symbol,'side':side,'orderType':'Market','qty':str(qty),'timeInForce':'GTC'}
    if tp: p['takeProfit']=str(tp)
    if sl: p['stopLoss']=str(sl)
    ts,s,b=sign(p)
    h={'X-BAPI-API-KEY':API,'X-BAPI-TIMESTAMP':ts,'X-BAPI-SIGN':s,'X-BAPI-RECV-WINDOW':'5000','Content-Type':'application/json'}
    r=requests.post(f'{BASE}/v5/order/create',headers=h,data=b).json()
    if r['retCode']==0:
        print(f"OK! {side} {symbol} цена={price} qty={qty}")
        t={'date':time.strftime('%Y-%m-%d %H:%M'),'coin':symbol,'direction':side,'entry':price,'qty':qty,'usdt':usdt,'tp':tp,'sl':sl,'result':'open'}
        trades=json.load(open('trades.json')) if os.path.exists('trades.json') else []
        trades.append(t)
        json.dump(trades,open('trades.json','w'),indent=2)
    else:
        print('Ошибка:',r['retMsg'])

args=' '.join(sys.argv[1:]).lower().split()
if len(args)>=2:
    side='Buy' if args[0]=='лонг' else 'Sell'
    symbol=args[1].upper()+'USDT' if 'USDT' not in args[1].upper() else args[1].upper()
    usdt=float(args[2]) if len(args)>2 else 10
    tp=float(args[3]) if len(args)>3 else None
    sl=float(args[4]) if len(args)>4 else None
    order(symbol,side,usdt,tp,sl)
else:
    print('Использование:')
    print('python3 trade.py лонг ada')
    print('python3 trade.py шорт btc 20')
    print('python3 trade.py лонг ada 10 0.26 0.24')
