from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    interval: Annotated[
        str,
        "Candle interval. Options: '1d' (daily), '1wk' (weekly), '1mo' (monthly), "
        "'1h' (hourly), '30m', '15m', '5m', '2m', '1m'. "
        "Omit to use the configured ohlcv_interval (default '1d').",
    ] = None,
) -> str:
    """
    Retrieve stock price data (OHLCV) for a given ticker symbol.
    Uses the configured core_stock_apis vendor.
    Args:
        symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
        interval (str): Candle interval (e.g. '1d', '1h', '1wk'). Defaults to the configured ohlcv_interval.
    Returns:
        str: A formatted dataframe containing the stock price data for the specified ticker symbol in the specified date range.
    """
    if interval is None:
        from tradingagents.dataflows.config import get_config
        interval = get_config().get("tool_vendors", {}).get("ohlcv_interval", "1d")
    return route_to_vendor("get_stock_data", symbol, start_date, end_date, interval)
