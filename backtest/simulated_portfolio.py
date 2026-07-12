"""
Simulated portfolio for the backtest engine.

This is deliberately NOT a mock of Alpaca's client API - execution.py's
real bracket-order construction doesn't apply to historical replay. What
it replicates instead is the *outcome* Alpaca's bracket orders produce:
the same share-count formula, the same stop/target price formula, and
critically, the same "fires even if the strategy agent said nothing
today" behavior, checked every single day regardless of whether a new
signal was generated - that property is a real structural strength of
the live bot and the backtest needs to actually test it, not assume it.
"""

import config


class SimulatedPortfolio:

    def __init__(self, starting_cash: float):
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.positions = {}  # ticker -> {qty, entry_price, entry_date, stop_price, target_price}
        self.completed_trades = []
        self.equity_curve = []  # [{date, equity}]

    def has_position(self, ticker: str) -> bool:
        return ticker in self.positions

    def total_exposure(self, price_lookup) -> float:
        return sum(
            pos["qty"] * price_lookup(ticker)
            for ticker, pos in self.positions.items()
        )

    def equity(self, price_lookup) -> float:
        return self.cash + self.total_exposure(price_lookup)

    def buy(self, ticker: str, date, price: float, position_size_usd: float) -> bool:
        """Same sizing formula as execution.py's submit_buy: whole shares,
        floor division. Returns False (no-op) if it can't afford even one
        share - matching the live "position size below 1 share" reject."""

        if price <= 0:
            return False

        qty = int(position_size_usd // price)

        if qty < 1:
            return False

        cost = qty * price

        # Safety clamp - shouldn't normally trigger since risk.py already
        # sizes within equity, but a stale price_lookup shouldn't be able
        # to put the simulated account into negative cash.
        if cost > self.cash:
            qty = int(self.cash // price)
            cost = qty * price

        if qty < 1:
            return False

        stop_price = round(price * (1 - config.STOP_LOSS_PCT), 2)
        target_price = round(price * (1 + config.TAKE_PROFIT_PCT), 2)

        self.cash -= cost
        self.positions[ticker] = {
            "qty": qty,
            "entry_price": price,
            "entry_date": date,
            "stop_price": stop_price,
            "target_price": target_price,
        }

        return True

    def sell(self, ticker: str, date, price: float, reason: str) -> dict:
        pos = self.positions.pop(ticker, None)

        if pos is None:
            return None

        proceeds = pos["qty"] * price
        self.cash += proceeds

        pnl = (price - pos["entry_price"]) * pos["qty"]
        pnl_pct = ((price - pos["entry_price"]) / pos["entry_price"]) * 100
        hold_days = (date - pos["entry_date"]).days

        trade = {
            "ticker": ticker,
            "entry_date": pos["entry_date"],
            "exit_date": date,
            "entry_price": pos["entry_price"],
            "exit_price": price,
            "qty": pos["qty"],
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "hold_days": hold_days,
            "exit_reason": reason,
        }

        self.completed_trades.append(trade)
        return trade

    def check_exits(self, date, day_bar_lookup):
        """Called every day, before evaluating any new signals - checks
        every open position's stop/target against that day's high/low.
        This runs regardless of whether the strategy agent produced a
        proposal today, matching the live bot's server-side bracket
        orders. If both stop and target are technically hit the same day,
        the stop is assumed to have fired first - the conservative
        assumption, since which one actually happened first intraday
        can't be known from daily bars alone."""

        for ticker in list(self.positions.keys()):

            bar = day_bar_lookup(ticker, date)
            if bar is None:
                continue

            pos = self.positions[ticker]
            day_low = bar["Low"]
            day_high = bar["High"]

            if day_low <= pos["stop_price"]:
                self.sell(ticker, date, pos["stop_price"], reason="stop_loss")
            elif day_high >= pos["target_price"]:
                self.sell(ticker, date, pos["target_price"], reason="take_profit")

    def record_equity(self, date, price_lookup):
        self.equity_curve.append({
            "date": date,
            "equity": round(self.equity(price_lookup), 2),
        })
