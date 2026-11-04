# FORK(funds): earnings-outlook
"""Forward earnings estimates, revisions, and the earnings calendar, via yfinance."""

from typing import Annotated

import yfinance as yf

from tradingagents.dataflows.date_window import withhold_live_estimates
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.common import raise_for_empty, yf_retry

_PERIOD_LABELS = {"0q": "Current Qtr", "+1q": "Next Qtr", "0y": "Current Year", "+1y": "Next Year"}


def _period_label(period: str) -> str:
    return _PERIOD_LABELS.get(period, period)


def _num(value, digits=2):
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def get_earnings_outlook(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None,
) -> str:
    """Forward earnings estimates, revisions, and the upcoming earnings date from yfinance.

    Every figure here (consensus estimates, revision counts, the analyst price
    target) reflects today's market consensus with no historical vintage, so a
    past ``as_of_date`` withholds the whole report (``withhold_live_estimates``,
    mirroring ``get_fundamentals``'s ``withhold_live_profile`` guard, #1300).

    An ETF/index proxy ticker has no earnings coverage at all; each section
    says so individually rather than erroring, except when every section is
    empty, which is reported as no data for the symbol.
    """
    canonical = normalize_symbol(ticker)
    withheld = withhold_live_estimates(as_of_date, canonical)
    if withheld:
        return withheld

    t = yf.Ticker(canonical)
    sections = []
    found_any = False

    calendar = yf_retry(lambda: t.calendar) or {}
    earnings_dates = calendar.get("Earnings Date")
    if earnings_dates:
        found_any = True
        lines = [f"Next Earnings Date: {', '.join(str(d) for d in earnings_dates)}"]
        if calendar.get("Earnings Average") is not None:
            lines.append(
                f"Consensus EPS Estimate: {_num(calendar.get('Earnings Average'))} "
                f"(range {_num(calendar.get('Earnings Low'))} - {_num(calendar.get('Earnings High'))})"
            )
        if calendar.get("Revenue Average") is not None:
            lines.append(
                f"Consensus Revenue Estimate: {calendar.get('Revenue Average'):,.0f} "
                f"(range {calendar.get('Revenue Low'):,.0f} - {calendar.get('Revenue High'):,.0f})"
            )
        sections.append("## Upcoming Earnings\n" + "\n".join(lines))
    else:
        sections.append("## Upcoming Earnings\nNot provided — no scheduled earnings date found.")

    eps_trend = yf_retry(lambda: t.eps_trend)
    if eps_trend is not None and not eps_trend.empty:
        found_any = True
        lines = ["| Period | Current Est. | 7d Ago | 30d Ago | 90d Ago |", "|---|---|---|---|---|"]
        for period, row in eps_trend.iterrows():
            lines.append(
                f"| {_period_label(period)} | {_num(row.get('current'))} | "
                f"{_num(row.get('7daysAgo'))} | {_num(row.get('30daysAgo'))} | "
                f"{_num(row.get('90daysAgo'))} |"
            )
        sections.append("## EPS Estimate Trend\n" + "\n".join(lines))
    else:
        sections.append("## EPS Estimate Trend\nNot provided — no analyst coverage.")

    eps_revisions = yf_retry(lambda: t.eps_revisions)
    if eps_revisions is not None and not eps_revisions.empty:
        found_any = True
        lines = [
            "| Period | Up (7d) | Up (30d) | Down (7d) | Down (30d) |",
            "|---|---|---|---|---|",
        ]
        for period, row in eps_revisions.iterrows():
            lines.append(
                f"| {_period_label(period)} | {row.get('upLast7days', 0)} | "
                f"{row.get('upLast30days', 0)} | {row.get('downLast7Days', 0)} | "
                f"{row.get('downLast30days', 0)} |"
            )
        # Revisions breadth (how many analysts moved estimates, and which way)
        # matters more than the point estimate level: a level can hold steady
        # while the breadth underneath it is deteriorating or improving.
        sections.append("## EPS Revisions Breadth\n" + "\n".join(lines))
    else:
        sections.append("## EPS Revisions Breadth\nNot provided — no analyst coverage.")

    recommendations = yf_retry(lambda: t.recommendations)
    if recommendations is not None and not recommendations.empty:
        found_any = True
        lines = [
            "| Period | Strong Buy | Buy | Hold | Sell | Strong Sell |",
            "|---|---|---|---|---|---|",
        ]
        for _, row in recommendations.iterrows():
            lines.append(
                f"| {row.get('period')} | {row.get('strongBuy', 0)} | {row.get('buy', 0)} | "
                f"{row.get('hold', 0)} | {row.get('sell', 0)} | {row.get('strongSell', 0)} |"
            )
        sections.append(
            "## Analyst Rating Distribution (by month, 0m = current)\n" + "\n".join(lines)
        )

    info = yf_retry(lambda: t.info) or {}
    target_mean = info.get("targetMeanPrice")
    if target_mean is not None:
        found_any = True
        sections.append(
            "## Analyst Price Target\n"
            f"Mean: {target_mean} (range {info.get('targetLowPrice')} - {info.get('targetHighPrice')}, "
            f"{info.get('numberOfAnalystOpinions', 'unknown')} analysts; "
            f"consensus recommendation: {info.get('recommendationKey', 'not provided')})"
        )

    if not found_any:
        raise_for_empty(ticker, canonical, "earnings outlook data")

    return f"# Earnings Outlook for {canonical}\n\n" + "\n\n".join(sections)
