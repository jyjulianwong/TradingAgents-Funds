from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_fund_fact_sheet(
    isin: Annotated[str, "ISIN of the fund to look up"],
) -> str:
    """
    Retrieve a fund's holdings fact sheet (top holdings by weight) for a given ISIN.
    Uses the configured fund_fact_sheet_data vendor.
    Args:
        isin (str): ISIN of the fund, e.g. IE00B4L5Y983
    Returns:
        str: A formatted table of the fund's largest holdings (ticker, security name, weight),
            or a NO_DATA_AVAILABLE / DATA_UNAVAILABLE sentinel string when no vendor has data
            for this ISIN.
    """
    return route_to_vendor("get_fund_fact_sheet", isin)
