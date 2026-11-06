"""Trailing P/E percentile reconstruction stays point-in-time-correct (#1300 family).

Every input (a reported EPS's report date, a historical close) is itself
historically dated, so filtering both to "on or before as_of_date" makes the
reconstruction safe for a backtest without a "withhold" sentinel -- unlike
``get_earnings_outlook``'s live consensus estimates. This exercises that
filtering, the percentile math, and the "no EPS" / "insufficient history"
degradation paths deterministically, with no live network access.
"""

from __future__ import annotations

from unittest import mock

import pandas as pd
import pytest

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors.yahoo import valuation

_TZ = "America/New_York"


def _earnings_dates(report_eps: dict[str, float]) -> pd.DataFrame:
    index = pd.DatetimeIndex(list(report_eps), tz=_TZ)
    return pd.DataFrame({"Reported EPS": list(report_eps.values())}, index=index)


def _history(closes: dict[str, float]) -> pd.DataFrame:
    index = pd.DatetimeIndex(list(closes), tz=_TZ)
    return pd.DataFrame({"Close": list(closes.values())}, index=index)


# 7 reported quarters of EPS 1.00 each (TTM EPS is a constant 4.00 from the
# 4th quarter on), with a rising price at each report date so the resulting
# quarterly P/E series is known: 10, 11, 12, 13 (for Q4..Q7).
_REPORTED = {
    "2022-01-01": 1.0,
    "2022-04-01": 1.0,
    "2022-07-01": 1.0,
    "2022-10-01": 1.0,
    "2023-01-01": 1.0,
    "2023-04-01": 1.0,
    "2023-07-01": 1.0,
}
_CLOSES = {
    "2022-01-01": 40.0,
    "2022-04-01": 40.0,
    "2022-07-01": 40.0,
    "2022-10-01": 40.0,
    "2023-01-01": 44.0,
    "2023-04-01": 48.0,
    "2023-07-01": 52.0,
    "2023-08-15": 60.0,
}


def _build(as_of_date, report_eps=_REPORTED, closes=_CLOSES, lookback_years=10):
    fake_ticker = mock.Mock()
    fake_ticker.earnings_dates = _earnings_dates(report_eps)
    fake_ticker.history.return_value = _history(closes)
    with (
        mock.patch.object(valuation.yf, "Ticker", return_value=fake_ticker),
        mock.patch.object(
            valuation, "get_macro_data", side_effect=RuntimeError("no network in tests")
        ),
    ):
        return valuation.build_valuation_history("AAPL", as_of_date, lookback_years)


@pytest.mark.unit
def test_percentile_and_current_pe_are_computed_correctly():
    out = _build("2023-08-15")
    # current P/E = latest close (60.0) / latest TTM EPS (4.0) = 15.0
    assert "Current Trailing P/E: 15.00x" in out
    # historical series is [10, 11, 12, 13]; 15.0 sits above all of them
    assert "100th percentile" in out
    assert "historically expensive" in out
    assert "min 10.0x" in out and "max 13.0x" in out


@pytest.mark.unit
def test_future_quarter_is_excluded_from_a_historical_run():
    # A quarter reported after as_of_date must not affect the reconstruction:
    # point-in-time correctness, not a live-snapshot "withhold" (#1300 family).
    leaking_report = dict(_REPORTED)
    leaking_report["2023-10-01"] = 999.0  # would blow up TTM EPS if included
    leaking_closes = dict(_CLOSES)
    leaking_closes["2023-10-01"] = 1.0

    out = _build("2023-08-15", report_eps=leaking_report, closes=leaking_closes)
    assert "999" not in out
    assert "Current Trailing P/E: 15.00x" in out


@pytest.mark.unit
def test_insufficient_reported_quarters_raises_no_market_data():
    with pytest.raises(NoMarketDataError):
        _build("2022-10-01", report_eps={"2022-01-01": 1.0, "2022-04-01": 1.0})


@pytest.mark.unit
def test_etf_with_no_earnings_raises_no_market_data(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.dataflows.vendors.yahoo.valuation.vendor_reachable", lambda url: True
    )
    fake_ticker = mock.Mock()
    fake_ticker.earnings_dates = None
    with (
        mock.patch.object(valuation.yf, "Ticker", return_value=fake_ticker),
        pytest.raises(NoMarketDataError),
    ):
        valuation.build_valuation_history("SPY", "2023-08-15")


@pytest.mark.unit
def test_negative_ttm_eps_reports_not_meaningful_instead_of_crashing():
    negative_eps = dict(_REPORTED)
    negative_eps["2023-07-01"] = -10.0  # makes the latest TTM EPS negative
    out = _build("2023-08-15", report_eps=negative_eps)
    assert "N/M" in out or "not meaningful" in out
