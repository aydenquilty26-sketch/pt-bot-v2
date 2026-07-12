"""
Market regime agent - not a per-ticker signal like technical/fundamental/
news. This is shared market-wide context, computed once per cycle and
applied uniformly to every ticker's risk sizing and buy threshold for
that run.

Two free inputs via yfinance:
- SPY trend (SMA20 vs SMA50 - same method the technical agent uses
  per-stock, applied to the whole market instead of one ticker).
- VIX level - how much fear is currently priced in, independent of
  direction.

What it produces feeds two places downstream:
- risk_multiplier: scales position size in risk.py. Cut hard in bad
  conditions, boosted only modestly in good ones - the bot should be
  slower to get more aggressive than it is to get defensive.
- threshold_adjustment: added to the buy-side score threshold in
  strategy.py only. Sells are never made harder by market conditions -
  staying able to exit is a defensive property that should never get
  tightened when things look shaky.

A data hiccup here should never block trading entirely - on any failure
this falls back to "no adjustment" (multiplier 1.0, threshold +0) rather
than halting the cycle.

spy_hist/vix_hist are optional - pass pre-fetched historical DataFrames
(from the backtest engine, sliced up to a past date) to score against
those instead of live-fetching. Live trading calls this with both None,
same behavior as before.
"""

MIN_MULTIPLIER = 0.25
MAX_MULTIPLIER = 1.25


def get_market_regime(spy_hist=None, vix_hist=None) -> dict:

    try:
        if spy_hist is None or vix_hist is None:
            import yfinance as yf

            if spy_hist is None:
                spy_hist = yf.Ticker("SPY").history(period="6mo", interval="1d")
            if vix_hist is None:
                vix_hist = yf.Ticker("^VIX").history(period="5d", interval="1d")

        trend = None

        if not spy_hist.empty and len(spy_hist) >= 50:
            close = spy_hist["Close"]
            sma20 = close.rolling(20).mean().iloc[-1]
            sma50 = close.rolling(50).mean().iloc[-1]

            if abs(sma20 - sma50) / sma50 < 0.003:
                trend = "neutral"
            else:
                trend = "bullish" if sma20 > sma50 else "bearish"

        vix = None

        if not vix_hist.empty:
            vix = float(vix_hist["Close"].iloc[-1])

        vix_tier = _classify_vix(vix)

        risk_multiplier, threshold_adjustment, rationale = _compute_adjustments(
            trend, vix_tier
        )

        return {
            "trend": trend,
            "vix": round(vix, 2) if vix is not None else None,
            "vix_tier": vix_tier,
            "risk_multiplier": risk_multiplier,
            "threshold_adjustment": threshold_adjustment,
            "rationale": rationale,
        }

    except Exception as e:
        return {
            "trend": None,
            "vix": None,
            "vix_tier": None,
            "risk_multiplier": 1.0,
            "threshold_adjustment": 0.0,
            "rationale": f"market data unavailable, using defaults: {e}",
        }


def _classify_vix(vix):

    if vix is None:
        return None
    if vix < 15:
        return "calm"
    if vix < 25:
        return "normal"
    if vix < 35:
        return "elevated"
    return "extreme"


def _compute_adjustments(trend, vix_tier):

    multiplier = 1.0
    threshold_adj = 0.0
    reasons = []

    if trend == "bearish":
        multiplier *= 0.6
        threshold_adj += 0.10
        reasons.append("bearish SPY trend: sizing cut, buy bar raised")
    elif trend == "bullish" and vix_tier == "calm":
        multiplier *= 1.15
        reasons.append("bullish trend + calm VIX: sizing modestly increased")

    if vix_tier == "elevated":
        multiplier *= 0.75
        threshold_adj += 0.05
        reasons.append("elevated VIX: sizing cut further")
    elif vix_tier == "extreme":
        multiplier *= 0.5
        threshold_adj += 0.15
        reasons.append("extreme VIX: sizing cut heavily, buy bar raised sharply")

    multiplier = max(MIN_MULTIPLIER, min(MAX_MULTIPLIER, multiplier))
    threshold_adj = round(threshold_adj, 2)

    if not reasons:
        reasons.append("normal conditions: no adjustment")

    return round(multiplier, 2), threshold_adj, "; ".join(reasons)
