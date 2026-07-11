"""
News/sentiment signal agent.

Input: recent headlines for a ticker, pulled from Finnhub's free
company-news endpoint (60 calls/minute on the free tier - plenty for a
watchlist this size checked every 30 minutes).

Finnhub's own sentiment scoring is a premium feature, so instead the
headlines are scored locally with VADER, a lexicon-based sentiment
analyzer built for short text like headlines and social posts. This
costs nothing per call and doesn't add to the API rate limit beyond the
headline fetch itself.

Output: score from -1 (very negative coverage) to +1 (very positive
coverage) + confidence.
"""
from datetime import datetime, timedelta

import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

import config

_analyzer = SentimentIntensityAnalyzer()

LOOKBACK_DAYS = 5
MAX_HEADLINES_SCORED = 20
# Confidence maxes out once we've seen this many headlines - a busier
# news day than that shouldn't count for any more certainty.
HEADLINES_FOR_FULL_CONFIDENCE = 6
MAX_CONFIDENCE = 0.75


def get_news_signal(ticker: str) -> dict:

    if not config.FINNHUB_API_KEY:
        return {
            "agent": "news", "ticker": ticker, "score": 0.0,
            "confidence": 0.0, "rationale": "no Finnhub API key configured",
        }

    today = datetime.utcnow().date()
    since = today - timedelta(days=LOOKBACK_DAYS)

    try:
        resp = requests.get(
            "https://finnhub.io/api/v1/company-news",
            params={
                "symbol": ticker,
                "from": since.isoformat(),
                "to": today.isoformat(),
                "token": config.FINNHUB_API_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        articles = resp.json()
    except Exception as e:
        return {
            "agent": "news", "ticker": ticker, "score": 0.0,
            "confidence": 0.0, "rationale": f"news fetch failed: {e}",
        }

    if not isinstance(articles, list) or not articles:
        return {
            "agent": "news", "ticker": ticker, "score": 0.0,
            "confidence": 0.0, "rationale": "no recent news found",
        }

    headlines = [
        a.get("headline", "")
        for a in articles[:MAX_HEADLINES_SCORED]
        if a.get("headline")
    ]

    if not headlines:
        return {
            "agent": "news", "ticker": ticker, "score": 0.0,
            "confidence": 0.0, "rationale": "no usable headlines",
        }

    compound_scores = [
        _analyzer.polarity_scores(h)["compound"]
        for h in headlines
    ]

    avg_score = sum(compound_scores) / len(compound_scores)
    score = max(-1.0, min(1.0, avg_score))

    confidence = min(1.0, len(headlines) / HEADLINES_FOR_FULL_CONFIDENCE) * MAX_CONFIDENCE

    if score > 0.15:
        tone = "net positive coverage"
    elif score < -0.15:
        tone = "net negative coverage"
    else:
        tone = "neutral/mixed coverage"

    return {
        "agent": "news",
        "ticker": ticker,
        "score": round(score, 3),
        "confidence": round(confidence, 2),
        "rationale": f"{tone} ({len(headlines)} headlines, {LOOKBACK_DAYS}d)",
    }
