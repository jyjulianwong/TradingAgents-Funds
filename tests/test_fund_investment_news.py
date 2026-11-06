"""Tests for the Investment News Analysis AI report (fork-specific).

Covers: the report client, the lookback over dated reports, the Fund
Analyst's fetch, that only the investment debate reads it, and the saved report.
"""

import copy
from datetime import date
from unittest import mock

import pytest
import requests

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.agents import fund_investment_news
from tradingagents.agents.analysts.fund_analyst import create_fund_analyst
from tradingagents.agents.fund_investment_news import (
    fetch_investment_news,
    find_latest_report,
    get_investment_news_instruction,
    render_news_block,
)
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.vendors import investment_news
from tradingagents.dataflows.vendors.investment_news import (
    InvestmentNewsUnavailableError,
    fetch_news_report,
)
from tradingagents.reporting import write_report_tree

ISIN = "IE00B4L5Y983"
URL = "https://004246189700-jyjulianwong-ina-news-reports.s3.eu-west-2.amazonaws.com"
REPORT = "# Investment News Analysis AI — 2026-11-05\n\n## 1. Executive Summary\n\n- Oil fell."


def _reset_config():
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)


@pytest.fixture(autouse=True)
def _config_reset():
    _reset_config()
    yield
    _reset_config()


def _response(status, body=b""):
    return mock.Mock(status_code=status, content=body)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFetchNewsReport:
    def test_builds_the_dated_url_and_decodes_utf8(self):
        body = REPORT.encode("utf-8")
        with mock.patch.object(
            investment_news, "get_scrubbed", return_value=_response(200, body)
        ) as get:
            assert fetch_news_report(URL + "/", "2026-11-05") == REPORT
        assert get.call_args.args[0] == f"{URL}/reports/2026-11-05/report.md"

    @pytest.mark.parametrize("status", [403, 404])
    def test_missing_report_is_none(self, status):
        with mock.patch.object(investment_news, "get_scrubbed", return_value=_response(status)):
            assert fetch_news_report(URL, "2026-11-07") is None

    def test_empty_body_is_unavailable(self):
        with (
            mock.patch.object(investment_news, "get_scrubbed", return_value=_response(200, b"  ")),
            pytest.raises(InvestmentNewsUnavailableError),
        ):
            fetch_news_report(URL, "2026-11-05")

    def test_server_error_is_unavailable(self):
        with (
            mock.patch.object(
                investment_news, "get_scrubbed", side_effect=requests.HTTPError("500")
            ),
            pytest.raises(InvestmentNewsUnavailableError),
        ):
            fetch_news_report(URL, "2026-11-05")

    def test_blocked_network_surfaces_as_unavailable(self):
        with pytest.raises(InvestmentNewsUnavailableError):
            fetch_news_report(URL, "2026-11-05")


# ---------------------------------------------------------------------------
# Lookback
# ---------------------------------------------------------------------------


def _published(*dates):
    """A fetch that has a report for ``dates`` only, recording what it was asked for."""
    return mock.Mock(side_effect=lambda _url, d: f"report {d}" if d in dates else None)


@pytest.mark.unit
class TestFindLatestReport:
    def test_uses_the_trade_dates_own_report(self):
        fetch = _published("2026-11-05", "2026-11-04")
        with mock.patch.object(fund_investment_news, "fetch_news_report", fetch):
            assert find_latest_report(URL, "2026-11-05", 5) == ("2026-11-05", "report 2026-11-05")

    def test_weekend_run_reads_fridays_report_without_asking_for_weekend_dates(self):
        fetch = _published("2026-10-30")  # Friday
        with mock.patch.object(fund_investment_news, "fetch_news_report", fetch):
            assert find_latest_report(URL, "2026-11-01", 5) == ("2026-10-30", "report 2026-10-30")
        asked = [c.args[1] for c in fetch.call_args_list]
        assert asked == ["2026-10-30"]

    def test_never_reads_a_report_after_the_trade_date(self):
        fetch = _published("2026-11-05")
        with mock.patch.object(fund_investment_news, "fetch_news_report", fetch):
            assert find_latest_report(URL, "2026-11-04", 5) is None
        assert all(c.args[1] <= "2026-11-04" for c in fetch.call_args_list)

    def test_future_trade_date_is_clamped_to_today(self):
        fetch = _published()
        with mock.patch.object(fund_investment_news, "fetch_news_report", fetch):
            find_latest_report(URL, "2999-01-01", 5)
        assert all(c.args[1] <= date.today().isoformat() for c in fetch.call_args_list)

    def test_outage_propagates(self):
        fetch = mock.Mock(side_effect=InvestmentNewsUnavailableError("down"))
        with (
            mock.patch.object(fund_investment_news, "fetch_news_report", fetch),
            pytest.raises(InvestmentNewsUnavailableError),
        ):
            find_latest_report(URL, "2026-11-05", 5)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRendering:
    def test_block_wraps_the_report_with_its_date(self):
        block = render_news_block("2026-11-05", "2026-11-05", REPORT)
        assert "INVESTMENT NEWS ANALYSIS AI REPORT (dated 2026-11-05)" in block
        assert REPORT in block
        assert "secondary to the analyst reports" in block

    def test_older_report_says_so(self):
        block = render_news_block("2026-10-30", "2026-11-02", REPORT)
        assert "latest published on or before 2026-11-02" in block

    def test_oversized_report_is_truncated(self):
        block = render_news_block("2026-11-05", "2026-11-05", "x" * 100_000)
        assert "[... report truncated ...]" in block
        assert len(block) < 61_000

    def test_instruction_is_empty_without_a_report(self):
        key = "investment_news_analysis_ai_report"
        assert get_investment_news_instruction({}) == ""
        assert get_investment_news_instruction(None) == ""
        assert get_investment_news_instruction({key: ""}) == ""
        assert get_investment_news_instruction({key: "X"}) == "\n\nX"

    def test_fetch_records_why_nothing_was_used(self):
        with mock.patch.object(fund_investment_news, "fetch_news_report", _published()):
            report, section = fetch_investment_news(URL, "2026-11-05", 5)
        assert report == ""
        assert "no report published in the 5 days up to 2026-11-05" in section

    def test_empty_url_turns_it_off(self):
        assert fetch_investment_news("", "2026-11-05", 5) == ("", "")


