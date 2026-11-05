"""Valuation-history and earnings-outlook tools for the Fundamentals Analyst (fork-only).

Kept out of upstream's ``agents/tools.py``: the analyst adds ``VALUATION_TOOLS`` to
its own ``TOOLS`` tuple with one tagged line, so ``fund_tools.with_symbol`` builds
their symbol-selectable twins the same way it does for upstream's tools.
"""

from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from tradingagents.dataflows.date_window import as_of
from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.router import no_data_available, route_to_vendor, vendor_unavailable
from tradingagents.dataflows.vendors.yahoo.valuation import build_valuation_history


@tool
def get_valuation_history(
    symbol: Annotated[str, InjectedState("company_of_interest")],
    curr_date: Annotated[str, "the current trading date, YYYY-mm-dd"],
    lookback_years: Annotated[int, "how many years of reported history to use"] = 10,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """Trailing P/E percentile vs. the instrument's own history, plus the equity risk premium.

    Reconstructs a historical trailing-twelve-month P/E series from reported
    EPS and historical close prices, so today's multiple can be read as cheap,
    expensive, or mid-range relative to the instrument's own history, not just
    its level today. Not applicable to an ETF/index proxy ticker, which has no
    EPS to build a valuation history from.
    """
    # An exception out of a tool would end the run.
    try:
        return build_valuation_history(symbol, as_of(curr_date, trade_date), lookback_years)
    except VendorUnavailableError as exc:
        return vendor_unavailable("get_valuation_history", exc)
    except NoMarketDataError as exc:
        return no_data_available(exc)


@tool
def get_earnings_outlook(
    ticker: Annotated[str, InjectedState("company_of_interest")],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve forward earnings estimates, estimate-revision breadth, the analyst
    price target, and the upcoming earnings date for the instrument under
    analysis. Uses the configured earnings_outlook vendor. Not available for
    an ETF/index proxy ticker, which has no earnings coverage.
    Args:
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report of forward earnings estimates and revisions
    """
    return route_to_vendor("get_earnings_outlook", ticker, as_of(curr_date, trade_date))


VALUATION_TOOLS = (get_valuation_history, get_earnings_outlook)
