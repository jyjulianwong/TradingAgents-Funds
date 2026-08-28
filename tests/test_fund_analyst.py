"""Tests for the Fund Analyst node and its supporting pieces.

Covers: is_isin / resolve_isin_ticker_list state-awareness, the mstarpy
vendor module's typed-error behavior, and the Fund Analyst node's
non-ISIN passthrough / dynamic-resolution / deterministic-fallback paths.
"""

import copy
from unittest import mock

import pandas as pd
import pytest

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.agents.analysts.fund_analyst import create_fund_analyst
from tradingagents.agents.schemas import FundHoldingsAnalysis
from tradingagents.agents.utils.agent_utils import is_isin, resolve_isin_ticker_list
from tradingagents.dataflows import interface
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import NoMarketDataError

ISIN = "IE00B4L5Y983"


def _reset_config():
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)


@pytest.fixture(autouse=True)
def _config_reset():
    _reset_config()
    yield
    _reset_config()


# ---------------------------------------------------------------------------
# is_isin / resolve_isin_ticker_list
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIsIsin:
    def test_valid_isin(self):
        assert is_isin(ISIN) is True

    def test_ordinary_ticker(self):
        assert is_isin("AAPL") is False

    def test_crypto_ticker(self):
        assert is_isin("BTC-USD") is False


@pytest.mark.unit
class TestResolveIsinTickerList:
    def test_non_isin_passthrough(self):
        assert resolve_isin_ticker_list("AAPL") == ["AAPL"]

    def test_no_state_falls_back_to_static_map(self):
        set_config({"isin_ticker_map": {ISIN: ["IWDA.L", "SWRD.L"]}})
        assert resolve_isin_ticker_list(ISIN) == [ISIN, "IWDA.L", "SWRD.L"]

    def test_state_with_fund_proxy_tickers_takes_precedence_over_map(self):
        # Even though the static map has an entry, a state carrying the
        # Fund Analyst's own resolution (however it got there) wins.
        set_config({"isin_ticker_map": {ISIN: ["STALE_MAP_TICKER"]}})
        state = {"fund_proxy_tickers": ["AAPL", "MSFT"]}
        assert resolve_isin_ticker_list(ISIN, state) == [ISIN, "AAPL", "MSFT"]

    def test_state_with_empty_fund_proxy_tickers_is_authoritative(self):
        # An empty list (Fund Analyst ran, found nothing, map had no entry
        # either) must NOT re-trigger a fallback map lookup here — the Fund
        # Analyst already tried that.
        set_config({"isin_ticker_map": {ISIN: ["SHOULD_NOT_BE_USED"]}})
        state = {"fund_proxy_tickers": []}
        assert resolve_isin_ticker_list(ISIN, state) == [ISIN]

    def test_state_missing_key_falls_back_to_map(self):
        # Bare state built without running the Fund Analyst (e.g. tests).
        set_config({"isin_ticker_map": {ISIN: ["IWDA.L"]}})
        state = {"company_of_interest": ISIN}
        assert resolve_isin_ticker_list(ISIN, state) == [ISIN, "IWDA.L"]


