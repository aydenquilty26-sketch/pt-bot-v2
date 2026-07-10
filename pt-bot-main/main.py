"""
Runs one full pass across the watchlist: data -> signals -> strategy ->
risk -> execution -> logging. Meant to be triggered on a schedule (cron,
GitHub Actions, etc) rather than run as a long-lived loop - each run is
one self-contained cycle.
"""
import sys
import config
import db
import compliance
import portfolio_monitor
import execution
from strategy import build_proposal
from risk import validate_proposal
from signals.technical import get_technical_signal
from signals.fundamental import get_fundamental_signal


def run_cycle():
    print(f"=== PT bot cycle start | mode={config.MODE} | watchlist={config.WATCHLIST} ===")

    halted, reason = compliance.is_halted()
    if halted:
        print(f"HALTED: {reason}. Skipping this cycle entirely.")
        return

    account = portfolio_monitor.get_account_state()
    equity = account["equity"]
    positions_by_ticker = account["positions_by_ticker"]
    total_exposure = account["positions_value"]

    print(f"Account equity: ${equity:,.2f} | cash: ${account['cash']:,.2f} "
          f"| in positions: ${total_exposure:,.2f}")

    proposals_this_cycle = 0

    for ticker in config.WATCHLIST:
        has_position = ticker in positions_by_ticker

        tech_signal = get_technical_signal(ticker)
        fund_signal = get_fundamental_signal(ticker)
        signals = [tech_signal, fund_signal]

        proposal = build_proposal(ticker, signals, has_position)

        if proposal is None:
            db.log_cycle(
                ticker=ticker,
                technical_score=tech_signal["score"],
                fundamental_score=fund_signal["score"],
                composite_score=None,
                action="none",
                risk_decision="n/a",
                risk_reason="no trade proposed",
            )
            print(f"[{ticker}] no trade (tech={tech_signal['score']}, fund={fund_signal['score']})")
            continue

        proposals_this_cycle += 1

        risk_result = validate_proposal(proposal, equity, total_exposure)

        if not risk_result["approved"]:
            db.log_cycle(
                ticker=ticker,
                technical_score=tech_signal["score"],
                fundamental_score=fund_signal["score"],
                composite_score=proposal["composite_score"],
                action=proposal["action"],
                risk_decision="rejected",
                risk_reason=risk_result["reason"],
            )
            print(f"[{ticker}] proposal REJECTED: {risk_result['reason']}")
            continue

        # Approved - hand off to execution
        if proposal["action"] == "buy":
            last_price = float(tech_signal.get("last_price", 0)) or _get_last_price(ticker)
            exec_result = execution.submit_buy(ticker, risk_result["position_size_usd"], last_price)
        else:  # sell
            qty = positions_by_ticker[ticker].qty
            exec_result = execution.submit_sell(ticker, qty)

        db.log_cycle(
            ticker=ticker,
            technical_score=tech_signal["score"],
            fundamental_score=fund_signal["score"],
            composite_score=proposal["composite_score"],
            action=proposal["action"],
            risk_decision="approved",
            risk_reason=risk_result["reason"],
            order_id=exec_result.get("order_id"),
            notes=exec_result.get("reason", ""),
        )
        status = "OK" if exec_result["success"] else "FAILED"
        print(f"[{ticker}] {proposal['action'].upper()} {status}: {exec_result['reason']}")

    anomaly, anomaly_reason = compliance.check_anomalies(proposals_this_cycle, len(config.WATCHLIST))
    if anomaly:
        print(f"COMPLIANCE HALT TRIGGERED: {anomaly_reason}")

    print("=== PT bot cycle complete ===")


def _get_last_price(ticker: str) -> float:
    import yfinance as yf
    hist = yf.Ticker(ticker).history(period="1d")
    if hist.empty:
        return 0.0
    return float(hist["Close"].iloc[-1])


if __name__ == "__main__":
    try:
        run_cycle()
    except Exception as e:
        print(f"FATAL ERROR: {e}", file=sys.stderr)
        raise
