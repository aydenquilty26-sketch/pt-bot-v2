"""
Entry point for stage 1: run the coarse parameter sweep against real
historical data and save the results to a CSV for review.

Usage (from the repo root):
    python -m backtest.run_sweep

Needs network access to fetch historical data via yfinance on first run -
after that, results are cached on disk in backtest/cache/ and reused.
"""

import os

import config
from backtest.data import load_all, get_backtest_date_range
from backtest.sweep import run_sweep, save_results_csv, DEFAULT_GRID


def main():

    start_date, end_date = get_backtest_date_range(config.BACKTEST_YEARS)

    print(f"Backtest window: {start_date} to {end_date} "
          f"({config.BACKTEST_YEARS} years)")
    print(f"Watchlist: {len(config.BACKTEST_WATCHLIST)} tickers")

    print("Loading price history (cached after first run)...")

    price_data = load_all(config.BACKTEST_WATCHLIST, start_date, end_date)
    spy_df = load_all(["SPY"], start_date, end_date).get("SPY")
    vix_df = load_all(["^VIX"], start_date, end_date).get("^VIX")

    if spy_df is None or spy_df.empty:
        raise SystemExit("Could not load SPY data - required as the master trading calendar.")
    if vix_df is None or vix_df.empty:
        raise SystemExit("Could not load VIX data - required for market regime scoring.")

    watchlist = list(price_data.keys())
    print(f"Loaded {len(watchlist)}/{len(config.BACKTEST_WATCHLIST)} tickers successfully")

    results = run_sweep(
        watchlist=watchlist,
        price_data=price_data,
        spy_df=spy_df,
        vix_df=vix_df,
        start_date=start_date,
        end_date=end_date,
        grid=DEFAULT_GRID,
    )

    output_path = os.path.join(
        os.path.dirname(__file__), "results", "sweep_results.csv"
    )
    save_results_csv(results, output_path)

    print()
    print("IMPORTANT: these results reflect technical + market regime "
          "signals only. Fundamental and news are not included - no free "
          "source for historical point-in-time data exists for either.")
    print()
    print("Next: look at the CSV for a broad plateau of good results "
          "across nearby parameter values, not a single isolated best "
          "number. An isolated spike is very likely overfitting, even if "
          "it's the best-looking row.")


if __name__ == "__main__":
    main()
