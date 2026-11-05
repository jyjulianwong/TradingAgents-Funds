"""Fork-only point-in-time rules, kept out of upstream's ``date_window.py``."""

from tradingagents.dataflows.date_window import is_historical


def withhold_live_estimates(as_of_date: str | None, label: str) -> str | None:
    """Notice to serve instead of forward analyst estimates, or None to serve them.

    Consensus EPS/revenue estimates, estimate-revision counts, and the next
    earnings date all reflect today's market consensus with no historical
    vintage (unlike an actual reported EPS, which carries a real filing/report
    date) -- a past run would otherwise see today's forward-looking consensus,
    not the one that existed on ``as_of_date``.
    """
    if not is_historical(as_of_date):
        return None
    return (
        f"# Earnings Outlook for {label}\n"
        f"# Point-in-time as of: {as_of_date}\n\n"
        f"Forward earnings estimates are withheld for this date. Consensus EPS/"
        f"revenue estimates, estimate-revision counts, and the next earnings "
        f"date all reflect today's market consensus with no historical vintage, "
        f"so serving them would put post-decision information into a "
        f"{as_of_date} analysis."
    )
