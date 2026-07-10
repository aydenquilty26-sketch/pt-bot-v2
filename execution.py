"""
Execution agent. The only agent that submits orders.
"""

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    TakeProfitRequest,
    StopLossRequest,
)
from alpaca.trading.enums import (
    OrderSide,
    TimeInForce,
    OrderClass,
)

import config
from trade_tracker import record_buy

if not config.API_KEY or not config.API_SECRET:
    raise ValueError(
        "Missing Alpaca API keys. Set APCA_API_KEY_ID and APCA_API_SECRET_KEY."
    )

_client = TradingClient(
    config.API_KEY,
    config.API_SECRET,
    paper=config.IS_PAPER,
)


def get_trading_client() -> TradingClient:
    return _client


def submit_buy(ticker: str, position_size_usd: float, last_price: float) -> dict:

    qty = int(position_size_usd // last_price)

    if qty < 1:
        return {
            "success": False,
            "reason": "position size below 1 share",
            "order_id": None,
        }

    stop_price = round(last_price * (1 - config.STOP_LOSS_PCT), 2)
    take_profit_price = round(last_price * (1 + config.TAKE_PROFIT_PCT), 2)

    order_req = MarketOrderRequest(
        symbol=ticker,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(
            limit_price=take_profit_price
        ),
        stop_loss=StopLossRequest(
            stop_price=stop_price
        ),
    )

    try:

        order = _client.submit_order(order_req)

        record_buy(
            ticker=ticker,
            price=last_price,
            qty=qty,
        )

        return {
            "success": True,
            "reason": "submitted",
            "order_id": str(order.id),
        }

    except Exception as e:

        return {
            "success": False,
            "reason": f"broker error: {e}",
            "order_id": None,
        }


def submit_sell(ticker: str, qty: float) -> dict:

    order_req = MarketOrderRequest(
        symbol=ticker,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    )

    try:

        order = _client.submit_order(order_req)

        # Trade tracking stays untouched here on purpose. We don't yet know
        # the real fill price - this is a market order, not a guarantee.
        # The reconciler picks up the closed position next cycle and logs
        # it using the broker's actual filled_avg_price.

        return {
            "success": True,
            "reason": "submitted",
            "order_id": str(order.id),
        }

    except Exception as e:

        return {
            "success": False,
            "reason": f"broker error: {e}",
            "order_id": None,
        }
