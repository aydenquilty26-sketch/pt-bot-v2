"""
Historical data fetching + local caching for the backtest engine.

The actual bottleneck in a large parameter sweep isn't the math - it's
re-downloading the same years of price history from yfinance for every
one of thousands of parameter combinations. This fetches each ticker's
history exactly once per backtest session and caches it to disk, so
repeated sweep runs (and every parameter combination within one run)
reuse the same in-memory/on-disk data.
"""

import os
from datetime import datetime, timedelta

import pandas as pd

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")

_memory_cache = {}


def _cache_path(ticker: str, start: str, end: str) -> str:
    safe_ticker = ticker.replace("^", "_")
    return os.path.join(CACHE_DIR, f"{safe_ticker}_{start}_{end}.csv")


def get_history(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Daily OHLCV for one ticker between start and end (YYYY-MM-DD).
    Cached in memory for the life of the process, and on disk across
    process runs. Returns an empty DataFrame on failure rather than
    raising - callers should treat that the same as "insufficient data",
    consistent with how the live signal agents already handle bad data."""

    key = (ticker, start, end)

    if key in _memory_cache:
        return _memory_cache[key]

    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(ticker, start, end)

    if os.path.exists(path):
        try:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            _memory_cache[key] = df
            return df
        except Exception:
            pass  # fall through and re-fetch if the cache file is bad

    try:
        import yfinance as yf
        df = yf.Ticker(ticker).history(start=start, end=end, interval="1d")
    except Exception as e:
        print(f"Backtest data fetch failed for {ticker}: {e}")
        df = pd.DataFrame()

    if not df.empty:
        try:
            df.to_csv(path)
        except Exception:
            pass  # caching is an optimization, not a requirement

    _memory_cache[key] = df
    return df


def get_backtest_date_range(years: int) -> tuple:
    """Returns (start, end) as YYYY-MM-DD strings covering the requested
    number of years up to today."""

    end = datetime.utcnow().date()
    start = end - timedelta(days=365 * years + 30)  # small buffer for warmup
    return start.isoformat(), end.isoformat()


def load_all(tickers: list, start: str, end: str) -> dict:
    """Fetches history for every ticker up front, once. Returns
    {ticker: DataFrame}. Tickers that fail to fetch are silently omitted -
    the engine treats a missing ticker the same as one with no signal."""

    data = {}

    for ticker in tickers:
        df = get_history(ticker, start, end)
        if not df.empty and len(df) >= 60:
            data[ticker] = df
        else:
            print(f"Skipping {ticker} - insufficient historical data")

    return data
