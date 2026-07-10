"""
Fundamental signal agent.
Input: a ticker's key financial metrics (via yfinance, free, no key).
Output: score from -1 to +1 + confidence.

Note: fundamentals move slowly, so this signal changes rarely day to day -
that's expected, not a bug.
"""
import yfinance as yf


def get_fundamental_signal(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info
    except Exception as e:
        return {"agent": "fundamental", "ticker": ticker, "score": 0.0,
                "confidence": 0.0, "rationale": f"data fetch failed: {e}"}

    if not info or "trailingPE" not in info:
        return {"agent": "fundamental", "ticker": ticker, "score": 0.0,
                "confidence": 0.0, "rationale": "insufficient fundamental data"}

    score = 0.0
    reasons = []

    earnings_growth = info.get("earningsGrowth")
    if earnings_growth is not None:
        if earnings_growth > 0.10:
            score += 0.3
            reasons.append("earnings growing >10%")
        elif earnings_growth < 0:
            score -= 0.3
            reasons.append("earnings declining")

    profit_margin = info.get("profitMargins")
    if profit_margin is not None:
        if profit_margin > 0.15:
            score += 0.2
            reasons.append("healthy margins")
        elif profit_margin < 0.02:
            score -= 0.2
            reasons.append("thin margins")

    roe = info.get("returnOnEquity")
    if roe is not None:
        if roe > 0.15:
            score += 0.2
            reasons.append("strong ROE")
        elif roe < 0:
            score -= 0.2
            reasons.append("negative ROE")

    debt_to_equity = info.get("debtToEquity")
    if debt_to_equity is not None:
        if debt_to_equity > 200:
            score -= 0.2
            reasons.append("high debt load")
        elif debt_to_equity < 50:
            score += 0.1
            reasons.append("low debt load")

    forward_pe = info.get("forwardPE")
    trailing_pe = info.get("trailingPE")
    if forward_pe and trailing_pe and trailing_pe > 0:
        if forward_pe < trailing_pe:
            score += 0.1
            reasons.append("valuation improving")

    score = max(-1.0, min(1.0, score))

    # Confidence is lower than technical - fundamentals are noisier proxies
    # and yfinance data quality varies by ticker.
    confidence = 0.7 if reasons else 0.3

    return {
        "agent": "fundamental",
        "ticker": ticker,
        "score": round(score, 3),
        "confidence": confidence,
        "rationale": ", ".join(reasons) if reasons else "neutral",
    }
