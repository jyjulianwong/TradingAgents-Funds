"""Hargreaves Lansdown fund-factsheet vendor, via HTML scraping.

Unlike ``mstarpy_fund.py`` (Selenium-driven Morningstar scraping), HL's fund
factsheet pages are plain server-rendered HTML — a normal HTTP GET returns
the full page, no browser needed. The page is at a human-readable URL slug,
not the ISIN, so lookup goes through HL's SEDOL-keyed alias instead:
``/funds/.../search-results/<SEDOL>`` redirects to the canonical page.

That only gets us as far as SEDOL, not ISIN, but for every UK-domiciled fund
(ISIN starting "GB00" — the case for every entry in this project's
``isin_ticker_map``) the SEDOL is embedded directly in the ISIN by
convention: ``GB00`` + 7-character SEDOL + 1 check digit. So for GB00 ISINs,
resolution to the factsheet URL needs no network round-trip or search step
at all. For any other ISIN (IE00, LU00, ...) there is no such convention and
no ISIN-keyed search endpoint HL exposes without hitting the ``/ajax/``
paths robots.txt disallows, so this vendor declines those immediately —
``mstarpy`` (a true ISIN-keyed lookup) is the vendor for those.

The page has no ticker symbols in its holdings table, only company names and
SEDOLs (HL's retail audience cares about company names, not tickers) — so
the Fund Analyst's prompt has to be able to work from a name-only holdings
list for this vendor, not just a ready-made ``ticker`` column.
"""

from __future__ import annotations

import logging
import re

import requests
from parsel import Selector

from .errors import NoMarketDataError

logger = logging.getLogger(__name__)

_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"
_BASE_URL = "https://www.hl.co.uk/funds/fund-discounts,-prices--and--factsheets/search-results"
_TIMEOUT = 15

_GB_ISIN_RE = re.compile(r"^GB00[A-Z0-9]{7}[0-9]$")

# Rows beyond this rank are dropped — matches mstarpy_fund.py's cap so
# fact sheets from either vendor read the same length to the LLM.
_MAX_ROWS = 25


def _sedol_from_gb_isin(isin: str) -> str | None:
    """Return the embedded SEDOL for a GB00 ISIN, or None if not GB-domiciled."""
    isin = isin.strip().upper()
    if not _GB_ISIN_RE.match(isin):
        return None
    return isin[4:11]


def _extract_table(sel: Selector, summary: str) -> list[tuple[str, str]]:
    """Return [(label, weight), ...] rows from a `table[summary=...]` block."""
    rows = []
    for row in sel.css(f'table[summary="{summary}"] tbody tr'):
        cells = row.css("td")
        if len(cells) < 2:
            continue
        label = " ".join(t.strip() for t in cells[0].css("::text").getall() if t.strip())
        weight = " ".join(t.strip() for t in cells[1].css("::text").getall() if t.strip())
        if label and weight:
            rows.append((label, weight))
    return rows


def _extract_key_fact(sel: Selector, label: str) -> str | None:
    """Return the value text for a `<th>label</th><td>value</td>` row, or None."""
    td = sel.xpath(f'//th[contains(., "{label}")]/following-sibling::td[1]')
    text = " ".join(t.strip() for t in td.css("::text").getall() if t.strip())
    return text or None


def _format_factsheet(isin: str, sel: Selector) -> str:
    title = (sel.css("title::text").get() or "").strip()
    fund_name = re.sub(r"\s+Fund Price\s*&\s*Information$", "", title).strip() or isin

    sell = sel.css("span.bid::text").get()
    buy = sel.css("span.ask::text").get()

    holdings = _extract_table(sel, "Top 10 holdings")[:_MAX_ROWS]
    sectors = _extract_table(sel, "Top 10 sectors")[:_MAX_ROWS]
    countries = _extract_table(sel, "Top 10 countries")[:_MAX_ROWS]

    if not holdings and not sectors:
        raise NoMarketDataError(isin, isin, "page loaded but no holdings/sector data found")

    lines = [
        f"**Fund fact sheet for {fund_name} (ISIN {isin}) — Hargreaves Lansdown**",
        "Data retrieved live from hl.co.uk",
    ]
    if sell or buy:
        lines.append(f"**Price**: sell {sell or '—'}, buy {buy or '—'}")
    for fact_label in ("Fund size", "Number of holdings", "Fund type"):
        value = _extract_key_fact(sel, fact_label)
        if value:
            lines.append(f"**{fact_label}**: {value}")
    lines.append("")

    if holdings:
        lines.append(
            "NOTE: HL lists holdings by company name and SEDOL only — no exchange "
            "ticker symbols are shown. Identify the ticker for each name yourself; "
            "if you are not confident which ticker a name refers to, omit it rather "
            "than guessing."
        )
        lines.append("")
        lines.append("Top 10 holdings:")
        lines.append("")
        lines.append("security_name | weighting_pct")
        lines.append("------------- | -------------")
        for name, weight in holdings:
            lines.append(f"{name} | {weight}")
        lines.append("")

    if sectors:
        lines.append("Top 10 sectors:")
        lines.append("")
        lines.append("sector | weighting_pct")
        lines.append("------ | -------------")
        for name, weight in sectors:
            lines.append(f"{name} | {weight}")
        lines.append("")

    if countries:
        lines.append("Top 10 countries:")
        lines.append("")
        lines.append("country | weighting_pct")
        lines.append("------- | -------------")
        for name, weight in countries:
            lines.append(f"{name} | {weight}")

    return "\n".join(lines).rstrip()


def get_fund_holdings(isin: str) -> str:
    """Fetch a fund's factsheet from Hargreaves Lansdown, keyed by ISIN.

    Only handles UK-domiciled ("GB00...") ISINs, since the SEDOL->URL
    resolution this vendor relies on only holds for those; any other ISIN
    raises ``NoMarketDataError`` immediately (no network call), so a
    multi-vendor chain (``fund_fact_sheet_data: "hl,mstarpy"``) falls
    straight through to a real ISIN-keyed vendor without wasted latency.
    """
    sedol = _sedol_from_gb_isin(isin)
    if sedol is None:
        raise NoMarketDataError(
            isin, isin, "not a GB00 ISIN — HL lookup only covers UK-domiciled funds"
        )

    url = f"{_BASE_URL}/{sedol}"
    try:
        response = requests.get(url, headers={"User-Agent": _UA}, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        logger.warning("HL fund lookup failed for %r (%s): %s", isin, sedol, exc)
        raise NoMarketDataError(isin, isin, str(exc)) from exc

    if response.status_code == 404:
        raise NoMarketDataError(isin, isin, f"no HL factsheet for SEDOL {sedol}")
    if response.status_code != 200:
        raise NoMarketDataError(
            isin, isin, f"HL returned HTTP {response.status_code} for SEDOL {sedol}"
        )

    return _format_factsheet(isin, Selector(response.text))
