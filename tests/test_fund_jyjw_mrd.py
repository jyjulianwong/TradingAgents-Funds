"""Tests for the US macro regime context (fork-specific).

Covers: the Market Regime Detector client, the rendered block, the Fund
Analyst's live-only fetch, and that only the investment debate reads it.
"""

import copy
from unittest import mock

import pytest
import requests

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.agents.analysts.fund_analyst import create_fund_analyst
from tradingagents.agents.fund_jyjw_mrd import (
    get_jyjw_mrd_instruction,
    render_jyjw_mrd_block,
)
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.vendors import jyjw_mrd
from tradingagents.dataflows.vendors.jyjw_mrd import (
    JyjwMrdUnavailableError,
    fetch_jyjw_mrd_latest,
)
from tradingagents.reporting import write_report_tree

ISIN = "IE00B4L5Y983"
FUND_ANALYST = "tradingagents.agents.analysts.fund_analyst"

PAYLOAD = {
    "model_id": "m-1",
    "model_name": "allweather-hmm2naive-us",
    "dataset_id": "d-1",
    "asof": "2026-11-05",
    "generated_at": "2026-11-05T06:00:00Z",
    "observation_date": "2026-10-31",
    "is_stale": False,
    "latest": {
        "p_growth_up": 0.31,
        "p_inflation_up": 0.72,
        "quadrants": {
            "GROWTH_UP_INFLATION_DOWN": 0.08,
            "GROWTH_UP_INFLATION_UP": 0.23,
            "GROWTH_DOWN_INFLATION_UP": 0.49,
            "GROWTH_DOWN_INFLATION_DOWN": 0.20,
        },
        "regime": "GROWTH_DOWN_INFLATION_UP",
        "confidence": 0.49,
        "data": [
            {
                "name": "RAW_SERIES_CPIAUCSL",
                "description": "CPI | all urban consumers",
                "value": 321.456,
                "realtime_start": "2026-10-15",
                "date": "2026-09-01",
                "lag_days": 44,
            },
            {
                "name": "PAYEMS",
                "description": "Nonfarm payrolls (thousands)",
                "value": 159234.0,
                "realtime_start": "2026-11-01",
                "date": "2026-10-01",
                "lag_days": 31,
            },
        ],
        "features": [
            {
                "name": "cpilfesl_3m_annualized_change",
                "description": "3-month annualized % change in core CPI | inflation",
                "value": 0.034124037788220596,
                "realtime_start": "2026-10-14",
                "date": "2026-09-01",
                "lag_days": 22,
            },
            {
                "name": "icsa_4wk_avg_change",
                "description": "Change in the 4-week average of initial claims (growth, inverted)",
                "value": -1250.0,
                "realtime_start": "2026-10-29",
                "date": "2026-10-24",
                "lag_days": 7,
            },
            {
                "name": "t10yie_1m_change",
                "description": "1-month change in the 10-year breakeven inflation rate (inflation)",
                "value": -0.08000000000000007,
                "realtime_start": "2026-11-04",
                "date": "2026-11-04",
                "lag_days": 1,
            },
            {
                "name": "empire_state_level",
                "description": "Empire State Manufacturing Survey, raw level (growth)",
                "value": 25.5,
                "realtime_start": "2026-10-15",
                "date": "2026-10-01",
                "lag_days": 21,
            },
        ],
    },
    "warnings": ["CPI series lags by 44 days"],
    "disclaimer": "Not financial advice.",
}


def _reset_config():
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)


@pytest.fixture(autouse=True)
def _config_reset():
    _reset_config()
    yield
    _reset_config()


def _fund_state(trade_date):
    state = {"company_of_interest": ISIN, "asset_type": "stock", "messages": []}
    if trade_date is not None:
        state["trade_date"] = trade_date
    return state


