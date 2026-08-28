from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def search_ticker_symbol(
    query: Annotated[str, "Ticker symbol or company name to look up"],
) -> str:
    """
    Look up a ticker symbol or company name against a live symbol database.
    Uses the configured ticker_symbol_search vendor.
    Args:
        query (str): A ticker symbol (e.g. AAPL) or company name (e.g. Apple Inc).
    Returns:
        str: A formatted table of best-matching symbols (symbol, name, type,
            region, match score), or a NO_DATA_AVAILABLE / DATA_UNAVAILABLE
            sentinel string when no vendor has data for this query.
    """
    return route_to_vendor("search_ticker_symbol", query)
