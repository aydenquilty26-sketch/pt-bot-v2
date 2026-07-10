"""
Trade reconciler.

Single source of truth for closing out a trade. A ticker is tracked as
open (in trade_tracker.py's JSON file) from the moment a buy fills until
this function sees the position is no longer open at the broker - whether
that happened because the strategy agent decided to sell, or because a
stop-loss / take-profit fired automatically on Alpaca's side.

Either way, we always pull the real fill price from Alpaca's own order
records rather than trusting anything guessed locally, since market
orders don't fill at a known price in advance.
"""

from datetime import datetime, timezone

from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

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

        # Position is still open at the broker - nothing to reconcile yet.
        if ticker in open_positions:
            continue

        try:
            buy_time = datetime.fromisoformat(tracked[ticker]["buy_time"])

            # Ask the broker specifically for this symbol's closed orders,
            # newest first. Using status=CLOSED (not the default, which is
            # OPEN) is what makes this actually find filled orders.
            closed_orders = client.get_orders(
                filter=GetOrdersRequest(
                    status=QueryOrderStatus.CLOSED,
                    symbols=[ticker],
                    limit=20,
                    direction="desc",
                )
            )

            sell_order = None

            for order in closed_orders:

                if "sell" not in str(order.side).lower():
                    continue

                if order.filled_avg_price is None:
                    continue

                if order.filled_at is None:
                    continue

                # Only accept a sell that closed after this specific buy -
                # guards against pairing up the wrong round trip if this
                # ticker has been traded more than once.
                filled_at = order.filled_at
                if filled_at.tzinfo is None:
                    filled_at = filled_at.replace(tzinfo=timezone.utc)

                if filled_at < buy_time:
                    continue

                sell_order = order
                break

            if sell_order is None:
                # Sell likely hasn't filled yet (e.g. submitted right at
                # market close). Leave it tracked and try again next cycle.
                continue

            buy_price = float(tracked[ticker]["buy_price"])
            qty = float(tracked[ticker]["quantity"])
            sell_price = float(sell_order.filled_avg_price)

            sell_time = sell_order.filled_at
            if sell_time.tzinfo is None:
                sell_time = sell_time.replace(tzinfo=timezone.utc)

            pnl = (sell_price - buy_price) * qty
            pnl_pct = ((sell_price - buy_price) / buy_price) * 100
            hold_time_hours = (sell_time - buy_time).total_seconds() / 3600

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

            print(f"Recorded completed trade for {ticker}: P/L ${pnl:,.2f} ({pnl_pct:.2f}%)")

        except Exception as e:
            print(f"Trade reconciliation failed for {ticker}: {e}")

    if changed:
        save(tracked)
