"""
All logging goes through here into a local SQLite file.
"""

import sqlite3
from datetime import datetime, timezone
import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    ticker TEXT NOT NULL,
    technical_score REAL,
    fundamental_score REAL,
    composite_score REAL,
    action TEXT,
    risk_decision TEXT,
    risk_reason TEXT,
    order_id TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    equity REAL,
    cash REAL,
    positions_value REAL
);

CREATE TABLE IF NOT EXISTS halts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS completed_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    buy_time TEXT,
    sell_time TEXT,
    buy_price REAL,
    sell_price REAL,
    quantity REAL,
    pnl REAL,
    pnl_pct REAL,
    hold_time_hours REAL
);
"""


def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn):
    """Adds columns introduced after the original schema, without
    touching existing data. Safe to run on every connection - it's a
    no-op once the column already exists."""

    existing_cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(cycles)").fetchall()
    }

    new_columns = {
        "news_score": "REAL",
        "stop_price": "REAL",
        "take_profit_price": "REAL",
        "risk_amount": "REAL",
        "reward_amount": "REAL",
    }

    for col, col_type in new_columns.items():
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE cycles ADD COLUMN {col} {col_type}")

    conn.commit()


def log_cycle(
    ticker,
    technical_score,
    fundamental_score,
    composite_score,
    action,
    risk_decision,
    risk_reason,
    order_id=None,
    notes="",
    news_score=None,
    stop_price=None,
    take_profit_price=None,
    risk_amount=None,
    reward_amount=None,
):
    conn = get_conn()

    conn.execute(
        """
        INSERT INTO cycles (
            timestamp,
            ticker,
            technical_score,
            fundamental_score,
            composite_score,
            action,
            risk_decision,
            risk_reason,
            order_id,
            notes,
            news_score,
            stop_price,
            take_profit_price,
            risk_amount,
            reward_amount
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            ticker,
            technical_score,
            fundamental_score,
            composite_score,
            action,
            risk_decision,
            risk_reason,
            order_id,
            notes,
            news_score,
            stop_price,
            take_profit_price,
            risk_amount,
            reward_amount,
        ),
    )

    conn.commit()
    conn.close()


def log_equity(equity, cash, positions_value):
    conn = get_conn()

    conn.execute(
        """
        INSERT INTO equity_snapshots (
            timestamp,
            equity,
            cash,
            positions_value
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            equity,
            cash,
            positions_value,
        ),
    )

    conn.commit()
    conn.close()


def log_halt(reason):
    conn = get_conn()

    conn.execute(
        """
        INSERT INTO halts (
            timestamp,
            reason
        )
        VALUES (?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            reason,
        ),
    )

    conn.commit()
    conn.close()


def log_completed_trade(
    ticker,
    buy_time,
    sell_time,
    buy_price,
    sell_price,
    quantity,
    pnl,
    pnl_pct,
    hold_time_hours,
):
    conn = get_conn()

    conn.execute(
        """
        INSERT INTO completed_trades (
            ticker,
            buy_time,
            sell_time,
            buy_price,
            sell_price,
            quantity,
            pnl,
            pnl_pct,
            hold_time_hours
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticker,
            buy_time,
            sell_time,
            buy_price,
            sell_price,
            quantity,
            pnl,
            pnl_pct,
            hold_time_hours,
        ),
    )

    conn.commit()
    conn.close()
