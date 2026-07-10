"""
Portfolio monitor agent. Source of truth for what's actually held.
Reads directly from the broker rather than tracking state locally, so it
can never drift out of sync with reality.
"""
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus
from execution import get_trading_client
import db


def get_account_state() -> dict:
    client = get_trading_client()
    account = client.get_account()
    positions = client.get_all_positions()

    # Also check pending/open orders - a DAY order placed while markets
    # are closed sits "open" (not filled, not a position) until the next
    # session. Without checking this too, the bot would think it has no
    # position and submit duplicate buy orders on every cycle until one
    # finally fills - stacking well past the intended position size.
    open_orders = client.get_orders(
        filter=GetOrdersRequest(status=QueryOrderStatus.OPEN)
    )
    open_order_tickers = {o.symbol for o in open_orders}

    positions_by_ticker = {p.symbol: p for p in positions}
    positions_value = sum(float(p.market_value) for p in positions)

    equity = float(account.equity)
    cash = float(account.cash)

    db.log_equity(equity=equity, cash=cash, positions_value=positions_value)

    return {
        "equity": equity,
        "cash": cash,
        "positions_value": positions_value,
        "positions_by_ticker": positions_by_ticker,
        "open_order_tickers": open_order_tickers,
    }
