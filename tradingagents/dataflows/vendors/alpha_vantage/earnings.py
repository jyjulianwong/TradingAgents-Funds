# FORK(funds): earnings-outlook
"""Forward/trailing earnings outlook via Alpha Vantage, as a fallback for yfinance.

Alpha Vantage's EARNINGS endpoint carries no forward consensus-revision trend
(yfinance's richer ``eps_trend``/``eps_revisions`` surfaces that); this reports
the trailing reported-vs-estimated EPS surprise sequence instead, which is a
narrower but still genuine revisions-breadth proxy (consecutive beats/misses).
"""

import json
from typing import Annotated

from tradingagents.dataflows.date_window import withhold_live_estimates
from tradingagents.dataflows.vendors.alpha_vantage.common import _make_api_request


def get_earnings_outlook(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None,
) -> str:
    """Trailing EPS surprise trend for a ticker, from Alpha Vantage's EARNINGS endpoint.

    The next quarter's ``estimatedEPS`` and every trailing surprise figure
    reflect today's consensus/latest filing with no historical vintage, so a
    past ``as_of_date`` withholds the whole report, mirroring
    ``withhold_live_profile`` (#1300).
    """
    withheld = withhold_live_estimates(as_of_date, ticker)
    if withheld:
        return withheld

    response_text = _make_api_request("EARNINGS", {"symbol": ticker})
    try:
        payload = json.loads(response_text)
    except (TypeError, ValueError):
        return response_text

    quarterly = payload.get("quarterlyEarnings") or []
    if not quarterly:
        return (
            f"# Earnings Outlook for {ticker}\n\n"
            f"Not provided — Alpha Vantage has no earnings history for this symbol "
            f"(this is expected for an ETF/index instrument, which has no EPS)."
        )

    lines = [
        "| Report Date | Reported EPS | Estimated EPS | Surprise % |",
        "|---|---|---|---|",
    ]
    for row in quarterly[:4]:
        lines.append(
            f"| {row.get('reportedDate', 'n/a')} | {row.get('reportedEPS', 'n/a')} | "
            f"{row.get('estimatedEPS', 'n/a')} | {row.get('surprisePercentage', 'n/a')} |"
        )
    return (
        f"# Earnings Outlook for {ticker}\n\n"
        "## Trailing EPS Surprise Trend (last 4 quarters)\n"
        + "\n".join(lines)
        + "\n\nNot provided — Alpha Vantage's EARNINGS endpoint carries no forward "
        "consensus-revision trend; this reports only trailing reported-vs-estimated "
        "surprises."
    )
