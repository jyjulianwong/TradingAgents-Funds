"""Fork-only vendor routing entries for fund support (kept out of ``router.py``).

``router.py`` merges these tables into its own with one tagged line each:
the fund fact-sheet, ticker-symbol-search and earnings-outlook tool categories,
which of them are optional, and the vendor implementations behind each tool.
"""

from tradingagents.dataflows.vendors.alpha_vantage import (
    get_symbol_matches as get_alpha_vantage_symbol_matches,
)
from tradingagents.dataflows.vendors.alpha_vantage.earnings import (
    get_earnings_outlook as get_alpha_vantage_earnings_outlook,
)
from tradingagents.dataflows.vendors.hl_fund import get_fund_holdings as get_hl_fund_holdings
from tradingagents.dataflows.vendors.mstarpy_fund import (
    get_fund_holdings as get_mstarpy_fund_holdings,
)
from tradingagents.dataflows.vendors.yahoo.earnings import (
    get_earnings_outlook as get_yfinance_earnings_outlook,
)

FUND_TOOLS_CATEGORIES = {
    "fund_fact_sheet_data": {
        "description": "Fund holdings / fact sheet data, keyed by ISIN",
        "tools": [
            "get_fund_fact_sheet",
        ],
    },
    "ticker_symbol_search": {
        "description": "Ticker/company-name symbol lookup, used to verify Fund Analyst proxy tickers",
        "tools": [
            "search_ticker_symbol",
        ],
    },
    # FORK(funds): earnings-outlook
    "earnings_outlook": {
        "description": "Forward earnings estimates, revisions, and upcoming earnings dates",
        "tools": [
            "get_earnings_outlook",
        ],
    },
}

# fund_fact_sheet_data joins this set for a different reason: mstarpy drives a
# real Chrome session and can legitimately be unavailable in headless/CI
# environments (see mstarpy_fund.py). The Fund Analyst node's isin_ticker_map
# fallback is the real safety net; this just keeps a vendor outage from ever
# raising instead of degrading to a sentinel the node checks for.
# ticker_symbol_search is optional for the same reason as fund_fact_sheet_data:
# it's a best-effort check the Fund Analyst can simply skip (no ALPHA_VANTAGE_API_KEY,
# rate-limited, network error) without that ever blocking a run — see
# fund_analyst.py's _verify_ticker, which treats an unreachable vendor as "no
# verdict" rather than a failure.
# earnings_outlook is optional like macro_data: flavour for the Fundamentals
# Analyst, and an ETF/index proxy ticker has no earnings coverage at all.
# FORK(funds): fund
FUND_OPTIONAL_CATEGORIES = {
    "fund_fact_sheet_data",
    "ticker_symbol_search",
    "earnings_outlook",
}

FUND_VENDOR_METHODS = {
    # fund_fact_sheet_data — additional providers plug in here without
    # touching the Fund Analyst node or the tool. "hl" (Hargreaves Lansdown,
    # HTML scrape) only covers GB00-domiciled ISINs and declines everything
    # else instantly (no network call); "mstarpy" (Morningstar via Selenium)
    # covers any ISIN globally but is slower and Chrome-dependent. Default
    # chain tries hl first — see default_config.py.
    "get_fund_fact_sheet": {
        "mstarpy": get_mstarpy_fund_holdings,
        "hl": get_hl_fund_holdings,
    },
    # ticker_symbol_search — Alpha Vantage only for now; additional providers
    # (e.g. a second symbol-lookup API) can plug in here later the same way
    # fund_fact_sheet_data grew a second vendor.
    "search_ticker_symbol": {
        "alpha_vantage": get_alpha_vantage_symbol_matches,
    },
    # earnings_outlook  # FORK(funds): earnings-outlook
    "get_earnings_outlook": {
        "yfinance": get_yfinance_earnings_outlook,
        "alpha_vantage": get_alpha_vantage_earnings_outlook,
    },
}