def _run_fund_analyst(trade_date, fetch=None):
    """Run the Fund Analyst on the static-map path, with the regime fetch mocked."""
    set_config({"isin_ticker_map_override": True, "isin_ticker_map": {ISIN: ["IWDA.L"]}})
    fetch = fetch or mock.Mock(return_value=PAYLOAD)
    with mock.patch(f"{FUND_ANALYST}.fetch_jyjw_mrd_latest", fetch):
        result = create_fund_analyst(mock.MagicMock())(_fund_state(trade_date))
    return result, fetch


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFetchJyjwMrdLatest:
    def test_builds_the_latest_url_and_returns_the_payload(self):
        response = mock.Mock(json=mock.Mock(return_value=PAYLOAD))
        with mock.patch.object(jyjw_mrd, "get_scrubbed", return_value=response) as get:
            assert (
                fetch_jyjw_mrd_latest("https://api.example/", "allweather-hmm2naive-us") == PAYLOAD
            )
        assert get.call_args.args[0] == (
            "https://api.example/v1/models/allweather-hmm2naive-us/predictions/latest"
        )

    def test_network_error_is_unavailable(self):
        with (
            mock.patch.object(
                jyjw_mrd, "get_scrubbed", side_effect=requests.ConnectionError("down")
            ),
            pytest.raises(JyjwMrdUnavailableError),
        ):
            fetch_jyjw_mrd_latest("https://api.example", "m")

    def test_missing_latest_snapshot_is_unavailable(self):
        response = mock.Mock(json=mock.Mock(return_value={**PAYLOAD, "latest": None}))
        with (
            mock.patch.object(jyjw_mrd, "get_scrubbed", return_value=response),
            pytest.raises(JyjwMrdUnavailableError),
        ):
            fetch_jyjw_mrd_latest("https://api.example", "m")

    def test_blocked_network_surfaces_as_unavailable(self):
        # The autouse _no_network fixture refuses the socket; it must come
        # back as the typed error the Fund Analyst catches, not a crash.
        with pytest.raises(JyjwMrdUnavailableError):
            fetch_jyjw_mrd_latest("https://api.example", "m")


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenderRegimeBlock:
    def test_contents(self):
        block = render_jyjw_mrd_block(PAYLOAD)
        assert "specific to the United States" in block
        assert "`GROWTH_DOWN_INFLATION_UP`" in block
        assert "stagflation" in block
        assert "Confidence**: 49%" in block
        assert "GROWTH_UP_INFLATION_UP 23%" in block
        assert "CPI series lags by 44 days" in block
        assert "`GROWTH_DOWN_INFLATION_UP` ← current" in block

    def test_features_are_shown_with_descriptions(self):
        block = render_jyjw_mrd_block(PAYLOAD)
        assert "| cpilfesl_3m_annualized_change |" in block
        assert "core CPI / inflation" in block  # pipe escaped for the table
        assert "| 2026-09-01 |" in block

    def test_feature_values_are_formatted_by_kind(self):
        block = render_jyjw_mrd_block(PAYLOAD)
        assert "| +3.41% |" in block  # "% change" fraction -> percentage
        assert "| -1,250 |" in block  # other change -> signed
        assert "| -0.08 |" in block  # float noise trimmed
        assert "| 25.5 |" in block  # level -> plain

    def test_raw_data_is_left_out(self):
        assert "RAW_SERIES_CPIAUCSL" not in render_jyjw_mrd_block(PAYLOAD)

    def test_stale_is_flagged(self):
        assert "STALE" in render_jyjw_mrd_block({**PAYLOAD, "is_stale": True})
        assert "STALE" not in render_jyjw_mrd_block(PAYLOAD)

    def test_instruction_is_empty_without_a_report(self):
        assert get_jyjw_mrd_instruction({}) == ""
        assert get_jyjw_mrd_instruction(None) == ""
        assert get_jyjw_mrd_instruction({"jyjw_mrd_report": ""}) == ""
        assert get_jyjw_mrd_instruction({"jyjw_mrd_report": "X"}) == "\n\nX"


