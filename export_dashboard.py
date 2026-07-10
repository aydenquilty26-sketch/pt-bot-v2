"""
Reads the trade database and writes docs/data.json.
"""

import json
import os
import sqlite3

import config


def export():

    if not os.path.exists(config.DB_PATH):
        data = {
            "mode": config.MODE,
            "equity_history": [],
            "recent_cycles": [],
            "recent_trades": [],
            "halted": False,
        }

    else:

        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row

        equity_rows = conn.execute("""
            SELECT timestamp, equity, cash, positions_value
            FROM equity_snapshots
            ORDER BY id DESC
            LIMIT 500
        """).fetchall()

        cycle_rows = conn.execute("""
            SELECT
                timestamp,
                ticker,
                technical_score,
                fundamental_score,
                composite_score,
                action,
                risk_decision,
                risk_reason,
                order_id,
                notes
            FROM cycles
            ORDER BY id DESC
            LIMIT 200
        """).fetchall()

        halt_rows = conn.execute("""
            SELECT timestamp, reason
            FROM halts
            ORDER BY id DESC
            LIMIT 5
        """).fetchall()

        trade_rows = conn.execute("""
            SELECT
                ticker,
                buy_time,
                sell_time,
                buy_price,
                sell_price,
                quantity,
                pnl,
                pnl_pct,
                hold_time_hours
            FROM completed_trades
            ORDER BY id DESC
            LIMIT 100
        """).fetchall()

        conn.close()

        equity_history = [dict(r) for r in reversed(equity_rows)]
        recent_cycles = [dict(r) for r in cycle_rows]
        recent_halts = [dict(r) for r in halt_rows]
        recent_trades = [dict(r) for r in trade_rows]

        starting_equity = 100000.0

        current_equity = (
            equity_history[-1]["equity"]
            if equity_history else None
        )

        total_pnl = None
        total_pnl_pct = None

        if current_equity is not None:
            total_pnl = current_equity - starting_equity
            total_pnl_pct = (total_pnl / starting_equity) * 100

        current_decision = None

        for cycle in recent_cycles:
            if (
                cycle["action"] != "none"
                and cycle["composite_score"] is not None
            ):
                current_decision = cycle
                break

        wins = sum(1 for t in recent_trades if t["pnl"] > 0)
        losses = sum(1 for t in recent_trades if t["pnl"] <= 0)
        total_trades = len(recent_trades)

        win_rate = (
            round((wins / total_trades) * 100, 2)
            if total_trades
            else 0
        )

        average_trade = (
            round(
                sum(t["pnl"] for t in recent_trades) / total_trades,
                2,
            )
            if total_trades
            else 0
        )

        data = {
            "mode": config.MODE,

            "equity_history": equity_history,
            "recent_cycles": recent_cycles,
            "recent_trades": recent_trades,

            "halted": os.path.exists(config.HALT_FILE),
            "recent_halts": recent_halts,

            "starting_equity": starting_equity,
            "current_equity": current_equity,
            "portfolio_value": current_equity,

            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,

            "cash": equity_history[-1]["cash"] if equity_history else 0,
            "positions_value": equity_history[-1]["positions_value"] if equity_history else 0,
            "buying_power": equity_history[-1]["cash"] if equity_history else 0,

            "daily_pl": 0,
            "open_positions": 0,

            "current_decision": current_decision,

            "trade_stats": {
                "total_trades": total_trades,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "average_trade": average_trade,
            },

            "last_updated": (
                equity_history[-1]["timestamp"]
                if equity_history
                else None
            ),
        }

    os.makedirs("docs", exist_ok=True)

    with open("docs/data.json", "w") as f:
        json.dump(data, f, indent=2, default=str)

    print(
        f"Exported "
        f"{len(data['equity_history'])} equity snapshots, "
        f"{len(data['recent_cycles'])} cycles, "
        f"{len(data['recent_trades'])} completed trades."
    )


if __name__ == "__main__":
    export()
