"""Fund (ISIN) prompt context, split out of ``context.py`` to keep upstream's file intact.

Everything here exists for the fork's fund support: recognising an ISIN, expanding
it to the Fund Analyst's proxy tickers, and the prompt notes that tell agents how
to read a fund. ``context.py`` re-exports these names, so existing imports work.
"""

import logging
import re
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)

# Matches the standard 12-character ISIN format: 2-letter country code,
# 9 alphanumeric characters, 1 numeric check digit.
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def is_isin(ticker: str) -> bool:
    """Return True if *ticker* looks like a 12-character ISIN, not a stock/crypto ticker."""
    return bool(_ISIN_RE.match(ticker.strip().upper()))


def resolve_isin_ticker_list(ticker: str, state: Mapping[str, Any] | None = None) -> list[str]:
    """Return the ordered list of symbols to analyse for a given ticker.

    For ordinary stock/crypto tickers, returns ``[ticker]``.

    For a fund ISIN, the Fund Analyst node (the graph's first node) resolves
    proxy tickers dynamically — via its ``get_fund_fact_sheet`` tool, with
    ``isin_ticker_map`` as a static backup — and stores the result in
    ``state["fund_proxy_tickers"]``. When ``state`` is passed and already
    carries that key, this returns ``[ticker] + state["fund_proxy_tickers"]``
    directly; the Fund Analyst has already applied its own fallback, so no
    further map lookup happens here. When ``state`` is omitted or the key is
    absent (pre-graph resolution, or a bare state built without running the
    Fund Analyst, e.g. in tests), this falls back to a direct
    ``isin_ticker_map`` lookup with a warning if the ISIN isn't listed.

    Index 0 is always the original ticker (or ISIN); indices 1+ are the
    resolved proxies. Each analyst slices as appropriate — the market and
    fundamentals analysts use the full list; the sentiment analyst passes the
    full list too, with the ISIN appearing as a labelled section that will
    typically show empty social-media results (correctly signalling that the
    fund is not discussed under its ISIN on retail platforms).
    """
    if not is_isin(ticker):
        return [ticker]

    if state is not None:
        fund_tickers = state.get("fund_proxy_tickers")
        if isinstance(fund_tickers, list):
            return [ticker] + list(fund_tickers)

    from tradingagents.dataflows.config import get_config

    isin_map = get_config().get("isin_ticker_map", {})
    mapped = isin_map.get(ticker.upper()) or isin_map.get(ticker)
    if mapped:
        return [ticker] + list(mapped)

    logger.warning(
        "resolve_isin_ticker_list: %r looks like an ISIN but has no entry in "
        "DEFAULT_CONFIG['isin_ticker_map']. Only the ISIN itself will be queried "
        "— volume and financial-statement data will likely be unavailable. "
        'Add a mapping to fix this, e.g. "%s": ["TICKER1", "TICKER2"].',
        ticker,
        ticker.upper(),
    )
    return [ticker]


