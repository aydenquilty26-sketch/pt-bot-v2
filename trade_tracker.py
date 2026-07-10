import json
import os
from datetime import datetime

FILE = "open_trades.json"


def load():
    if not os.path.exists(FILE):
        return {}

    with open(FILE, "r") as f:
        return json.load(f)


def save(data):
    with open(FILE, "w") as f:
        json.dump(data, f, indent=2)


def record_buy(ticker, price, qty):
    trades = load()

    trades[ticker] = {
        "buy_price": float(price),
        "quantity": float(qty),
        "buy_time": datetime.utcnow().isoformat()
    }

    save(trades)


def record_sell(ticker):
    trades = load()

    trade = trades.pop(ticker, None)

    save(trades)

    return trade
