# pt-bot-v2 Backtest Engine — Spec

**Status: Stage 1 (parameter sweep + heat map) built and smoke-tested.
Stages 2-6 (Monte Carlo, cluster analysis, walk-forward, deflated Sharpe)
not yet built.**

## Confirmed decisions

- **Historical range:** last 5 years (`config.BACKTEST_YEARS = 5`).
- **Watchlist:** expanded 35-ticker `config.BACKTEST_WATCHLIST`, separate
  from the live `WATCHLIST` — sector-diversified across all 10 GICS
  sectors (5x Technology, 4 each Communication Services/Consumer
  Discretionary/Consumer Staples/Financials/Healthcare/Industrials, 2 each
  Energy/Utilities/Materials).
- **Walk-forward windows:** 12-month train / 3-month test (not yet
  implemented — stage 5).
- **Fundamental/news exclusion:** implemented via `confidence=0.0` on
  those two signals inside the backtest engine — `strategy.py`'s existing
  weighting loop already skips any signal with zero effective weight, so
  no monkeypatching of `AGENT_WEIGHTS` was needed. Cleaner than the
  originally proposed approach. Live trading is completely unaffected;
  this only happens inside `backtest/engine.py`.

## Goal

Validate strategy.py + risk.py logic against years of historical data before
trusting any threshold, weight, or sizing parameter with real capital. This
is the single highest-leverage piece of work remaining on the roadmap —
everything else (learning loop, live trading, LLM reporting) depends on
knowing whether the underlying strategy has a real edge or not.

## Scope: what actually gets validated

This is the part the original six-stage plan didn't address, and it has to
be decided before anything else, because it changes what the results mean.

**Backtestable now, with free data:**
- Technical signal (`signals/technical.py`) — pure price math (RSI, MACD,
  SMA), fully reconstructable from historical OHLCV via yfinance.
- Market regime (`signals/market_regime.py`) — SPY trend + VIX, both have
  long free daily history.

**NOT backtestable with free data, and the plan needs to say so honestly:**
- Fundamental signal (`signals/fundamental.py`) — pulls a live snapshot
  (trailingPE, etc.). There's no free source for what a stock's
  fundamentals looked like on a specific past date. Applying today's
  fundamentals to 2022 price data is lookahead bias, not validation.
- News signal (`signals/news.py`) — Finnhub's free tier doesn't have years
  of historical headlines. Can't be meaningfully backtested beyond a
  recent window, if at all.

**Decision:** during backtesting, `AGENT_WEIGHTS` for `fundamental` and
`news` are forced to 0 in the backtest harness only — live weights are
untouched. This keeps `strategy.py` itself unforked (no `if backtesting:`
branches inside the real strategy logic — the harness controls this from
the outside by passing different weights in). Every backtest result gets
labeled: **"Validated: technical + market regime only. Fundamental and
news are live-only, unvalidated components."** This label goes wherever
backtest results are shown — no exceptions, no fine print.

## The six-stage pipeline

Adopting the proposed order as-is — it's sound and the gating logic (each
stage must pass before the next runs) is the right structure:

1. **Parameter sweep → heat map.** Grid over each parameter, look for a
   broad plateau of good performance rather than an isolated spike.
2. **Monte Carlo on every parameter set from the sweep** (not just the
   winner) — shuffle trade order / bootstrap returns, see how much of each
   set's performance survives resampling.
3. **Cluster analysis** — group parameter sets by proximity + performance
   to find a *family* of good settings, not a lone winner. Functionally
   this is the N-dimensional generalization of stage 1's plateau check —
   useful specifically once more than 2 parameters are being swept at once
   and a 2D heat map can't show the whole space.
4. **In-sample / out-of-sample split** — fit on one period, test on a
   period never touched during tuning.
5. **Walk-forward validation** — roll the train/test window forward
   repeatedly through history. Closest simulation to actual live behavior.
6. **Deflated Sharpe ratio** — correct the winning Sharpe for the
   multiple-comparisons problem (testing thousands of combinations makes
   some look good by chance alone).

**Implementation note on stage 6 specifically:** the deflated Sharpe
formula needs the *actual number of independent trials* as an input. This
has to be tracked as explicit state on the sweep results object — the
count of parameter combinations tested in stage 1, not anything from stage
2's Monte Carlo resamples (those are noise-testing a single trial, not
additional trials, and must not be counted as such or the deflation
math will be conceptually wrong).

## Guardrails (always-on, independent of backtest results)

Confirming and formalizing rather than changing anything:
- Hard position cap — already enforced in `risk.py` at the bot level
  (`MAX_POSITION_PCT`), not just a strategy suggestion. Confirmed correct.
- Stop-loss independent of strategy signal logic — already true today,
  structurally: stop-loss/take-profit live in Alpaca's server-side bracket
  orders, so they fire even if the strategy agent is silent, erroring, or
  the bot isn't running at all. This is a real existing strength, worth
  stating explicitly since it's easy to take for granted.
- Grade against SPY benchmark, not absolute return — already computed in
  `export_dashboard.py`'s market context. Formalizing it as the primary
  backtest scorecard metric (alpha vs. just riding market beta) rather
  than a secondary dashboard number.
- Logged thesis per trade (signals fired, confidence, why) — already true
  for live trades via `db.log_cycle`. Extending the same requirement to
  every trade the backtest engine evaluates, not just live ones.

## Compute scope — sizing this before writing loops

