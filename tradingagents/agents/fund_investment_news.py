"""Investment News Analysis AI report for fund runs (fork-specific).

The Fund Analyst fetches the latest daily news report published on or before
the run's trade date and stores the rendered block on
``state["investment_news_analysis_ai_report"]``. Only the investment debate
(Bull, Bear and the Research Manager) reads it, through
``get_investment_news_instruction``; the analysts never see it, since they
gather their own data.

Reports are dated, so a historical run reads the report of its own date (or
the last weekday before it) and never one written after it.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any

from tradingagents.dataflows.vendors.investment_news import (
    InvestmentNewsUnavailableError,
    fetch_news_report,
    report_url,
)

logger = logging.getLogger(__name__)

# A report is ~25k characters; anything far beyond that is not a normal
# report and would crowd the debate prompts.
_MAX_REPORT_CHARS = 60_000


def _candidate_dates(trade_date: str, lookback_days: int) -> list[str]:
    """``trade_date`` and the days before it, newest first, skipping weekends."""
    end = min(datetime.strptime(trade_date, "%Y-%m-%d").date(), date.today())
    days = (end - timedelta(days=offset) for offset in range(lookback_days + 1))
    return [d.isoformat() for d in days if d.weekday() < 5]


def find_latest_report(
    base_url: str, trade_date: str, lookback_days: int
) -> tuple[str, str] | None:
    """Return ``(report_date, markdown)`` for the newest report on or before ``trade_date``.

    Looks back ``lookback_days`` calendar days to cover weekends, holidays,
    and a report not yet published today. None when none of them has one;
    ``InvestmentNewsUnavailableError`` propagates when the site cannot answer.
    """
    for report_date in _candidate_dates(trade_date, lookback_days):
        text = fetch_news_report(base_url, report_date)
        if text is not None:
            return report_date, text
    return None


def render_news_block(report_date: str, trade_date: str, markdown: str) -> str:
    """Wrap a report in the instructions the debate agents read it with."""
    if len(markdown) > _MAX_REPORT_CHARS:
        markdown = markdown[:_MAX_REPORT_CHARS] + "\n\n[... report truncated ...]"
    dated = (
        f"dated {report_date}"
        if report_date == trade_date
        else f"dated {report_date}, the latest published on or before {trade_date}"
    )
    return "\n".join(
        [
            f"**INVESTMENT NEWS ANALYSIS AI REPORT ({dated}):**",
            "An AI-generated daily digest of market and macro news across regions and"
            " asset classes. It is not about this fund specifically: use it as the"
            " broader news backdrop for the proxy tickers and the fund's sectors and"
            " regions. Treat its claims as secondary to the analyst reports' verified"
            " data, and say explicitly where it strengthens or weakens your argument.",
            "",
            "<investment_news_report>",
            markdown,
            "</investment_news_report>",
        ]
    )


def news_unavailable_note(reason: str) -> str:
    """One-line note recorded in the Fund Analyst's report when no news report was used."""
    return f"**Investment News Analysis AI report**: unavailable for this run ({reason})."


def news_source_note(base_url: str, report_date: str) -> str:
    """One-line note naming the report used, for the Fund Analyst's report."""
    return (
        f"**Investment News Analysis AI report**: {report_date}"
        f" ({report_url(base_url, report_date)}), passed to the investment debate."
    )


def fetch_investment_news(
    base_url: str | None, trade_date: str | None, lookback_days: int
) -> tuple[str, str]:
    """Return ``(investment_news_analysis_ai_report, fund_report_section)`` for this run.

    The first is the block the debate agents read; it is empty whenever no
    report was used. The second records what happened, for the saved report.
    """
    if not base_url:
        return "", ""
    if not trade_date:
        return "", news_unavailable_note("the run has no trade date")
    try:
        found = find_latest_report(base_url, trade_date, lookback_days)
    except InvestmentNewsUnavailableError as exc:
        logger.warning("Fund Analyst: investment news report unavailable: %s", exc)
        return "", news_unavailable_note(str(exc))
    if found is None:
        return "", news_unavailable_note(
            f"no report published in the {lookback_days} days up to {trade_date}"
        )
    report_date, markdown = found
    return render_news_block(report_date, trade_date, markdown), news_source_note(
        base_url, report_date
    )


def get_investment_news_instruction(state: Mapping[str, Any] | None) -> str:
    """Return the news report block for a debate prompt, or ``""``.

    Empty for non-fund runs and states the Fund Analyst has not populated,
    so it is safe to append unconditionally.
    """
    report = (state or {}).get("investment_news_analysis_ai_report")
    if not isinstance(report, str) or not report.strip():
        return ""
    return f"\n\n{report}"
