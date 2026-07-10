from datetime import datetime, timezone

import db


def record_buy(ticker, price, qty):
    db.save_open_position(
        ticker=ticker,
        qty=qty,
        entry_price=price,
    )


def record_sell(ticker, exit_price=None):
    position = db.get_open_position(ticker)

    if position is None:
        return None

    ticker = position[0]
    qty = float(position[1])
    entry_price = float(position[2])
    opened_at = position[3]

    if exit_price is None:
        exit_price = entry_price

    buy_time = datetime.fromisoformat(opened_at)
    sell_time = datetime.now(timezone.utc)

    pnl = (exit_price - entry_price) * qty
    pnl_pct = ((exit_price - entry_price) / entry_price) * 100

    hold_time_hours = (
        sell_time - buy_time
    ).total_seconds() / 3600

    db.log_completed_trade(
        ticker=ticker,
        buy_time=opened_at,
        sell_time=sell_time.isoformat(),
        buy_price=entry_price,
        sell_price=exit_price,
        quantity=qty,
        pnl=pnl,
        pnl_pct=pnl_pct,
        hold_time_hours=hold_time_hours,
    )

    db.remove_open_position(ticker)

    return {
        "ticker": ticker,
        "qty": qty,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "pnl": pnl,
    }
