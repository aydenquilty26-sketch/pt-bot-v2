"""
Keeps a permanent record of completed trades.

A trade is only logged once it has been fully closed. This allows the
dashboard to calculate real performance statistics such as win rate,
average winner, average loser, profit factor and realized P/L.
"""

import sqlite3
from datetime import datetime, timezone
import config


def get_conn():
    return sqlite3.connect(config.DB_PATH)


def log_completed_trade(
    ticker: str,
    side: str,
    qty: float,
    entry_price: float,
    exit_price: float,
):
    pnl = (exit_price - entry_price) * qty

    conn = get_conn()

    conn.execute(
        """
        INSERT INTO trade_history (
            timestamp,
            ticker,
            side,
            qty,
            entry_price,
            exit_price,
            pnl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            ticker,
            side,
            qty,
            entry_price,
            exit_price,
            pnl,
        ),
    )

    conn.commit()
    conn.close()


def get_trade_statistics():

    conn = get_conn()

    rows = conn.execute(
        """
        SELECT pnl
        FROM trade_history
        """
    ).fetchall()

    conn.close()

    if not rows:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "profit_factor": 0,
            "average_win": 0,
            "average_loss": 0,
            "realized_pnl": 0,
        }

    pnls = [r[0] for r in rows]

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    total_profit = sum(wins)
    total_loss = abs(sum(losses))

    return {
        "total_trades": len(pnls),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(pnls)) * 100,
        "profit_factor": (
            total_profit / total_loss
            if total_loss > 0
            else 0
        ),
        "average_win": (
            total_profit / len(wins)
            if wins
            else 0
        ),
        "average_loss": (
            abs(sum(losses)) / len(losses)
            if losses
            else 0
        ),
        "realized_pnl": sum(pnls),
    }
