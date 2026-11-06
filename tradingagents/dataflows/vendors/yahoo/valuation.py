# FORK(funds): valuation-history
"""Trailing P/E percentile vs. an instrument's own history, via yfinance.

Unlike ``get_fundamentals``'s present-day ``trailingPE``/``forwardPE`` snapshot,
this reconstructs a historical trailing-twelve-month P/E series from reported
EPS (dated by its real report date) and historical close prices, so a run can
say whether today's multiple is cheap or expensive relative to the
instrument's *own* history, not just its level today.

Every input here is itself historically dated (a reported EPS carries its own
``reportedDate``; a close price is dated by the trading day), so filtering
both to "on or before ``as_of_date``" makes the whole reconstruction naturally
point-in-time-safe -- unlike ``get_earnings_outlook``'s live consensus
estimates, this needs no "withhold" sentinel for a historical run.

Only meaningful for an instrument with real reported earnings: an ETF/index
proxy ticker has no EPS to reconstruct a P/E history from, and this reports
that plainly rather than approximating one from net asset value.
"""

import re
from typing import Annotated

import pandas as pd
import yfinance as yf

from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.net import vendor_reachable
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.fred import get_macro_data
from tradingagents.dataflows.vendors.yahoo.common import YAHOO_HOST, yf_retry

_MIN_QUARTERS = 4


def _percentile_rank(value: float, series: list[float]) -> float:
    """Percentile of ``value`` within ``series`` (0-100, inclusive of ties)."""
    return 100.0 * sum(1 for v in series if v <= value) / len(series)


def build_valuation_history(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"],
    lookback_years: Annotated[int, "how many years of reported history to use"] = 10,
) -> str:
    """Trailing P/E percentile, earnings yield, and the equity risk premium, as of ``as_of_date``."""
    canonical = normalize_symbol(ticker)
    as_of = pd.Timestamp(as_of_date)

    earnings_dates = yf_retry(lambda: yf.Ticker(canonical).earnings_dates)
    if earnings_dates is None or earnings_dates.empty:
        if not vendor_reachable(YAHOO_HOST):
            raise VendorUnavailableError(
                "Yahoo Finance is unreachable; no earnings history was retrieved"
            )
        raise NoMarketDataError(
            ticker,
            canonical,
            "no reported earnings (this is expected for an ETF/index instrument, "
            "which has no EPS to build a valuation history from)",
        )

    reported = earnings_dates["Reported EPS"].dropna().sort_index()
    reported.index = reported.index.tz_localize(None)
    reported = reported[reported.index <= as_of]
    if len(reported) < _MIN_QUARTERS:
        raise NoMarketDataError(
            ticker,
            canonical,
            f"only {len(reported)} reported quarter(s) as of {as_of_date}, "
            f"fewer than the {_MIN_QUARTERS} needed for a trailing P/E",
        )

    cutoff = as_of - pd.DateOffset(years=lookback_years)
    start = min(reported.index.min(), cutoff).strftime("%Y-%m-%d")
    history = yf_retry(
        lambda: yf.Ticker(canonical).history(
            start=start, end=(as_of + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        )
    )
    if history is None or history.empty:
        raise NoMarketDataError(
            ticker, canonical, f"no price history available on or before {as_of_date}"
        )
    history.index = history.index.tz_localize(None)
    closes = history["Close"]

    dates = reported.index
    # (report_date, P/E) pairs, kept together so a skipped quarter (negative
    # TTM EPS, or no price on/after it) never desynchronizes a later
    # date-based filter from the values it is meant to filter.
    dated_series: list[tuple[pd.Timestamp, float]] = []
    for i in range(_MIN_QUARTERS - 1, len(dates)):
        report_date = dates[i]
        ttm_eps = reported.iloc[i - _MIN_QUARTERS + 1 : i + 1].sum()
        if ttm_eps <= 0:
            continue
        price_on_or_after = closes[closes.index >= report_date]
        if price_on_or_after.empty:
            continue
        dated_series.append((report_date, float(price_on_or_after.iloc[0]) / float(ttm_eps)))

    if not dated_series:
        raise NoMarketDataError(
            ticker,
            canonical,
            "reported EPS has never been positive, so no trailing P/E could be computed",
        )
    series = [pe for _, pe in dated_series]

    latest_ttm_eps = float(reported.iloc[-_MIN_QUARTERS:].sum())
    latest_close = float(closes[closes.index <= as_of].iloc[-1])
    if latest_ttm_eps <= 0:
        return (
            f"# Valuation History for {canonical}\n"
            f"# Point-in-time as of: {as_of_date}\n\n"
            f"Trailing twelve-month EPS is currently negative ({latest_ttm_eps:.2f}), so "
            f"today's P/E is not meaningful (N/M). Historical context from "
            f"{len(series)} prior reported quarters: min {min(series):.1f}x, "
            f"median {pd.Series(series).median():.1f}x, max {max(series):.1f}x."
        )

    cutoff_series = [pe for d, pe in dated_series if d >= cutoff] or series
    current_pe = latest_close / latest_ttm_eps
    percentile = _percentile_rank(current_pe, cutoff_series)
    earnings_yield = 100.0 / current_pe

    read = (
        "historically cheap"
        if percentile <= 33
        else "historically expensive"
        if percentile >= 67
        else "roughly mid-range for this instrument"
    )

    lines = [
        f"# Valuation History for {canonical}",
        f"# Point-in-time as of: {as_of_date}\n",
        f"Current Trailing P/E: {current_pe:.2f}x (close {latest_close:.2f} / TTM EPS {latest_ttm_eps:.2f})",
        f"Percentile vs. own trailing ~{lookback_years}y history "
        f"({len(cutoff_series)} reported quarters): {percentile:.0f}th percentile — {read}.",
        f"Historical range: min {min(cutoff_series):.1f}x, "
        f"median {pd.Series(cutoff_series).median():.1f}x, max {max(cutoff_series):.1f}x.",
        f"Earnings Yield: {earnings_yield:.2f}%",
    ]

    try:
        treasury_report = get_macro_data("10y_treasury", as_of_date, look_back_days=14)
        match = re.search(r"\*\*Latest:\*\*\s*([-+]?\d+\.?\d*)", treasury_report)
        if match:
            ten_year = float(match.group(1))
            lines.append(
                f"Equity Risk Premium (earnings yield − 10y Treasury yield {ten_year:.2f}%): "
                f"{earnings_yield - ten_year:.2f} pp"
            )
    except Exception:
        # FRED is an optional cross-check here; its own tool already reports
        # unavailability elsewhere, so this report still stands without it.
        pass

    return "\n".join(lines)
