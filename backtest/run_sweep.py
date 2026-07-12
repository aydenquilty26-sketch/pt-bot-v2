"""
Entry point for stage 1: run the coarse parameter sweep against real
historical data and save the results to a CSV for review.

Usage (from the repo root):
    python -m backtest.run_sweep            # full sweep - 35 tickers, 216 combos
    QUICK=1 python -m backtest.run_sweep     # pilot - 5 tickers, 8 combos

Run QUICK=1 first. There's no reliable estimate of how long the full
sweep takes without actually profiling it against real data, which
wasn't possible in the environment this was built in (no network access).
The pilot run gives a real per-combination timing number you can
extrapolate from before committing to the full 216-combination sweep.

Needs network access to fetch historical data via yfinance on first run -
after that, results are cached on disk in backtest/cache/ and reused.
"""

import os
import time

import config
from backtest.data import load_all, get_backtest_date_range
from backtest.sweep import run_sweep, save_results_csv, DEFAULT_GRID

QUICK_GRID = {
    "TRADE_SCORE_THRESHOLD": [0.35, 0.45],
    "STOP_LOSS_PCT": [0.025, 0.04],
    "TAKE_PROFIT_PCT": [0.05, 0.08],
}


def main():

    quick = os.getenv("QUICK", "0") == "1"

    start_date, end_date = get_backtest_date_range(config.BACKTEST_YEARS)

    watchlist_to_fetch = (
        config.BACKTEST_WATCHLIST[:5] if quick else config.BACKTEST_WATCHLIST
    )
    grid = QUICK_GRID if quick else DEFAULT_GRID

    print(f"Mode: {'QUICK PILOT' if quick else 'FULL SWEEP'}")
    print(f"Backtest window: {start_date} to {end_date} "
          f"({config.BACKTEST_YEARS} years)")
    print(f"Watchlist: {len(watchlist_to_fetch)} tickers")

    print("Loading price history (cached after first run)...")

    price_data = load_all(watchlist_to_fetch, start_date, end_date)
    spy_df = load_all(["SPY"], start_date, end_date).get("SPY")
    vix_df = load_all(["^VIX"], start_date, end_date).get("^VIX")

    if spy_df is None or spy_df.empty:
        raise SystemExit("Could not load SPY data - required as the master trading calendar.")
    if vix_df is None or vix_df.empty:
        raise SystemExit("Could not load VIX data - required for market regime scoring.")

    watchlist = list(price_data.keys())
    print(f"Loaded {len(watchlist)}/{len(watchlist_to_fetch)} tickers successfully")

    started = time.time()

    results = run_sweep(
        watchlist=watchlist,
        price_data=price_data,
        spy_df=spy_df,
        vix_df=vix_df,
        start_date=start_date,
        end_date=end_date,
        grid=grid,
    )

    elapsed = time.time() - started
    per_combo = elapsed / len(results) if results else 0

    output_name = "sweep_results_quick.csv" if quick else "sweep_results.csv"
    output_path = os.path.join(
        os.path.dirname(__file__), "results", output_name
    )
    save_results_csv(results, output_path)

    print()
    print(f"Elapsed: {elapsed:.1f}s for {len(results)} combinations "
          f"({per_combo:.2f}s/combination)")

    if quick:
        full_combo_count = 1
        for values in DEFAULT_GRID.values():
            full_combo_count *= len(values)
        full_ticker_ratio = len(config.BACKTEST_WATCHLIST) / max(len(watchlist), 1)
        rough_estimate_minutes = (
            per_combo * full_combo_count * full_ticker_ratio
        ) / 60
        print(f"Rough full-sweep estimate: ~{rough_estimate_minutes:.0f} minutes "
              f"({full_combo_count} combinations x {len(config.BACKTEST_WATCHLIST)} tickers). "
              f"This is a linear extrapolation from a 5-ticker/8-combination "
              f"sample, so treat it as a ballpark, not a guarantee.")

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
