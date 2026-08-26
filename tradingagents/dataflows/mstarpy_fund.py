"""Morningstar fund-holdings vendor, via the ``mstarpy`` scraping library.

``mstarpy`` has no official Morningstar API key; it drives a real Chrome
session (Selenium) once per process to clear Morningstar's bot-detection
challenge, then reuses that session's cookies for subsequent HTTP calls. Two
practical consequences for callers:

- The Chrome launch is **not headless by default** (mstarpy leaves
  ``--headless`` commented out in its own browser options). It crashes on any
  display-less server/CI/container unless the environment sets
  ``SELENIUM_CHROME_FLAGS``, e.g.
  ``SELENIUM_CHROME_FLAGS="--headless=new --no-sandbox --disable-dev-shm-usage --disable-gpu"``.
- The first call in a process is slow (browser launch + an ~8s settle delay
  mstarpy hardcodes for the anti-bot JS). The session is cached at module
  level (see ``_get_session``) so only the *first* call in a process pays
  that cost.

Both failure modes above (no browser available, WAF change, network error,
ISIN not found) are surfaced as ``NoMarketDataError`` so the routing layer
treats them exactly like any other vendor's "no data" case — the Fund
Analyst node's static ``isin_ticker_map`` fallback is what makes this vendor
safe to depend on even where Chrome cannot run.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from .errors import NoMarketDataError

logger = logging.getLogger(__name__)

# One Selenium-backed session per process. Constructing it launches Chrome, so
# it is created lazily on first use and reused across calls/ISINs instead of
# relaunching a browser per lookup. mstarpy's session already refreshes its
# own cookies internally on a WAF challenge (see MorningstarSession.request),
# so a long-lived cached session is expected usage, not a workaround.
_session = None

# Holdings rows beyond this rank are dropped from the formatted output — a
# fund can hold hundreds of positions and only the largest are relevant for
# picking representative proxy tickers.
_MAX_HOLDINGS_ROWS = 25


def _get_session():
    global _session
    if _session is None:
        import mstarpy

        _session = mstarpy.MorningstarSession()
    return _session


def _format_holdings(isin: str, fund_name: str, holdings: pd.DataFrame) -> str:
    total = len(holdings)
    if "weighting" in holdings.columns:
        holdings = holdings.sort_values("weighting", ascending=False)
    top = holdings.head(_MAX_HOLDINGS_ROWS)

    lines = [
        f"# Fund holdings for {fund_name} (ISIN {isin})",
        f"# Total holdings: {total} (showing top {len(top)} by weight)",
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "ticker | security_name | weighting_pct",
        "------ | ------------- | -------------",
    ]
    for _, row in top.iterrows():
        ticker = str(row.get("ticker") or "").strip() or "—"
        name = str(row.get("securityName") or "").strip() or "—"
        weighting = row.get("weighting")
        weighting_fmt = f"{weighting:.2f}" if isinstance(weighting, (int, float)) else "—"
        lines.append(f"{ticker} | {name} | {weighting_fmt}")

    return "\n".join(lines)


def get_fund_holdings(isin: str) -> str:
    """Fetch a fund's top holdings from Morningstar, keyed by ISIN.

    Returns a formatted text table (ticker, security name, weight) suitable
    for an LLM to read and reason over. Raises ``NoMarketDataError`` for any
    failure — ISIN not recognised by Morningstar, the scraping session
    couldn't be established (no Chrome, WAF change, network error), or the
    fund has no holdings data — so the router (and the Fund Analyst node)
    treat it uniformly as "no data from this vendor".
    """
    import mstarpy

    try:
        session = _get_session()
        fund = mstarpy.Funds(term=isin, session=session)
        holdings = fund.holdings("all")
    except Exception as exc:  # noqa: BLE001 — any failure mode -> typed no-data
        logger.warning("mstarpy fund lookup failed for %r: %s", isin, exc)
        raise NoMarketDataError(isin, isin, str(exc)) from exc

    if holdings is None or holdings.empty:
        raise NoMarketDataError(isin, isin, "fund found but returned no holdings")

    fund_name = getattr(fund, "name", isin)
    return _format_holdings(isin, fund_name, holdings)
