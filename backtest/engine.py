"""
Single-run backtest engine.

This calls strategy.build_proposal() and risk.validate_proposal() -
the actual functions the live bot uses - not a reimplementation of them.
Only two things are swapped out for a historical replay:
  1. Price data comes from a pre-fetched historical slice instead of a
     live yfinance call (via technical.py's hist= parameter).
  2. Execution is simulated (SimulatedPortfolio) instead of hitting
     Alpaca's API.

Fundamental and news signals are NOT included - there's no free source
for historical point-in-time fundamentals or historical news headlines,
so including them here would mean testing against a signal that couldn't
have existed on that historical date (lookahead bias). They're passed in
with confidence=0.0, which strategy.py's own weighting logic already
excludes from the composite score - no monkeypatching of AGENT_WEIGHTS
needed, the existing "skip signals with zero effective weight" logic in
strategy.py handles this cleanly on its own.

Every result from this engine should be labeled: validated technical +
market regime only, not the full 3-agent live system.
"""

from contextlib import contextmanager

import pandas as pd

import config
from strategy import build_proposal
from risk import validate_proposal
from signals.technical import get_technical_signal
from signals.market_regime import get_market_regime


@contextmanager
def _override_config(**overrides):
    """Temporarily mutates config module attributes for one backtest run,
    then restores the originals. This is what lets the sweep test
    different STOP_LOSS_PCT/TRADE_SCORE_THRESHOLD/etc values while still
    calling the real strategy.py/risk.py code unmodified - those modules
    read config.X at call time, not at import time.

    Not thread-safe / not safe for parallel runs, since it mutates shared
    module state - fine for the sequential sweep this stage targets."""

    original = {}
    for key, value in overrides.items():
        original[key] = getattr(config, key)
        setattr(config, key, value)
    try:
        yield
    finally:
        for key, value in original.items():
            setattr(config, key, value)


def _align_to_calendar(price_data: dict, calendar_index) -> dict:
    """Reindexes every ticker's price history onto a single shared trading
    calendar (SPY's index, since SPY trades every market day), forward-
    filling small gaps. Avoids per-day KeyErrors for tickers with minor
    data gaps and keeps the day loop simple."""

    aligned = {}
    for ticker, df in price_data.items():
        aligned[ticker] = df.reindex(calendar_index, method="ffill").dropna()
    return aligned


def run_backtest(
    watchlist: list,
    price_data: dict,
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    start_date: str,
    end_date: str,
    params: dict = None,
    starting_cash: float = 100000.0,
) -> dict:
    """
    price_data: {ticker: DataFrame} from backtest.data.load_all()
    params: optional overrides, e.g. {"TRADE_SCORE_THRESHOLD": 0.35,
            "STOP_LOSS_PCT": 0.025, "TAKE_PROFIT_PCT": 0.05}
    """

    from backtest.simulated_portfolio import SimulatedPortfolio

    params = params or {}

    calendar = spy_df.index[
        (spy_df.index >= pd.Timestamp(start_date, tz=spy_df.index.tz))
        & (spy_df.index <= pd.Timestamp(end_date, tz=spy_df.index.tz))
    ]

    aligned = _align_to_calendar(price_data, spy_df.index)

    portfolio = SimulatedPortfolio(starting_cash)

    def price_lookup(ticker):
        # Latest known close as of "today" in the loop below - set per
        # iteration via closure variable `current_date`.
        df = aligned.get(ticker)
        if df is None or current_date not in df.index:
            return 0.0
        return float(df.loc[current_date, "Close"])

    def day_bar_lookup(ticker, date):
        df = aligned.get(ticker)
        if df is None or date not in df.index:
            return None
        return df.loc[date]

    WARMUP_DAYS = 60  # matches technical.py's own 50-day minimum + buffer

    with _override_config(**params):

        for current_date in calendar:

            # Every open position gets checked against its stop/target
            # every single day, regardless of whether any new signal
            # fires today - this is the property that makes the backtest
            # actually test the "protection survives even if the strategy
            # agent is silent" behavior, not just assume it.
            portfolio.check_exits(current_date, day_bar_lookup)

            spy_slice = spy_df.loc[:current_date].tail(90)
            vix_slice = vix_df.loc[:current_date].tail(90)

            if len(spy_slice) < WARMUP_DAYS:
                portfolio.record_equity(current_date, price_lookup)
                continue

            regime = get_market_regime(spy_hist=spy_slice, vix_hist=vix_slice)

            total_exposure = portfolio.total_exposure(price_lookup)
            equity = portfolio.equity(price_lookup)

            for ticker in watchlist:

                df = aligned.get(ticker)
                if df is None or current_date not in df.index:
                    continue

                # Trailing window only, not the full history-to-date -
                # technical.py's longest lookback is a 50-day SMA, so 90
                # rows is comfortable buffer. Without this cap, each day's
                # slice grows for the entire backtest length, making the
                # whole run scale O(n^2) instead of O(n) per ticker.
                hist_slice = df.loc[:current_date].tail(90)
                if len(hist_slice) < WARMUP_DAYS:
                    continue

                tech_signal = get_technical_signal(ticker, hist=hist_slice)

                # Confidence 0.0 -> strategy.py's own weighting loop
                # excludes these entirely. Not lookahead-safe data to
                # include, so they contribute nothing here on purpose.
                fund_signal = {"agent": "fundamental", "ticker": ticker,
                                "score": 0.0, "confidence": 0.0,
                                "rationale": "excluded from backtest - no free historical data"}
                news_signal = {"agent": "news", "ticker": ticker,
                                "score": 0.0, "confidence": 0.0,
                                "rationale": "excluded from backtest - no free historical data"}

                signals = [tech_signal, fund_signal, news_signal]

                has_position = portfolio.has_position(ticker)

                proposal = build_proposal(
                    ticker, signals, has_position,
                    threshold_adjustment=regime["threshold_adjustment"],
                )

                if proposal is None:
                    continue

                risk_result = validate_proposal(
                    proposal, equity, total_exposure,
                    risk_multiplier=regime["risk_multiplier"],
                )

                if not risk_result["approved"]:
                    continue

                current_price = float(hist_slice["Close"].iloc[-1])

                if proposal["action"] == "buy":
                    if portfolio.buy(ticker, current_date, current_price,
                                      risk_result["position_size_usd"]):
                        total_exposure = portfolio.total_exposure(price_lookup)

                elif proposal["action"] == "sell":
                    portfolio.sell(ticker, current_date, current_price, reason="signal")
                    total_exposure = portfolio.total_exposure(price_lookup)

            portfolio.record_equity(current_date, price_lookup)

    return {
        "params": params,
        "trades": portfolio.completed_trades,
        "equity_curve": portfolio.equity_curve,
        "starting_cash": starting_cash,
        "final_equity": portfolio.equity_curve[-1]["equity"] if portfolio.equity_curve else starting_cash,
    }
