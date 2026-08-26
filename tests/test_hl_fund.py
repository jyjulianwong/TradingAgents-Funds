"""Tests for the Hargreaves Lansdown fund-factsheet vendor.

The HTML fixture below is a trimmed-down but structurally faithful copy of
a real HL factsheet page (verified live against
https://www.hl.co.uk/funds/fund-discounts,-prices--and--factsheets/search-results/BJS8SF9
— Fidelity Index UK (Class P) Accumulation, SEDOL BJS8SF9, ISIN
GB00BJS8SF95) — same tag structure, table `summary` attributes, and CSS
classes the parser selects on.
"""

from unittest import mock

import pytest
import requests

from tradingagents.dataflows import hl_fund
from tradingagents.dataflows.errors import NoMarketDataError

ISIN = "GB00BJS8SF95"
SEDOL = "BJS8SF9"

_SAMPLE_HTML = """
<html>
<head><title>Fidelity Index UK (Class P) Accumulation Fund Price &amp; Information</title></head>
<body>
<div id="security-price">
  <div class="price">
    <span class="price-label">Sell:</span><span class="bid price-divide">254.04p</span>
    <span class="price-label">Buy:</span><span class="ask price-divide">254.04p</span>
  </div>
</div>
<table>
  <tr><th class="align-left">Fund size</th><td>&pound;4,925 million</td></tr>
  <tr><th class="align-left">Number of holdings:</th><td>545</td></tr>
  <tr><th class="align-left">Fund type</th><td class="fs-line-reduce">OEIC</td></tr>
</table>
<table class="factsheet-table" summary="Top 10 holdings">
  <thead><th>Security</th><th>Weight</th></thead>
  <tbody>
    <tr><td>HSBC HOLDINGS</td><td class="align-right">8.54%</td></tr>
    <tr><td><a href="/shares/shares-search-results/B1XZS82" title="View the factsheet for ASTRAZENECA">ASTRAZENECA</a></td><td class="align-right">7.48%</td></tr>
    <tr><td>SHELL</td><td class="align-right">5.62%</td></tr>
  </tbody>
</table>
<table class="factsheet-table" summary="Top 10 sectors">
  <thead><tr><th>Sector</th><th>Weight</th></tr></thead>
  <tbody>
    <tr><td class="align-left">Banks</td><td class="align-right">16.71%</td></tr>
    <tr><td class="align-left">Pharmaceuticals &amp; Biotechnology</td><td class="align-right">11.47%</td></tr>
  </tbody>
</table>
<table class="factsheet-table" summary="Top 10 countries">
  <thead><tr><th>Country</th><th>Weight</th></tr></thead>
  <tbody>
    <tr><td class="align-left">United Kingdom</td><td class="align-right">89.88%</td></tr>
  </tbody>
</table>
</body>
</html>
"""

_NOT_FOUND_HTML = "<html><head><title>Page cannot be found | Hargreaves Lansdown</title></head></html>"


def _response(status_code: int, text: str) -> mock.Mock:
    resp = mock.Mock()
    resp.status_code = status_code
    resp.text = text
    return resp


@pytest.mark.unit
class TestSedolFromGbIsin:
    def test_gb00_isin_extracts_sedol(self):
        assert hl_fund._sedol_from_gb_isin(ISIN) == SEDOL

    def test_lowercase_isin_still_extracts(self):
        assert hl_fund._sedol_from_gb_isin(ISIN.lower()) == SEDOL

    def test_non_gb_isin_returns_none(self):
        assert hl_fund._sedol_from_gb_isin("IE00B4L5Y983") is None

    def test_ordinary_ticker_returns_none(self):
        assert hl_fund._sedol_from_gb_isin("AAPL") is None


@pytest.mark.unit
class TestGetFundHoldings:
    def test_non_gb_isin_makes_no_network_call(self):
        with mock.patch.object(hl_fund.requests, "get") as get_mock, \
                pytest.raises(NoMarketDataError):
            hl_fund.get_fund_holdings("IE00B4L5Y983")
        get_mock.assert_not_called()

    def test_successful_scrape_formats_all_sections(self):
        with mock.patch.object(hl_fund.requests, "get", return_value=_response(200, _SAMPLE_HTML)):
            result = hl_fund.get_fund_holdings(ISIN)

        assert "Fidelity Index UK (Class P) Accumulation" in result
        assert ISIN in result
        assert "sell 254.04p, buy 254.04p" in result
        assert "£4,925 million" in result
        assert "HSBC HOLDINGS | 8.54%" in result
        assert "ASTRAZENECA | 7.48%" in result
        assert "Banks | 16.71%" in result
        assert "United Kingdom | 89.88%" in result
        # No ticker column exists in HL's data — the LLM must be told so.
        assert "no exchange" in result.lower()

    def test_request_uses_sedol_derived_url(self):
        with mock.patch.object(
            hl_fund.requests, "get", return_value=_response(200, _SAMPLE_HTML)
        ) as get_mock:
            hl_fund.get_fund_holdings(ISIN)
        called_url = get_mock.call_args[0][0]
        assert called_url.endswith(f"/{SEDOL}")

    def test_404_raises_no_market_data_error(self):
        with mock.patch.object(hl_fund.requests, "get", return_value=_response(404, _NOT_FOUND_HTML)), \
                pytest.raises(NoMarketDataError):
            hl_fund.get_fund_holdings(ISIN)

    def test_non_200_non_404_raises_no_market_data_error(self):
        with mock.patch.object(hl_fund.requests, "get", return_value=_response(503, "")), \
                pytest.raises(NoMarketDataError):
            hl_fund.get_fund_holdings(ISIN)

    def test_network_exception_raises_no_market_data_error(self):
        with mock.patch.object(
            hl_fund.requests, "get", side_effect=requests.ConnectionError("boom")
        ), pytest.raises(NoMarketDataError):
            hl_fund.get_fund_holdings(ISIN)

    def test_page_with_no_holdings_or_sectors_raises_no_market_data_error(self):
        empty_html = "<html><head><title>Some Fund Price &amp; Information</title></head></html>"
        with mock.patch.object(hl_fund.requests, "get", return_value=_response(200, empty_html)), \
                pytest.raises(NoMarketDataError):
            hl_fund.get_fund_holdings(ISIN)
