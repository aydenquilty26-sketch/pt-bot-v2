"""
Loads all settings from .env into one place. Nothing else in the project
reads environment variables directly - they all import from here.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _get_bool_mode():
    mode = os.getenv("MODE", "paper").strip().lower()
    if mode not in ("paper", "live"):
        raise ValueError(f"MODE must be 'paper' or 'live', got '{mode}'")
    return mode


MODE = _get_bool_mode()
IS_PAPER = MODE == "paper"

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

# Free tier: 60 calls/minute at finnhub.io, used only for news headlines,
# never for trading or pricing.
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

WATCHLIST = [t.strip().upper() for t in os.getenv("WATCHLIST", "AAPL").split(",") if t.strip()]

MAX_POSITION_PCT = float(os.getenv("MAX_POSITION_PCT", "0.05"))
MAX_TOTAL_EXPOSURE_PCT = float(os.getenv("MAX_TOTAL_EXPOSURE_PCT", "0.80"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0.03"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "0.06"))
DRAWDOWN_HALT_PCT = float(os.getenv("DRAWDOWN_HALT_PCT", "0.08"))
TRADE_SCORE_THRESHOLD = float(os.getenv("TRADE_SCORE_THRESHOLD", "0.25"))

# Separate database file per mode so paper and live results are never mixed,
# even though it's the same code running both.
DB_PATH = f"{MODE}_trades.db"

# Compliance agent writes this file to force a halt. Delete it to resume.
HALT_FILE = "HALT"

# Tracks portfolio peak equity for the drawdown circuit breaker.
PEAK_EQUITY_FILE = f"{MODE}_peak_equity.txt"

# --------------------
# Backtesting only - none of this affects live/paper trading
# --------------------

# Larger, sector-diversified list used only for backtest sample size -
# separate from the live WATCHLIST above on purpose. All large-cap,
# liquid names with long clean price history.
BACKTEST_WATCHLIST = [
    # Technology
    "AAPL", "MSFT", "NVDA", "AVGO", "CRM",
    # Communication Services
    "GOOGL", "META", "NFLX", "DIS",
    # Consumer Discretionary
    "AMZN", "TSLA", "HD", "NKE",
    # Consumer Staples
    "PG", "KO", "WMT", "COST",
    # Financials
    "JPM", "BAC", "GS", "V",
    # Healthcare
    "UNH", "JNJ", "PFE", "ABBV",
    # Industrials
    "BA", "CAT", "HON", "UPS",
    # Energy
    "XOM", "CVX",
    # Utilities
    "NEE", "DUK",
    # Materials
    "LIN", "FCX",
]

BACKTEST_YEARS = int(os.getenv("BACKTEST_YEARS", "5"))
WALK_FORWARD_TRAIN_MONTHS = int(os.getenv("WALK_FORWARD_TRAIN_MONTHS", "12"))
WALK_FORWARD_TEST_MONTHS = int(os.getenv("WALK_FORWARD_TEST_MONTHS", "3"))