def get_fund_analysis_instruction(ticker: str, state: Mapping[str, Any] | None = None) -> str:
    """Return fund-specific prompt instructions when *ticker* is an ISIN.

    Returns an empty string for non-ISIN tickers so it is safe to
    unconditionally append to any agent prompt.  When the ticker is an ISIN,
    the returned text corrects LLM misconceptions about UK open-ended
    investment companies (OEICs) / unit trusts that otherwise skew ratings
    toward SELL/UNDERWEIGHT due to structural data artefacts:

    - Zero trading volume on the ISIN is normal (NAV-priced, not exchange-traded)
      and must not be used as a liquidity or execution-risk signal.
    - Stop-loss orders, bid-ask spread, and slippage are inapplicable.
    - Missing corporate financial statements are expected for fund vehicles.
    - PE benchmarks should match the fund's underlying index, not a generic norm.
    - Proxy-ticker risks should inform sector/market context, not be imported as
      fund-level idiosyncratic risks.

    Pass ``state`` (any node has it) so the proxy tickers named here match
    the Fund Analyst's resolution instead of recomputing from the static map.
    """
    if not is_isin(ticker):
        return ""

    mapped = resolve_isin_ticker_list(ticker, state)
    proxy_tickers = mapped[1:]
    proxy_note = (
        (
            f" When proxy tickers ({', '.join(proxy_tickers)}) appear in the reports,"
            " use them for sector and market context only — do not attribute"
            " individual-stock risks (e.g. a single company's regulatory probe or"
            " earnings miss) directly to the diversified fund vehicle."
        )
        if proxy_tickers
        else ""
    )

    return (
        "\n\n**FUND INSTRUMENT NOTICE — this ticker is a UK OEIC / unit trust:**"
        " The following are structural characteristics of this instrument type,"
        " not warning signs. Factor them into your analysis accordingly."
        "\n- **Zero trading volume is normal and must not be used as a negative"
        " signal.** OEICs do not trade on a secondary exchange; investors subscribe"
        " and redeem directly through the fund manager at the next published NAV."
        " Zero volume does NOT indicate illiquidity, an untradeable asset, or"
        " execution risk."
        "\n- **Stop-loss orders, slippage, and bid-ask spread are inapplicable.**"
        " Redemptions settle at the next available NAV price (typically T+3"
        " business days). Risk management relies on allocation sizing and NAV"
        " discount monitoring, not exchange-order mechanics."
        "\n- **Missing income statements, balance sheets, and cash-flow statements"
        " are expected.** Fund vehicles publish NAV, factsheets, and portfolio"
        " holdings rather than corporate financial accounts."
        "\n- **Use an index-appropriate PE benchmark.** For a fund tracking the"
        " S&P 500, compare its PE to the historical S&P 500 PE range"
        " (approximately 18–28× in recent market cycles), not to a generic"
        " single-stock norm of 16-20x." + proxy_note
    )


def get_autonomous_agent_instruction() -> str:
    """Return a prompt instruction reminding tool-calling agents to proceed autonomously.

    Prevents the LLM from stalling the tool-calling loop by emitting a
    user-facing question on its first turn.  Appended to every analyst's
    system message alongside ``get_language_instruction()``.
    """
    return (
        " You are operating in a fully automated pipeline with no human in the loop."
        " Never ask the user for clarification or additional input."
        " If any parameter is ambiguous, choose the most sensible default and proceed immediately with the tool calls suggested in the system message."
    )


def fund_instrument_note(ticker: str, mapped_tickers: list[str] | None) -> str:
    """The sentence ``build_instrument_context`` appends when the instrument is a fund.

    ``mapped_tickers`` are the proxy tickers resolved for the fund's ISIN; empty or
    None (an ordinary instrument) gives an empty string.
    """
    if not mapped_tickers:
        return ""
    return (
        f" This instrument is a fund identified by ISIN {ticker}. Because fund"
        f" vehicles do not report exchange-traded volume or corporate financial"
        f" statements, the following proxy tickers have been mapped as"
        f" representative underlying holdings: {', '.join(mapped_tickers)}."
        f" The market and fundamentals reports contain data sections for each"
        f" proxy. Treat data from these proxy tickers as representative of the"
        f" fund's performance and characteristics."
    )


def get_symbol_argument_instruction(ticker: str, state: Mapping[str, Any] | None = None) -> str:
    """Prompt sentence telling a fund run's analyst how to pick a symbol in the data tools.

    Empty for an ordinary ticker, or a fund with no resolved proxies, so it is safe to
    append to any analyst prompt. See ``fund_tools.py`` for the tools it refers to.
    """
    symbols = resolve_isin_ticker_list(ticker, state) if is_isin(ticker) else []
    if len(symbols) < 2:
        return ""
    return (
        " Every per-instrument data tool takes an optional `symbol` argument: pass one of"
        f" {', '.join(f'`{s}`' for s in symbols)} to get that symbol's data, and omit it for"
        f" the fund `{ticker}` itself. Any other symbol is refused."
    )
