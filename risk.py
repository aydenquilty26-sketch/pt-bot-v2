"""
Risk validation agent - the gate. Every proposal from the strategy agent
passes through here before an order is ever placed. This is the one place
in the system with veto power.
"""
import os
import config


def check_drawdown_halt(current_equity: float) -> tuple[bool, str]:
    """Circuit breaker: compares current equity to the highest equity ever
    recorded. If we've dropped too far from the peak, halt new buys."""
    peak = current_equity
    if os.path.exists(config.PEAK_EQUITY_FILE):
        with open(config.PEAK_EQUITY_FILE) as f:
            try:
                peak = max(float(f.read().strip()), current_equity)
            except ValueError:
                peak = current_equity

    with open(config.PEAK_EQUITY_FILE, "w") as f:
        f.write(str(peak))

    if peak <= 0:
        return False, ""

    drawdown = (peak - current_equity) / peak
    if drawdown >= config.DRAWDOWN_HALT_PCT:
        return True, f"drawdown {drawdown:.1%} exceeds limit {config.DRAWDOWN_HALT_PCT:.1%}"
    return False, ""


def validate_proposal(
    proposal: dict,
    account_equity: float,
    total_exposure: float,
    risk_multiplier: float = 1.0,
) -> dict:
    """
    Returns {"approved": bool, "reason": str, "position_size_usd": float}

    risk_multiplier comes from the market regime agent - 1.0 in normal
    conditions, scaled down in a bearish/volatile market, scaled up only
    modestly in calm bullish conditions.
    """
    ticker = proposal["ticker"]

    if proposal["action"] == "sell":
        # Exiting a position always passes risk - reducing exposure is
        # never the dangerous direction.
        return {"approved": True, "reason": "exit approved", "position_size_usd": 0}

    # Buy path
    halted, halt_reason = check_drawdown_halt(account_equity)
    if halted:
        return {"approved": False, "reason": f"halted: {halt_reason}", "position_size_usd": 0}

    position_size_usd = account_equity * config.MAX_POSITION_PCT * risk_multiplier

    projected_exposure = (total_exposure + position_size_usd) / account_equity
    if projected_exposure > config.MAX_TOTAL_EXPOSURE_PCT:
        return {
            "approved": False,
            "reason": f"would breach max total exposure "
                      f"({projected_exposure:.1%} > {config.MAX_TOTAL_EXPOSURE_PCT:.1%})",
            "position_size_usd": 0,
        }

    if position_size_usd < 1:
        return {"approved": False, "reason": "position size too small", "position_size_usd": 0}

    return {"approved": True, "reason": "within limits", "position_size_usd": round(position_size_usd, 2)}