# ---------------------------------------------------------------------------
# Fund Analyst
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFundAnalystRegime:
    def test_live_fund_run_fetches_the_configured_model(self):
        result, fetch = _run_fund_analyst(get_current_date())
        fetch.assert_called_once_with(
            "https://6nbosjpuc9.execute-api.eu-west-2.amazonaws.com", "allweather-hmm2naive-us"
        )
        assert "GROWTH_DOWN_INFLATION_UP" in result["jyjw_mrd_report"]
        # The fund report records only the headline; the full block is saved on its own.
        assert "`GROWTH_DOWN_INFLATION_UP` (confidence 49%" in result["fund_report"]
        assert "allweather-hmm2naive-us" in result["fund_report"]
        assert "trend features" not in result["fund_report"]
        # The analysts read instrument_context; the regime must stay out of it.
        assert "MACRO REGIME" not in result["instrument_context"]

    def test_historical_run_skips_the_fetch(self):
        result, fetch = _run_fund_analyst("2020-01-02")
        fetch.assert_not_called()
        assert result["jyjw_mrd_report"] == ""
        assert "skipped (historical run" in result["fund_report"]

    def test_run_without_a_date_skips_the_fetch(self):
        result, fetch = _run_fund_analyst(None)
        fetch.assert_not_called()
        assert result["jyjw_mrd_report"] == ""

    def test_empty_url_turns_it_off(self):
        set_config({"jyjw_mrd_api_url": ""})
        fetch = mock.Mock(return_value=PAYLOAD)
        with mock.patch(f"{FUND_ANALYST}.fetch_jyjw_mrd_latest", fetch):
            result = create_fund_analyst(mock.MagicMock())(_fund_state(get_current_date()))
        fetch.assert_not_called()
        assert result["jyjw_mrd_report"] == ""
        assert "macro regime" not in result["fund_report"].lower()

    def test_fetch_failure_keeps_the_run_going(self):
        fetch = mock.Mock(side_effect=JyjwMrdUnavailableError("timeout"))
        result, _ = _run_fund_analyst(get_current_date(), fetch)
        assert result["fund_proxy_tickers"] == ["IWDA.L"]
        assert result["jyjw_mrd_report"] == ""
        assert "unavailable for this run (timeout)" in result["fund_report"]

    def test_ordinary_ticker_is_still_a_no_op(self):
        fetch = mock.Mock(return_value=PAYLOAD)
        with mock.patch(f"{FUND_ANALYST}.fetch_jyjw_mrd_latest", fetch):
            state = {**_fund_state(get_current_date()), "company_of_interest": "AAPL"}
            assert create_fund_analyst(mock.MagicMock())(state) == {}
        fetch.assert_not_called()


# ---------------------------------------------------------------------------
# Debate prompts
# ---------------------------------------------------------------------------


def _debate_state(jyjw_mrd_report):
    return {
        "company_of_interest": ISIN,
        "asset_type": "stock",
        "trade_date": get_current_date(),
        "instrument_context": "instrument",
        "market_report": "m",
        "sentiment_report": "s",
        "news_report": "n",
        "fundamentals_report": "f",
        "fund_proxy_tickers": ["IWDA.L"],
        "jyjw_mrd_report": jyjw_mrd_report,
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
        },
    }


def _prompt_text(llm):
    prompt = llm.invoke.call_args.args[0]
    return prompt if isinstance(prompt, str) else str(prompt)


@pytest.mark.unit
class TestDebatePrompts:
    @pytest.mark.parametrize("factory", [create_bull_researcher, create_bear_researcher])
    def test_researchers_see_the_regime(self, factory):
        llm = mock.MagicMock()
        llm.invoke.return_value = mock.Mock(content="argument")
        factory(llm)(_debate_state("REGIME-BLOCK-123"))
        assert "REGIME-BLOCK-123" in _prompt_text(llm)

    @pytest.mark.parametrize("factory", [create_bull_researcher, create_bear_researcher])
    def test_researchers_unchanged_without_it(self, factory):
        llm = mock.MagicMock()
        llm.invoke.return_value = mock.Mock(content="argument")
        factory(llm)(_debate_state(""))
        assert "MACRO REGIME" not in _prompt_text(llm)

    def test_research_manager_sees_the_regime(self):
        llm = mock.MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError
        llm.invoke.return_value = mock.Mock(content="Rating: Hold")
        create_research_manager(llm)(_debate_state("REGIME-BLOCK-123"))
        assert "REGIME-BLOCK-123" in _prompt_text(llm)


# ---------------------------------------------------------------------------
# Saved report
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_saved_report_includes_the_regime_file(tmp_path):
    state = {"fund_report": "fund", "jyjw_mrd_report": "REGIME-BLOCK-123"}
    complete = write_report_tree(state, ISIN, tmp_path, html=False)
    saved = tmp_path / "1_analysts" / "jyjw_mrd.md"
    assert saved.read_text(encoding="utf-8") == "REGIME-BLOCK-123"
    assert "### Market Regime Detector" in complete.read_text(encoding="utf-8")
