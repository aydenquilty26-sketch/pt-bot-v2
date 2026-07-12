"""
Basic performance stats for a single backtest run. This is intentionally
minimal for stage 1 (parameter sweep + heat map) - full Monte Carlo,
cluster analysis, walk-forward, and deflated Sharpe are separate stages
built on top of this, once the engine itself is proven correct.
"""

import math


def summarize(result: dict) -> dict:

    trades = result["trades"]
    equity_curve = result["equity_curve"]
    starting_cash = result["starting_cash"]
    final_equity = result["final_equity"]

    total_return_pct = round(
        ((final_equity - starting_cash) / starting_cash) * 100, 2
    )

    if not trades:
        return {
            "total_trades": 0,
            "win_rate": None,
            "profit_factor": None,
            "total_return_pct": total_return_pct,
            "max_drawdown_pct": _max_drawdown(equity_curve),
            "sharpe_ratio": _sharpe(equity_curve),
        }

    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    total_profit = sum(wins)
    total_loss = abs(sum(losses))

    return {
        "total_trades": len(trades),
        "win_rate": round((len(wins) / len(trades)) * 100, 2),
        "profit_factor": round(total_profit / total_loss, 2) if total_loss > 0 else None,
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": _max_drawdown(equity_curve),
        "sharpe_ratio": _sharpe(equity_curve),
    }


def _max_drawdown(equity_curve: list):

    if len(equity_curve) < 2:
        return None

    peak = equity_curve[0]["equity"]
    max_dd = 0.0

    for point in equity_curve:
        peak = max(peak, point["equity"])
        if peak > 0:
            max_dd = max(max_dd, (peak - point["equity"]) / peak)

    return round(max_dd * 100, 2)


def _sharpe(equity_curve: list):

    if len(equity_curve) < 30:
        return None

    values = [p["equity"] for p in equity_curve]
    returns = [
        (values[i] - values[i - 1]) / values[i - 1]
        for i in range(1, len(values))
        if values[i - 1] > 0
    ]

    if len(returns) < 20:
        return None

    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
    std_r = math.sqrt(variance)

    if std_r == 0:
        return None

    # Daily returns, annualized assuming ~252 trading days.
    return round((mean_r / std_r) * math.sqrt(252), 2)
