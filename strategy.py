"""
Strategy agent.
Input: outputs from all signal agents for one ticker.
Output: a trade proposal, or None if there's not enough conviction to act.

v1 is long-only: it can propose buying or exiting an existing position,
never shorting. This keeps risk and execution logic simpler for the first
working version.
"""
import config

# Equal weighting for v1. Once the performance feedback loop is built
# (phase 2), these get adjusted automatically based on each agent's
# realized accuracy instead of being fixed here.
AGENT_WEIGHTS = {
    "technical": 0.5,
    "fundamental": 0.5,
}


def build_proposal(ticker: str, signals: list, has_position: bool) -> dict | None:
    weighted_sum = 0.0
    weight_total = 0.0
    contributing = []

    for sig in signals:
        w = AGENT_WEIGHTS.get(sig["agent"], 0.0) * sig["confidence"]
        if w <= 0:
            continue
        weighted_sum += sig["score"] * w
        weight_total += w
        if abs(sig["score"]) > 0.1:
            contributing.append(sig["agent"])

    # Not enough usable signal -> no trade. This is a deliberate no-op,
    # not a failure - insufficient information should never force a trade.
    if weight_total == 0 or len(contributing) < 1:
        return None

    composite_score = weighted_sum / weight_total

    if composite_score >= config.TRADE_SCORE_THRESHOLD and not has_position:
        action = "buy"
    elif composite_score <= -config.TRADE_SCORE_THRESHOLD and has_position:
        action = "sell"
    else:
        return None

    return {
        "ticker": ticker,
        "action": action,
        "composite_score": round(composite_score, 3),
        "contributing_agents": contributing,
    }
