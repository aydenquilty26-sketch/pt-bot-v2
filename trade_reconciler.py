"""
Trade reconciler.

Looks for positions that have been closed by Alpaca (manual sell,
take-profit, stop-loss, etc.) and writes completed trades into the
database.
"""

from datetime import datetime, timezone

import db
from execution import get_trading_client
from trade_tracker import load, save


def reconcile():

    client = get_trading_client()

    open_positions = {
        p.symbol
        for p in client.get_all_positions()
    }

    tracked = load()

    changed = False

    for ticker in list(tracked.keys()):

        # Position is still open.
        if ticker in open_positions:
            continue

        try:

            orders = client.get_orders()

            buy = None
            sell = None

            for order in orders:

                if order.symbol != ticker:
                    continue

                side = str(order.side).lower()

                if "buy" in side:
                    buy = order

                elif "sell" in side:
                    sell = order

            if buy is None or sell is None:
                continue

            buy_price = float(buy.filled_avg_price)
            sell_price = float(sell.filled_avg_price)
            qty = float(sell.filled_qty)

            buy_time = datetime.fromisoformat(
                tracked[ticker]["buy_time"]
            )

            sell_time = datetime.now(timezone.utc)

            pnl = (sell_price - buy_price) * qty

            pnl_pct = (
                (sell_price - buy_price)
                / buy_price
            ) * 100

            hold_time_hours = (
                sell_time - buy_time
            ).total_seconds() / 3600

            db.log_completed_trade(
                ticker=ticker,
                buy_time=buy_time.isoformat(),
                sell_time=sell_time.isoformat(),
                buy_price=buy_price,
                sell_price=sell_price,
                quantity=qty,
                pnl=pnl,
                pnl_pct=pnl_pct,
                hold_time_hours=hold_time_hours,
            )

            del tracked[ticker]
            changed = True

            print(f"Recorded completed trade for {ticker}")

        except Exception as e:
            print(f"Trade reconciliation failed for {ticker}: {e}")

    if changed:
        save(tracked)
