import json
import os
from datetime import datetime

trade = {
    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "coin": "ADAUSDT",
    "direction": "long",
    "entry": 0.246,
    "size_usdt": 199.26,
    "margin": 9.96,
    "leverage": 20,
    "take_profit": 0.2486,
    "stop_loss": 0.2434,
    "liquidation": 0.2362,
    "session": "Europe",
    "result": "open"
}

file = "trades.json"
trades = json.load(open(file)) if os.path.exists(file) else []
trades.append(trade)
json.dump(trades, open(file, "w"), indent=2)
print("Сделка сохранена!")
