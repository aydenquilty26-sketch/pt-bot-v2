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


def _compute_extended_trade_stats(trade_rows: list) -> dict:
    """Hold time and best/worst trade, computed over full trade history -
    not the same list as _compute_trade_stats' pnls, but derived from the
    same underlying rows so they always agree with each other."""

    if not trade_rows:
        return {
            "avg_hold_hours": None,
            "largest_win": None,
            "largest_loss": None,
        }

    hold_times = [
        r["hold_time_hours"]
        for r in trade_rows
        if r["hold_time_hours"] is not None
    ]

    pnls = [r["pnl"] for r in trade_rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    return {
        "avg_hold_hours": round(sum(hold_times) / len(hold_times), 1) if hold_times else None,
        "largest_win": round(max(wins), 2) if wins else None,
        "largest_loss": round(min(losses), 2) if losses else None,
    }


def _compute_rejection_reasons(conn) -> list:
    """Why has the risk gate said no, and how often. Answers 'what mistakes
    is the AI trying to make that risk management is catching.'"""

    rows = conn.execute("""
        SELECT risk_reason, COUNT(*) as cnt
        FROM cycles
        WHERE risk_decision = 'rejected'
        GROUP BY risk_reason
        ORDER BY cnt DESC
        LIMIT 8
    """).fetchall()

    return [{"reason": r["risk_reason"], "count": r["cnt"]} for r in rows]


def _compute_confidence_distribution(conn) -> dict:
    """Buckets every proposed trade (not just executed ones) by how
    confident the composite score was. Since TRADE_SCORE_THRESHOLD gates
    proposals at 0.40, the buckets split the 0.40-1.0 range into thirds
    rather than starting from zero."""

    rows = conn.execute("""
        SELECT composite_score
        FROM cycles
        WHERE composite_score IS NOT NULL
    """).fetchall()

    low = medium = high = 0

    for r in rows:
        score = abs(r["composite_score"])
        if score < 0.55:
            low += 1
        elif score < 0.70:
            medium += 1
        else:
            high += 1

    return {"low": low, "medium": medium, "high": high}


def _get_watchlist_snapshot(conn) -> list:
    """The latest reading on every ticker currently being watched, not
    just the one that most recently triggered a trade - answers 'what is
    the bot seeing across the whole list right now.'"""

    rows = conn.execute("""
        SELECT c.ticker, c.technical_score, c.fundamental_score,
               c.news_score, c.composite_score, c.action, c.timestamp
        FROM cycles c
        INNER JOIN (
            SELECT ticker, MAX(id) as max_id
            FROM cycles
            GROUP BY ticker
        ) latest ON c.ticker = latest.ticker AND c.id = latest.max_id
    """).fetchall()

    by_ticker = {r["ticker"]: dict(r) for r in rows}

    # Ordered to match the configured watchlist, and limited to tickers
    # still actually on it - old rows from a ticker that's since been
    # removed shouldn't linger in this view.
    return [
        by_ticker[t]
        for t in config.WATCHLIST
        if t in by_ticker
    ]


def _get_market_context(equity_history: list) -> dict:
    """SPY trend (bullish/bearish/neutral, same logic as the technical
    agent uses per-stock) and how the account's return compares to just
    holding SPY over the same window. One extra data fetch per run - not
    per ticker, so it doesn't meaningfully add to API usage."""

    try:
        import yfinance as yf

        hist = yf.Ticker("SPY").history(period="6mo", interval="1d")

        if hist.empty or len(hist) < 50:
            return {"trend": None, "spy_return_pct": None}

        close = hist["Close"]
        sma20 = close.rolling(20).mean().iloc[-1]
        sma50 = close.rolling(50).mean().iloc[-1]

        if abs(sma20 - sma50) / sma50 < 0.003:
            trend = "neutral"
        else:
            trend = "bullish" if sma20 > sma50 else "bearish"

        spy_return_pct = None

        if equity_history:
            start_date = equity_history[0]["timestamp"][:10]
            close_dates = close.index.strftime("%Y-%m-%d")
            matching = close[close_dates >= start_date]

            if len(matching) >= 1:
                first_price = float(matching.iloc[0])
                last_price = float(close.iloc[-1])
                spy_return_pct = round(
                    ((last_price - first_price) / first_price) * 100, 2
                )

        return {"trend": trend, "spy_return_pct": spy_return_pct}

    except Exception:
        return {"trend": None, "spy_return_pct": None}


def _get_sector_allocation(positions_detail: list) -> list:
    """Groups open positions by sector using yfinance's company profile
    data. Only looked up for currently-held tickers, not the whole
    watchlist - keeps this to a handful of calls even as the watchlist
    grows, since it only runs against what's actually in the portfolio."""

    if not positions_detail:
        return []

    try:
        import yfinance as yf
    except Exception:
        return []

    total_value = sum(p["market_value"] for p in positions_detail)

    if total_value <= 0:
        return []

    sector_totals = {}

    for p in positions_detail:
        sector = "Unknown"
        try:
            info = yf.Ticker(p["ticker"]).info
            sector = info.get("sector") or "Unknown"
        except Exception:
            pass

        sector_totals[sector] = sector_totals.get(sector, 0) + p["market_value"]

    allocation = [
        {
            "sector": sector,
            "market_value": round(value, 2),
            "pct": round((value / total_value) * 100, 1),
        }
        for sector, value in sector_totals.items()
    ]

    allocation.sort(key=lambda x: x["pct"], reverse=True)

    return allocation


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

    sector_allocation = _get_sector_allocation(positions_detail)

    if not os.path.exists(config.DB_PATH):

        empty_stats = _compute_trade_stats([])
        empty_stats.update({
            "avg_hold_hours": None,
            "largest_win": None,
            "largest_loss": None,
        })

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
            "rejection_reasons": [],
            "confidence_distribution": {"low": 0, "medium": 0, "high": 0},
            "watchlist_snapshot": [],
            "market_context": {"trend": None, "spy_return_pct": None},
            "active_regime": None,
            "sector_allocation": sector_allocation,
            "cash_deployed_pct": None,
            "risk_reward_ratio": round(config.TAKE_PROFIT_PCT / config.STOP_LOSS_PCT, 2),
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
                notes,
                stop_price,
                take_profit_price,
                risk_amount,
                reward_amount
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

        # Full history (not just the last 100) so profit factor / win rate /
        # hold time / largest win-loss reflect everything the bot has ever
        # done, not a recent window.
        all_trades_full = conn.execute("""
            SELECT pnl, hold_time_hours FROM completed_trades
        """).fetchall()

        rejection_reasons = _compute_rejection_reasons(conn)
        confidence_distribution = _compute_confidence_distribution(conn)
        watchlist_snapshot = _get_watchlist_snapshot(conn)

        regime_row = conn.execute("""
            SELECT timestamp, trend, vix, vix_tier, risk_multiplier,
                   threshold_adjustment, rationale
            FROM market_regime_log
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

        conn.close()

        active_regime = dict(regime_row) if regime_row else None

        equity_history = [dict(r) for r in reversed(equity_rows)]
        recent_cycles = [dict(r) for r in cycle_rows]
        recent_halts = [dict(r) for r in halt_rows]
        recent_trades = [dict(r) for r in trade_rows]
        all_pnls = [r["pnl"] for r in all_trades_full]

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
        extended_stats = _compute_extended_trade_stats(all_trades_full)

        trade_stats["max_drawdown_pct"] = max_drawdown_pct
        trade_stats["sharpe_ratio"] = sharpe_ratio
        trade_stats.update(extended_stats)

        market_context = _get_market_context(equity_history)

        cash_deployed_pct = (
            round((positions_value / current_equity) * 100, 1)
            if current_equity and current_equity > 0
            else None
        )

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

            "rejection_reasons": rejection_reasons,
            "confidence_distribution": confidence_distribution,
            "watchlist_snapshot": watchlist_snapshot,
            "market_context": market_context,
            "active_regime": active_regime,
            "sector_allocation": sector_allocation,
            "cash_deployed_pct": cash_deployed_pct,
            "risk_reward_ratio": round(config.TAKE_PROFIT_PCT / config.STOP_LOSS_PCT, 2),

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