# ---------------------------------------------------------------------------
# mstarpy vendor module
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMstarpyFundVendor:
    def test_holdings_formatted_with_ticker_and_weight(self):
        import mstarpy

        from tradingagents.dataflows import mstarpy_fund

        fake_fund = mock.Mock()
        fake_fund.name = "Test Fund"
        fake_fund.holdings.return_value = pd.DataFrame([
            {"ticker": "AAPL", "securityName": "Apple Inc", "weighting": 5.5},
            {"ticker": "", "securityName": "US Treasury Bond", "weighting": 2.0},
        ])

        with mock.patch.object(mstarpy_fund, "_get_session", return_value=mock.Mock()), \
                mock.patch.object(mstarpy, "Funds", return_value=fake_fund):
            result = mstarpy_fund.get_fund_holdings(ISIN)

        assert "AAPL" in result
        assert "Apple Inc" in result
        assert "5.50" in result
        assert ISIN in result

    def test_no_fund_found_raises_no_market_data_error(self):
        import mstarpy

        from tradingagents.dataflows import mstarpy_fund

        with mock.patch.object(mstarpy_fund, "_get_session", return_value=mock.Mock()), \
                mock.patch.object(
                    mstarpy, "Funds", side_effect=ValueError(f"0 fund found with the term {ISIN}")
                ), pytest.raises(NoMarketDataError):
            mstarpy_fund.get_fund_holdings(ISIN)

    def test_empty_holdings_raises_no_market_data_error(self):
        import mstarpy

        from tradingagents.dataflows import mstarpy_fund

        fake_fund = mock.Mock()
        fake_fund.holdings.return_value = pd.DataFrame([])

        with mock.patch.object(mstarpy_fund, "_get_session", return_value=mock.Mock()), \
                mock.patch.object(mstarpy, "Funds", return_value=fake_fund), \
                pytest.raises(NoMarketDataError):
            mstarpy_fund.get_fund_holdings(ISIN)

    def test_vendor_failure_degrades_to_sentinel_not_exception(self):
        # fund_fact_sheet_data is an OPTIONAL_CATEGORIES entry: route_to_vendor
        # must return a DATA_UNAVAILABLE string, never raise, so a Chrome/mstarpy
        # outage can't take down the whole graph run.
        assert "fund_fact_sheet_data" in interface.OPTIONAL_CATEGORIES
        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_fund_fact_sheet": {"mstarpy": mock.Mock(side_effect=RuntimeError("no chrome"))}},
        ):
            result = interface.route_to_vendor("get_fund_fact_sheet", ISIN)
        assert result.startswith("DATA_UNAVAILABLE")


# ---------------------------------------------------------------------------
# Fund Analyst node
# ---------------------------------------------------------------------------


def _make_state(ticker: str, asset_type: str = "stock"):
    return {
        "company_of_interest": ticker,
        "asset_type": asset_type,
        "messages": [],
    }


