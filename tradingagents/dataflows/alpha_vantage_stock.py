from datetime import datetime

from .alpha_vantage_common import _filter_csv_by_date_range, _make_api_request

# Maps yfinance-style interval strings to Alpha Vantage endpoints.
# Intraday intervals are not supported: Alpha Vantage's TIME_SERIES_INTRADAY
# uses a different parameter set and response format that would require a
# separate implementation. Use yfinance for intraday data.
_AV_ENDPOINT_MAP = {
    "1d": "TIME_SERIES_DAILY_ADJUSTED",
    "1wk": "TIME_SERIES_WEEKLY_ADJUSTED",
    "1mo": "TIME_SERIES_MONTHLY_ADJUSTED",
}


def get_stock(
    symbol: str,
    start_date: str,
    end_date: str,
    interval: str = "1d",
) -> str:
    """
    Returns OHLCV values filtered to the specified date range.

    Args:
        symbol: The name of the equity. For example: symbol=IBM
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format
        interval: Candle interval — '1d' (daily), '1wk' (weekly), or '1mo' (monthly).
                  Intraday intervals are not supported by this vendor; use yfinance instead.

    Returns:
        CSV string containing the time series data filtered to the date range.
    """
    endpoint = _AV_ENDPOINT_MAP.get(interval)
    if endpoint is None:
        supported = list(_AV_ENDPOINT_MAP)
        raise ValueError(
            f"Alpha Vantage does not support interval '{interval}'. "
            f"Supported: {supported}. Switch to yfinance for intraday intervals."
        )

    params: dict = {"symbol": symbol, "datatype": "csv"}

    # outputsize only applies to the daily endpoint; weekly/monthly return full history.
    if interval == "1d":
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        days_from_today_to_start = (datetime.now() - start_dt).days
        params["outputsize"] = "compact" if days_from_today_to_start < 100 else "full"

    response = _make_api_request(endpoint, params)

    return _filter_csv_by_date_range(response, start_date, end_date)
