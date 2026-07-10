"""
Technical signal agent.
Input: a ticker's recent daily price history (fetched via yfinance - free,
no API key needed, used only for market data, never for trading).
Output: score from -1 (strong sell) to +1 (strong buy) + confidence.
"""
import yfinance as yf
import pandas as pd
import numpy as np


def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line


def get_technical_signal(ticker: str) -> dict:
    try:
        hist = yf.Ticker(ticker).history(period="6mo", interval="1d")
    except Exception as e:
        return {"agent": "technical", "ticker": ticker, "score": 0.0,
                "confidence": 0.0, "rationale": f"data fetch failed: {e}"}

    if hist.empty or len(hist) < 50:
        return {"agent": "technical", "ticker": ticker, "score": 0.0,
                "confidence": 0.0, "rationale": "insufficient price history"}

    close = hist["Close"]

    rsi = _rsi(close).iloc[-1]
    macd_line, signal_line = _macd(close)
    macd_bullish = macd_line.iloc[-1] > signal_line.iloc[-1]
    macd_prev_bullish = macd_line.iloc[-2] > signal_line.iloc[-2]
    macd_cross_up = macd_bullish and not macd_prev_bullish
    macd_cross_down = (not macd_bullish) and macd_prev_bullish

    sma20 = close.rolling(20).mean().iloc[-1]
    sma50 = close.rolling(50).mean().iloc[-1]
    trend_bullish = sma20 > sma50

    score = 0.0
    reasons = []

    # RSI: oversold = bullish tilt, overbought = bearish tilt
    if rsi < 30:
        score += 0.35
        reasons.append("RSI oversold")
    elif rsi > 70:
        score -= 0.35
        reasons.append("RSI overbought")

    # MACD crossover carries more weight than raw position
    if macd_cross_up:
        score += 0.4
        reasons.append("MACD bullish cross")
    elif macd_cross_down:
        score -= 0.4
        reasons.append("MACD bearish cross")
    elif macd_bullish:
        score += 0.15
    else:
        score -= 0.15

    # Trend filter
    if trend_bullish:
        score += 0.25
        reasons.append("SMA20 > SMA50")
    else:
        score -= 0.25
        reasons.append("SMA20 < SMA50")

    score = max(-1.0, min(1.0, score))

    return {
        "agent": "technical",
        "ticker": ticker,
        "score": round(score, 3),
        "confidence": 0.9,
        "rationale": ", ".join(reasons) if reasons else "neutral",
        "last_price": float(close.iloc[-1]),
    }
