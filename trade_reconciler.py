"""
Trade reconciler.

Looks for positions that have been closed by Alpaca and records the
completed trade in the database.
"""

from execution import get_trading_client
from trade_tracker import load_trades, save_trades
import db


def reconcile():

    client = get_trading_client()

    open_positions = {
        p.symbol
        for p in client.get_all_positions()
    }

    tracked = load_trades()

    changed = False

    for ticker in list(tracked.keys()):

        if ticker in open_positions:
            continue

        try:

            orders = client.get_orders()

            buys = [
                o for o in orders
                if o.symbol == ticker
                and str(o.side).lower() == "buy"
                and o.filled_avg_price
            ]

            sells = [
                o for o in orders
                if o.symbol == ticker
                and str(o.side).lower() == "sell"
                and o.filled_avg_price
            ]

            if not buys or not sells:
                continue

            buy = max(buys, key=lambda o: o.filled_at)
            sell = max(sells, key=lambda o: o.filled_at)

            buy_price = float(buy.filled_avg_price)
            sell_price = float(sell.filled_avg_price)
            qty = float(sell.filled_qty)

            pnl = (sell_price - buy_price) * qty
            pnl_pct = ((sell_price - buy_price) / buy_price) * 100

            hold_hours = (
                sell.filled_at - buy.filled_at
            ).total_seconds() / 3600

            db.log_completed_trade(
                ticker=ticker,
                buy_time=buy.filled_at.isoformat(),
                sell_time=sell.filled_at.isoformat(),
                buy_price=buy_price,
                sell_price=sell_price,
                quantity=qty,
                pnl=pnl,
                pnl_pct=pnl_pct,
                hold_time_hours=hold_hours,
            )

            del tracked[ticker]
            changed = True

            print(f"Recorded completed trade for {ticker}")

        except Exception as e:
            print(f"Trade reconciliation failed for {ticker}: {e}")

    if changed:
        save_trades(tracked)