@pytest.mark.unit
class TestFundAnalystNode:
    def test_non_isin_ticker_is_a_no_op(self):
        node = create_fund_analyst(mock.MagicMock())
        result = node(_make_state("AAPL"))
        assert result == {}

    def test_isin_with_successful_mstarpy_synthesis(self):
        llm = mock.MagicMock()
        structured = mock.MagicMock()
        structured.invoke.return_value = FundHoldingsAnalysis(
            proxy_tickers=["AAPL", "MSFT"], rationale="Top two holdings by weight."
        )
        llm.with_structured_output.return_value = structured

        with mock.patch(
            "tradingagents.agents.analysts.fund_analyst.get_fund_fact_sheet"
        ) as tool_mock:
            tool_mock.func.return_value = "ticker | security_name | weighting_pct\nAAPL | Apple | 5.5"
            node = create_fund_analyst(llm)
            result = node(_make_state(ISIN))

        assert result["fund_proxy_tickers"] == ["AAPL", "MSFT"]
        assert "AAPL" in result["instrument_context"]
        assert "MSFT" in result["instrument_context"]
        assert "mstarpy" in result["fund_report"]

    def test_tool_failure_falls_back_to_static_map(self):
        set_config({"isin_ticker_map": {ISIN: ["IWDA.L", "SWRD.L"]}})
        llm = mock.MagicMock()
        structured = mock.MagicMock()
        llm.with_structured_output.return_value = structured

        with mock.patch(
            "tradingagents.agents.analysts.fund_analyst.get_fund_fact_sheet"
        ) as tool_mock:
            tool_mock.func.return_value = "NO_DATA_AVAILABLE: No usable data for 'X'."
            node = create_fund_analyst(llm)
            result = node(_make_state(ISIN))

        assert result["fund_proxy_tickers"] == ["IWDA.L", "SWRD.L"]
        assert "isin_ticker_map fallback" in result["fund_report"]
        # A failed tool call must never reach the LLM to judge — the
        # structured call itself is skipped entirely, not just its result.
        structured.invoke.assert_not_called()

    def test_empty_llm_synthesis_falls_back_to_static_map(self):
        set_config({"isin_ticker_map": {ISIN: ["IWDA.L"]}})
        llm = mock.MagicMock()
        structured = mock.MagicMock()
        structured.invoke.return_value = FundHoldingsAnalysis(proxy_tickers=[], rationale="")
        llm.with_structured_output.return_value = structured

        with mock.patch(
            "tradingagents.agents.analysts.fund_analyst.get_fund_fact_sheet"
        ) as tool_mock:
            tool_mock.func.return_value = "ticker | security_name | weighting_pct\n(bonds only, no tickers)"
            node = create_fund_analyst(llm)
            result = node(_make_state(ISIN))

        assert result["fund_proxy_tickers"] == ["IWDA.L"]

    def test_no_data_anywhere_yields_empty_proxy_list(self):
        # No map entry configured, mstarpy also unavailable.
        llm = mock.MagicMock()

        with mock.patch(
            "tradingagents.agents.analysts.fund_analyst.get_fund_fact_sheet"
        ) as tool_mock:
            tool_mock.func.return_value = "DATA_UNAVAILABLE: optional fund_fact_sheet_data could not be retrieved."
            node = create_fund_analyst(llm)
            result = node(_make_state(ISIN))

        assert result["fund_proxy_tickers"] == []
        assert "none" in result["fund_report"]

    def test_tool_exception_falls_back_to_static_map(self):
        set_config({"isin_ticker_map": {ISIN: ["IWDA.L"]}})
        llm = mock.MagicMock()

        with mock.patch(
            "tradingagents.agents.analysts.fund_analyst.get_fund_fact_sheet"
        ) as tool_mock:
            tool_mock.func.side_effect = RuntimeError("boom")
            node = create_fund_analyst(llm)
            result = node(_make_state(ISIN))

        assert result["fund_proxy_tickers"] == ["IWDA.L"]

    def test_result_carries_proxy_source_for_dynamic_resolution(self):
        llm = mock.MagicMock()
        structured = mock.MagicMock()
        structured.invoke.return_value = FundHoldingsAnalysis(
            proxy_tickers=["AAPL", "MSFT"], rationale="Top two holdings by weight."
        )
        llm.with_structured_output.return_value = structured

        with mock.patch(
            "tradingagents.agents.analysts.fund_analyst.get_fund_fact_sheet"
        ) as tool_mock:
            tool_mock.func.return_value = "ticker | security_name | weighting_pct\nAAPL | Apple | 5.5"
            node = create_fund_analyst(llm)
            result = node(_make_state(ISIN))

        assert result["fund_proxy_source"] == "mstarpy fund holdings"

    def test_result_carries_proxy_source_for_static_fallback(self):
        set_config({"isin_ticker_map": {ISIN: ["IWDA.L"]}})
        llm = mock.MagicMock()

        with mock.patch(
            "tradingagents.agents.analysts.fund_analyst.get_fund_fact_sheet"
        ) as tool_mock:
            tool_mock.func.side_effect = RuntimeError("boom")
            node = create_fund_analyst(llm)
            result = node(_make_state(ISIN))

        assert result["fund_proxy_source"] == "isin_ticker_map fallback"


@pytest.mark.unit
class TestFundHoldingsAnalysisTickerCap:
    """The model is told to aim for 3-5 tickers, but the validator must not
    trust it to honor that limit — it has to enforce the cap itself."""

    def test_more_than_five_tickers_is_truncated_to_five(self):
        result = FundHoldingsAnalysis(
            proxy_tickers=["AAPL", "MSFT", "GOOG", "AMZN", "NVDA", "META", "TSLA"],
            rationale="too many",
        )
        assert result.proxy_tickers == ["AAPL", "MSFT", "GOOG", "AMZN", "NVDA"]

    def test_dedup_then_cap_keeps_first_five_distinct(self):
        result = FundHoldingsAnalysis(
            proxy_tickers=["AAPL", "aapl", "MSFT", "GOOG", "AMZN", "NVDA", "META"],
            rationale="dupes before cap",
        )
        assert result.proxy_tickers == ["AAPL", "MSFT", "GOOG", "AMZN", "NVDA"]

    def test_three_to_five_tickers_pass_through_unchanged(self):
        result = FundHoldingsAnalysis(proxy_tickers=["GDX", "NEM", "GOLD"], rationale="gold")
        assert result.proxy_tickers == ["GDX", "NEM", "GOLD"]
