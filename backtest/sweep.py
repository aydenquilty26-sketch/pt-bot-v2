"""
Stage 1: parameter sweep -> heat map data.

Coarse grid first, per the plan - widely-spaced values across the 3
highest-impact parameters (TRADE_SCORE_THRESHOLD, STOP_LOSS_PCT,
TAKE_PROFIT_PCT), everything else held at current config defaults. Once
a promising region is visible in the results, a second fine-grained sweep
narrows in on just that region - this file supports both by accepting
any grid, not just the default coarse one.

This stage does NOT judge which result is "best" - that's what stages
2 (Monte Carlo) and 3 (cluster analysis) are for for. This just runs
every combination and reports the raw numbers so a human (or the later
stages) can look for a plateau vs. an isolated spike.
"""

import itertools
import csv
import os

from backtest.engine import run_backtest
from backtest.stats import summarize

# Coarse default grid - widely spaced on purpose. Narrow this to a fine
# grid around whatever region looks promising once this first pass runs.
DEFAULT_GRID = {
    "TRADE_SCORE_THRESHOLD": [0.25, 0.30, 0.35, 0.40, 0.45, 0.50],
    "STOP_LOSS_PCT": [0.02, 0.025, 0.03, 0.035, 0.04, 0.05],
    "TAKE_PROFIT_PCT": [0.04, 0.05, 0.06, 0.08, 0.10, 0.12],
}


def run_sweep(
    watchlist: list,
    price_data: dict,
    spy_df,
    vix_df,
    start_date: str,
    end_date: str,
    grid: dict = None,
    starting_cash: float = 100000.0,
) -> list:
    """Returns a list of {params, stats} dicts, one per grid combination.
    This is the raw heat map data - total_trades count is worth checking
    per row, since a combination with very few trades (e.g. under 15-20)
    produced a number that shouldn't be trusted regardless of how good it
    looks, same logic as the human day-trading data we looked at earlier:
    small samples produce noisy, misleading results."""

    grid = grid or DEFAULT_GRID

    keys = list(grid.keys())
    value_lists = [grid[k] for k in keys]
    combinations = list(itertools.product(*value_lists))

    print(f"Running sweep: {len(combinations)} parameter combinations "
          f"across {len(watchlist)} tickers, {start_date} to {end_date}")

    results = []

    for i, combo in enumerate(combinations, 1):
        params = dict(zip(keys, combo))

        result = run_backtest(
            watchlist=watchlist,
            price_data=price_data,
            spy_df=spy_df,
            vix_df=vix_df,
            start_date=start_date,
            end_date=end_date,
            params=params,
            starting_cash=starting_cash,
        )

        stats = summarize(result)

        results.append({"params": params, "stats": stats})

        print(f"  [{i}/{len(combinations)}] {params} -> "
              f"return={stats['total_return_pct']}% "
              f"trades={stats['total_trades']} "
              f"sharpe={stats['sharpe_ratio']}")

    return results


def save_results_csv(results: list, path: str):
    """Flat CSV - one row per combination, params + stats as columns.
    Easiest format to pull into a spreadsheet or a plotting tool for the
    actual heat map visualization."""

    if not results:
        return

    param_keys = list(results[0]["params"].keys())
    stat_keys = list(results[0]["stats"].keys())

    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(param_keys + stat_keys)

        for row in results:
            writer.writerow(
                [row["params"][k] for k in param_keys]
                + [row["stats"][k] for k in stat_keys]
            )

    print(f"Saved {len(results)} sweep results to {path}")
