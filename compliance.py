"""
Compliance agent. Runs before anything else each cycle. If it says halt,
no proposals are generated and no orders are placed that cycle - existing
bracket orders (stop-loss/take-profit) still work on their own since
they live on the broker's side, not in this script.
"""
import os
import config
import db


def is_halted() -> tuple[bool, str]:
    if os.path.exists(config.HALT_FILE):
        with open(config.HALT_FILE) as f:
            reason = f.read().strip() or "manual halt file present"
        return True, reason
    return False, ""


def trigger_halt(reason: str):
    with open(config.HALT_FILE, "w") as f:
        f.write(reason)
    db.log_halt(reason)


def check_anomalies(proposals_this_cycle: int, watchlist_size: int) -> tuple[bool, str]:
    """Basic anomaly guard: if the strategy agent is proposing trades on
    an unreasonably large fraction of the watchlist in one cycle, something
    is likely wrong with the signals (bad data, feedback loop bug) rather
    than a genuinely unusual market."""
    if watchlist_size == 0:
        return False, ""
    ratio = proposals_this_cycle / watchlist_size
    if ratio > 0.6 and watchlist_size >= 5:
        reason = f"{proposals_this_cycle}/{watchlist_size} tickers triggered trades in one cycle"
        trigger_halt(reason)
        return True, reason
    return False, ""