Current tunable parameters: `TRADE_SCORE_THRESHOLD`, `STOP_LOSS_PCT`,
`TAKE_PROFIT_PCT`, `MAX_POSITION_PCT`, `MAX_TOTAL_EXPOSURE_PCT`, plus the
technical/regime weight split. A naive full-resolution grid across all of
these is tens of thousands of combinations, each needing hundreds of Monte
Carlo resamples on top — computationally serious, not a "run it and wait a
minute" job.

**Proposed approach:**
- First pass: sweep only the 3 highest-impact params (`TRADE_SCORE_THRESHOLD`,
  `STOP_LOSS_PCT`, `TAKE_PROFIT_PCT`), hold the rest fixed at current values.
- Coarse grid first (5-6 widely-spaced values per param), find the
  promising region, then a fine grid only within that region — not one
  giant uniform grid from the start.
- Monte Carlo resamples: start at ~200 per set while developing/debugging
  the pipeline itself, scale to 500-1,000 for the final validated run.
- Cache historical OHLCV locally (watchlist + SPY + VIX) once per backtest
  session rather than re-fetching from yfinance per parameter combination —
  this is the actual bottleneck risk, not the statistics.

## Build notes (decisions made while implementing stage 1)

- **`signals/technical.py` and `signals/market_regime.py` were refactored**
  to accept an optional pre-fetched history (`hist=`, `spy_hist=`/`vix_hist=`)
  instead of always live-fetching. Live trading is unaffected — both
  default to `None`, which triggers the exact same live yfinance call as
  before. This is what lets the backtest engine call the *actual* live
  signal-scoring code against historical slices, not a reimplementation.
- **Performance fix applied during build, not after:** the engine slices
  each ticker to a 90-day trailing window per day, not the full
  history-to-date. Without this, each day's slice would grow for the
  entire backtest length, making the whole run scale O(n²) instead of
  O(n) per ticker — the difference between a sweep finishing in a
  reasonable time and one that doesn't finish practically at all.
- **Smoke-tested against synthetic random-walk data** (no live network
  access available in the build environment). Results: small losses
  across all parameter combinations tested — the correct outcome, since a
  real strategy shouldn't find an edge in literally random data. A
  suspiciously *good* result on random data would have indicated a
  lookahead bias bug; this is the useful negative-control test for that.
  Also confirmed: config values are correctly restored after each sweep
  combination (no state leakage between runs), and a sample simulated
  trade exited at exactly the configured stop-loss percentage.

## Not yet built

Stages 2-6 (Monte Carlo resampling, cluster analysis, in/out-of-sample
split, walk-forward validation, deflated Sharpe ratio) and the report.py
summary layer. Stage 1 needs to actually run against real historical data
first — this requires network access this build environment doesn't have,
so that first real run happens on your machine or in GitHub Actions.

## Module structure — actual, as built

```
backtest/
  __init__.py
  data.py                  # [BUILT] fetch + locally cache historical OHLCV
  simulated_portfolio.py   # [BUILT] renamed from the original
                           # simulated_broker.py concept - see note below
  engine.py                # [BUILT] single-run backtest loop: replays
                           # signals -> strategy.build_proposal ->
                           # risk.validate_proposal -> simulated execution
  stats.py                 # [BUILT, basic version] total return, win rate,
                           # profit factor, max drawdown, simple Sharpe -
                           # enough to rank stage 1 results. Full deflated
                           # Sharpe (stage 6) is a separate future addition.
  sweep.py                 # [BUILT] stage 1 - coarse grid, CSV output
  run_sweep.py             # [BUILT] entry point - python -m backtest.run_sweep
  monte_carlo.py           # [NOT BUILT] stage 2
  cluster.py               # [NOT BUILT] stage 3
  validation.py            # [NOT BUILT] stages 4-5
  report.py                # [NOT BUILT] readable summary layer
  cache/                   # gitignored - local OHLCV cache, regenerated locally
  results/                 # gitignored - sweep CSV output
```

**Naming note:** the original plan called this `simulated_broker.py`, as
if it would mimic Alpaca's client API surface. In practice that would
have been dishonest scaffolding — `execution.py`'s real bracket-order
construction doesn't apply to historical replay, so pretending to mimic
Alpaca's exact interface would just be extra code that doesn't do
anything real. `simulated_portfolio.py` instead replicates the *outcome*
those bracket orders produce (same share-count formula, same stop/target
formula, checked every day regardless of whether the strategy agent said
anything) without pretending to be an Alpaca client. `engine.py` still
calls the real `strategy.py`/`risk.py` functions directly and unmodified
— that part of the original plan held exactly as specified.

## Open questions — resolved

All four are answered in "Confirmed decisions" at the top of this doc.

## Next step

Stage 1 code is built and smoke-tested against synthetic data. What's
actually next:

1. **Run `python -m backtest.run_sweep` for real**, somewhere with network
   access (not this build environment) — first real run against 5 years
   of actual price data across the 35-ticker watchlist. This needs to
   happen before anything else, since stage 1's results determine what
   region of parameter space stage 2 (Monte Carlo) even needs to look at.
2. **Review the resulting CSV for a plateau vs. an isolated spike** before
   trusting any single row, per the original methodology.
3. Then stage 2 (Monte Carlo resampling on every sweep result) gets built
   on top of a foundation that's actually been proven to run correctly
   against real data, not just synthetic test data.
