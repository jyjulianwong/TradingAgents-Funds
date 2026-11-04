"""Forward earnings estimates must not leak into a historical run.

Consensus EPS/revenue estimates, estimate-revision counts, analyst price
targets and the next earnings date all reflect today's market consensus with
no historical vintage (unlike a reported EPS, which carries a real report
date) -- a past run would otherwise see today's forward-looking consensus,
not the one that existed on ``as_of_date``. Both vendors withhold on one
shared rule (``date_window.withhold_live_estimates``), mirroring the existing
``withhold_live_profile`` rule for company-overview fields (#1300).
"""

from __future__ import annotations

import json
from unittest import mock

import pandas as pd
import pytest

from tradingagents.dataflows import date_window
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors.alpha_vantage import earnings as av_earnings
from tradingagents.dataflows.vendors.yahoo import earnings as yahoo_earnings

_TODAY = "2026-09-07"
_PAST = "2024-05-10"

_CALENDAR = {
    "Earnings Date": [pd.Timestamp("2026-10-30").date()],
    "Earnings Average": 1.5,
    "Earnings Low": 1.4,
    "Earnings High": 1.6,
}
_EPS_TREND = pd.DataFrame(
    {"current": [1.5], "7daysAgo": [1.49], "30daysAgo": [1.48], "90daysAgo": [1.45]},
    index=pd.Index(["0q"], name="period"),
)
_EPS_REVISIONS = pd.DataFrame(
    {"upLast7days": [2], "upLast30days": [3], "downLast7Days": [0], "downLast30days": [1]},
    index=pd.Index(["0q"], name="period"),
)
_RECOMMENDATIONS = pd.DataFrame(
    {"period": ["0m"], "strongBuy": [5], "buy": [10], "hold": [3], "sell": [1], "strongSell": [0]}
)
_INFO = {
    "targetMeanPrice": 200.0,
    "targetLowPrice": 150.0,
    "targetHighPrice": 250.0,
    "numberOfAnalystOpinions": 20,
    "recommendationKey": "buy",
}

# Values that must never reach a historical run.
_LEAKY = ("1.5", "200.0", "2026-10-30")


class _FakeTicker:
    calendar = _CALENDAR
    eps_trend = _EPS_TREND
    eps_revisions = _EPS_REVISIONS
    recommendations = _RECOMMENDATIONS
    info = _INFO


def _yf(as_of_date, today=_TODAY):
    with (
        mock.patch.object(date_window, "get_current_date", return_value=today),
        mock.patch.object(yahoo_earnings.yf, "Ticker", return_value=_FakeTicker()),
    ):
        return yahoo_earnings.get_earnings_outlook("AAPL", as_of_date)


def _av(as_of_date, today=_TODAY):
    payload = json.dumps(
        {
            "quarterlyEarnings": [
                {
                    "reportedDate": "2026-07-30",
                    "reportedEPS": "1.50",
                    "estimatedEPS": "1.40",
                    "surprisePercentage": "7.14",
                },
            ]
        }
    )
    with (
        mock.patch.object(date_window, "get_current_date", return_value=today),
        mock.patch.object(av_earnings, "_make_api_request", return_value=payload) as req,
    ):
        return av_earnings.get_earnings_outlook("AAPL", as_of_date), req


@pytest.mark.unit
class TestYFinanceHistoricalRun:
    def test_no_estimate_value_survives(self):
        out = _yf(_PAST)
        for leaked in _LEAKY:
            assert leaked not in out, f"leaked live-estimate value {leaked!r}"

    def test_states_the_as_of_date_and_explains_itself(self):
        out = _yf(_PAST)
        assert f"Point-in-time as of: {_PAST}" in out
        assert "withheld" in out
        assert _PAST in out and _TODAY not in out

    def test_the_request_is_not_even_made(self):
        with (
            mock.patch.object(date_window, "get_current_date", return_value=_TODAY),
            mock.patch.object(yahoo_earnings.yf, "Ticker") as tk,
        ):
            yahoo_earnings.get_earnings_outlook("AAPL", _PAST)
        tk.assert_not_called()


@pytest.mark.unit
class TestAlphaVantageHistoricalRun:
    def test_surprise_trend_is_withheld(self):
        out, _ = _av(_PAST)
        assert "1.50" not in out
        assert "withheld" in out
        assert f"Point-in-time as of: {_PAST}" in out

    def test_the_api_call_is_not_made(self):
        _, req = _av(_PAST)
        req.assert_not_called()

    def test_live_run_still_calls_the_api(self):
        out, req = _av(_TODAY)
        req.assert_called_once()
        assert "1.50" in out


@pytest.mark.unit
class TestLiveRunUnchanged:
    def test_yfinance_current_date_returns_the_full_outlook(self):
        out = _yf(_TODAY)
        for value in _LEAKY:
            assert value in out
        assert "withheld" not in out

    def test_yfinance_absent_curr_date_returns_the_full_outlook(self):
        out = _yf(None)
        assert "withheld" not in out
        assert "2026-10-30" in out


@pytest.mark.unit
def test_etf_with_no_earnings_coverage_raises_no_market_data():
    class _EmptyTicker:
        calendar = {}
        eps_trend = pd.DataFrame()
        eps_revisions = pd.DataFrame()
        recommendations = pd.DataFrame()
        info = {}

    with (
        mock.patch.object(date_window, "get_current_date", return_value=_TODAY),
        mock.patch.object(yahoo_earnings.yf, "Ticker", return_value=_EmptyTicker()),
        mock.patch(
            "tradingagents.dataflows.vendors.yahoo.common.vendor_reachable", return_value=True
        ),
        pytest.raises(NoMarketDataError),
    ):
        yahoo_earnings.get_earnings_outlook("SPY", _TODAY)


@pytest.mark.unit
def test_alpha_vantage_etf_degrades_gracefully_without_raising():
    with (
        mock.patch.object(date_window, "get_current_date", return_value=_TODAY),
        mock.patch.object(av_earnings, "_make_api_request", return_value="{}"),
    ):
        out = av_earnings.get_earnings_outlook("SPY", _TODAY)
    assert "Not provided" in out
