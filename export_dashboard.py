"""
Reads the trade database and writes docs/data.json.
"""

import json
import math
import os
import sqlite3
from datetime import datetime

import config
from execution import get_trading_client


def _compute_trade_stats(pnls: list) -> dict:
    """Real performance stats over completed trades. Returns None for any
    metric that doesn't have enough data yet, rather than a misleading 0 -
    a bot with zero closed trades hasn't "lost" anything, it just hasn't
    traded enough to measure yet."""

    total_trades = len(pnls)

    if total_trades == 0:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": None,
            "profit_factor": None,
            "average_win": None,
            "average_loss": None,
            "average_trade": None,
            "expectancy": None,
        }

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    total_profit = sum(wins)
    total_loss = abs(sum(losses))

    win_rate = round((len(wins) / total_trades) * 100, 2)
    average_trade = round(sum(pnls) / total_trades, 2)
    average_win = round(total_profit / len(wins), 2) if wins else None
    average_loss = round(total_loss / len(losses), 2) if losses else None

    # Profit factor needs at least one loss to mean anything - undefined
    # (not infinite) with zero losing trades so far.
    profit_factor = (
        round(total_profit / total_loss, 2)
        if total_loss > 0
        else None
    )

    return {
        "total_trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "average_win": average_win,
        "average_loss": average_loss,
        "average_trade": average_trade,
        # Expectancy = average $ result per trade. Same number as
        # average_trade, kept as a separate key since it answers a
        # different question ("what do I expect the next trade to make").
        "expectancy": average_trade,
    }


def _compute_max_drawdown_pct(equity_history: list):
    """Largest peak-to-trough drop in the equity curve, as a percent.
    Needs at least two snapshots to mean anything."""

    if len(equity_history) < 2:
        return None

    peak = equity_history[0]["equity"]
    max_dd = 0.0

    for point in equity_history:
        equity = point["equity"]
        peak = max(peak, equity)
        if peak > 0:
            dd = (peak - equity) / peak
            max_dd = max(max_dd, dd)

    return round(max_dd * 100, 2)


def _compute_sharpe_ratio(equity_history: list):
    """Annualized Sharpe ratio from daily equity closes. Uses the last
    snapshot of each calendar day as that day's closing equity. Needs at
    least a handful of distinct trading days before this number means
    anything - a couple of intraday snapshots isn't a return series."""

    daily_close = {}
    for point in equity_history:
        day = point["timestamp"][:10]
        daily_close[day] = point["equity"]

    closes = [daily_close[d] for d in sorted(daily_close.keys())]

    if len(closes) < 5:
        return None

    returns = [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1] > 0
    ]

    if len(returns) < 4:
        return None

    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    std_dev = math.sqrt(variance)

    if std_dev == 0:
        return None

    sharpe = (mean_return / std_dev) * math.sqrt(252)
    return round(sharpe, 2)


def _build_plain_summary(
    positions_detail: list,
    daily_pl,
    trade_stats: dict,
    recent_cycles: list,
    watchlist_size: int,
    halted: bool,
) -> list:
    """Plain-English bullet points summarizing what the bot is doing right
    now, for anyone who doesn't want to parse a metrics table."""

    lines = []

    if halted:
        lines.append("Trading is currently halted - no new buys will be placed until this clears.")

    if positions_detail:
        tickers = ", ".join(p["ticker"] for p in positions_detail)
        lines.append(
            f"Currently holding {len(positions_detail)} "
            f"position{'s' if len(positions_detail) != 1 else ''}: {tickers}."
        )
    else:
        lines.append("No open positions right now - fully in cash.")

    if daily_pl is not None:
        direction = "up" if daily_pl >= 0 else "down"
        lines.append(f"The account is {direction} ${abs(daily_pl):,.2f} today.")

    # Look at the most recent pass over the watchlist (one row per ticker).
    recent_pass = recent_cycles[:max(watchlist_size, 1)]
    if recent_pass:
        acted = sum(1 for c in recent_pass if c["action"] != "none")
        lines.append(
            f"In its most recent check, the bot reviewed {len(recent_pass)} "
            f"stock{'s' if len(recent_pass) != 1 else ''} and found "
            f"{acted} worth acting on"
            + (" - the rest didn't meet its confidence bar, which is normal." if acted < len(recent_pass) else ".")
        )

    total_trades = trade_stats.get("total_trades") or 0
    if total_trades == 0:
        lines.append("No trades have closed yet, so win rate and profit factor aren't meaningful yet.")
    else:
        win_rate = trade_stats.get("win_rate")
        wins = trade_stats.get("wins")
        lines.append(
            f"Out of {total_trades} closed trade{'s' if total_trades != 1 else ''}, "
            f"{wins} {'was' if wins == 1 else 'were'} winners ({win_rate}% win rate)."
        )

    return lines