# ---------------------------------------------------------------------------
# Fund Analyst
# ---------------------------------------------------------------------------


def _fund_state(trade_date):
    return {
        "company_of_interest": ISIN,
        "asset_type": "stock",
        "messages": [],
        "trade_date": trade_date,
    }


def _run_fund_analyst(trade_date, fetch):
    set_config(
        {
            "isin_ticker_map_override": True,
            "isin_ticker_map": {ISIN: ["IWDA.L"]},
            "market_regime_api_url": "",
        }
    )
    with mock.patch.object(fund_investment_news, "fetch_news_report", fetch):
        return create_fund_analyst(mock.MagicMock())(_fund_state(trade_date))


@pytest.mark.unit
class TestFundAnalystNews:
    def test_fund_run_emits_the_report(self):
        result = _run_fund_analyst("2026-11-05", _published("2026-11-05"))
        assert "report 2026-11-05" in result["investment_news_analysis_ai_report"]
        # The fund report names the source without repeating the whole digest.
        assert f"{URL}/reports/2026-11-05/report.md" in result["fund_report"]
        assert "report 2026-11-05" not in result["fund_report"]
        # The analysts read instrument_context; the news must stay out of it.
        assert "INVESTMENT NEWS" not in result["instrument_context"]

    def test_historical_run_reads_its_own_dates_report(self):
        fetch = _published("2020-01-02")
        result = _run_fund_analyst("2020-01-02", fetch)
        assert "dated 2020-01-02" in result["investment_news_analysis_ai_report"]

    def test_outage_keeps_the_run_going(self):
        fetch = mock.Mock(side_effect=InvestmentNewsUnavailableError("timeout"))
        result = _run_fund_analyst("2026-11-05", fetch)
        assert result["fund_proxy_tickers"] == ["IWDA.L"]
        assert result["investment_news_analysis_ai_report"] == ""
        assert "unavailable for this run (timeout)" in result["fund_report"]

    def test_empty_url_turns_it_off(self):
        set_config({"investment_news_report_url": ""})
        fetch = _published("2026-11-05")
        result = _run_fund_analyst("2026-11-05", fetch)
        fetch.assert_not_called()
        assert result["investment_news_analysis_ai_report"] == ""
        assert "investment news" not in result["fund_report"].lower()

    def test_ordinary_ticker_is_still_a_no_op(self):
        fetch = _published("2026-11-05")
        with mock.patch.object(fund_investment_news, "fetch_news_report", fetch):
            state = {**_fund_state("2026-11-05"), "company_of_interest": "AAPL"}
            assert create_fund_analyst(mock.MagicMock())(state) == {}
        fetch.assert_not_called()


# ---------------------------------------------------------------------------
# Debate prompts
# ---------------------------------------------------------------------------


def _debate_state(news_report):
    return {
        "company_of_interest": ISIN,
        "asset_type": "stock",
        "trade_date": "2026-11-05",
        "instrument_context": "instrument",
        "market_report": "m",
        "sentiment_report": "s",
        "news_report": "n",
        "fundamentals_report": "f",
        "fund_proxy_tickers": ["IWDA.L"],
        "investment_news_analysis_ai_report": news_report,
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
    def test_researchers_see_the_report(self, factory):
        llm = mock.MagicMock()
        llm.invoke.return_value = mock.Mock(content="argument")
        factory(llm)(_debate_state("NEWS-BLOCK-123"))
        assert "NEWS-BLOCK-123" in _prompt_text(llm)

    @pytest.mark.parametrize("factory", [create_bull_researcher, create_bear_researcher])
    def test_researchers_unchanged_without_it(self, factory):
        llm = mock.MagicMock()
        llm.invoke.return_value = mock.Mock(content="argument")
        factory(llm)(_debate_state(""))
        assert "INVESTMENT NEWS" not in _prompt_text(llm)

    def test_research_manager_sees_the_report(self):
        llm = mock.MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError
        llm.invoke.return_value = mock.Mock(content="Rating: Hold")
        create_research_manager(llm)(_debate_state("NEWS-BLOCK-123"))
        assert "NEWS-BLOCK-123" in _prompt_text(llm)


# ---------------------------------------------------------------------------
# Saved report
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_saved_report_includes_the_news_file(tmp_path):
    state = {"fund_report": "fund", "investment_news_analysis_ai_report": "NEWS-BLOCK-123"}
    complete = write_report_tree(state, ISIN, tmp_path, html=False)
    saved = tmp_path / "1_analysts" / "investment_news.md"
    assert saved.read_text(encoding="utf-8") == "NEWS-BLOCK-123"
    assert "### Investment News Analysis AI" in complete.read_text(encoding="utf-8")