def export():

    broker = None
    positions_detail = []

    try:
        client = get_trading_client()
        broker = client.get_account()

        raw_positions = client.get_all_positions()
        open_positions = len(raw_positions)

        for p in raw_positions:
            positions_detail.append({
                "ticker": p.symbol,
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price) if p.current_price else None,
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc) * 100,
            })

    except Exception:
        broker = None
        open_positions = 0

    if not os.path.exists(config.DB_PATH):

        empty_stats = _compute_trade_stats([])

        data = {
            "mode": config.MODE,
            "equity_history": [],
            "recent_cycles": [],
            "recent_trades": [],
            "halted": False,
            "open_positions": open_positions,
            "positions": positions_detail,
            "daily_pl": 0,
            "trade_stats": empty_stats,
            "plain_summary": _build_plain_summary(
                positions_detail, 0, empty_stats, [], len(config.WATCHLIST), False
            ),
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
                news_score,
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

        # Full history (not just the last 100) so profit factor / win rate
        # reflect everything the bot has ever done, not a recent window.
        all_pnl_rows = conn.execute("""
            SELECT pnl FROM completed_trades
        """).fetchall()

        conn.close()

        equity_history = [dict(r) for r in reversed(equity_rows)]
        recent_cycles = [dict(r) for r in cycle_rows]
        recent_halts = [dict(r) for r in halt_rows]
        recent_trades = [dict(r) for r in trade_rows]
        all_pnls = [r["pnl"] for r in all_pnl_rows]

        starting_equity = 100000.0

        current_equity = (
            float(broker.equity)
            if broker
            else (
                equity_history[-1]["equity"]
                if equity_history
                else None
            )
        )

        cash = (
            float(broker.cash)
            if broker
            else (
                equity_history[-1]["cash"]
                if equity_history
                else 0
            )
        )

        buying_power = (
            float(broker.buying_power)
            if broker
            else cash
        )

        positions_value = (
            current_equity - cash
            if current_equity is not None
            else (
                equity_history[-1]["positions_value"]
                if equity_history
                else 0
            )
        )

        daily_pl = (
            float(broker.equity) - float(broker.last_equity)
            if broker
            else 0
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

        halted = os.path.exists(config.HALT_FILE)

        trade_stats = _compute_trade_stats(all_pnls)
        max_drawdown_pct = _compute_max_drawdown_pct(equity_history)
        sharpe_ratio = _compute_sharpe_ratio(equity_history)

        trade_stats["max_drawdown_pct"] = max_drawdown_pct
        trade_stats["sharpe_ratio"] = sharpe_ratio

        plain_summary = _build_plain_summary(
            positions_detail,
            daily_pl,
            trade_stats,
            recent_cycles,
            len(config.WATCHLIST),
            halted,
        )

        data = {
            "mode": config.MODE,

            "equity_history": equity_history,
            "recent_cycles": recent_cycles,
            "recent_trades": recent_trades,

            "halted": halted,
            "recent_halts": recent_halts,

            "starting_equity": starting_equity,
            "current_equity": current_equity,
            "portfolio_value": current_equity,

            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,

            "cash": cash,
            "positions_value": positions_value,
            "buying_power": buying_power,

            "daily_pl": daily_pl,
            "open_positions": open_positions,
            "positions": positions_detail,

            "current_decision": current_decision,

            "trade_stats": trade_stats,

            "plain_summary": plain_summary,

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
