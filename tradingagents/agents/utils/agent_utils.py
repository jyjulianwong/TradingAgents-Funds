import functools
import logging
import re
from collections.abc import Mapping
from typing import Any

import yfinance as yf
from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import get_stock_data
from tradingagents.agents.utils.fund_data_tools import get_fund_fact_sheet
from tradingagents.agents.utils.fundamental_data_tools import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
)
from tradingagents.agents.utils.macro_data_tools import get_macro_indicators
from tradingagents.agents.utils.market_data_validation_tools import get_verified_market_snapshot
from tradingagents.agents.utils.news_data_tools import (
    get_global_news,
    get_insider_transactions,
    get_news,
)
from tradingagents.agents.utils.prediction_markets_tools import get_prediction_markets
from tradingagents.agents.utils.symbol_search_tools import search_ticker_symbol
from tradingagents.agents.utils.technical_indicators_tools import get_indicators

# Public surface: the data tools are imported here so agents and the graph
# import them from one place, plus the instrument/language helpers defined below.
__all__ = [
    "get_stock_data",
    "get_indicators",
    "get_fund_fact_sheet",
    "search_ticker_symbol",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_news",
    "get_global_news",
    "get_insider_transactions",
    "get_macro_indicators",
    "get_prediction_markets",
    "get_verified_market_snapshot",
    "build_instrument_context",
    "resolve_instrument_identity",
    "resolve_isin_ticker_list",
    "is_isin",
    "get_instrument_context_from_state",
    "get_fund_analysis_instruction",
    "get_language_instruction",
    "get_autonomous_agent_instruction",  # TODO: Hotfix #0001
    "create_msg_delete",
]

logger = logging.getLogger(__name__)

# Matches the standard 12-character ISIN format: 2-letter country code,
# 9 alphanumeric characters, 1 numeric check digit.
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def is_isin(ticker: str) -> bool:
    """Return True if *ticker* looks like a 12-character ISIN, not a stock/crypto ticker."""
    return bool(_ISIN_RE.match(ticker.strip().upper()))


def resolve_isin_ticker_list(
    ticker: str, state: Mapping[str, Any] | None = None
) -> list[str]:
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


def get_fund_analysis_instruction(
    ticker: str, state: Mapping[str, Any] | None = None
) -> str:
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


# TODO: Hotfix #0001
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


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Applied to every agent whose output reaches the saved report —
    analysts, researchers, debaters, research manager, trader, and
    portfolio manager — so a non-English run produces a fully localized
    report rather than a mix of languages.
    """
    from tradingagents.dataflows.config import get_config

    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def _clean_identity_value(value: Any) -> str | None:
    """Return a trimmed string, or None for empty / placeholder-ish values."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.lower() in {"none", "n/a", "nan", "null"}:
        return None
    return cleaned


@functools.lru_cache(maxsize=256)
def resolve_instrument_identity(ticker: str) -> dict:
    """Resolve deterministic identity metadata (company name, sector, …) for a ticker.

    This exists to stop the pipeline from hallucinating a *different* company
    when a chart pattern suggests a different industry than the real one
    (#814): without a ground-truth name, the market analyst would pattern-match
    the price action to a narrative and invent an identity that then cascaded
    through every downstream agent.

    Best-effort by design: if yfinance is unavailable, rate-limited, or doesn't
    recognise the ticker, we return ``{}`` and the caller falls back to
    ticker-only context rather than failing before analysis starts. Cached so
    the lookup happens at most once per ticker per process.

    The symbol is normalized first (e.g. ``XAUUSD`` -> ``GC=F``) so identity
    resolves for the same instrument the price path actually fetches (#983).
    """
    from tradingagents.dataflows.symbol_utils import normalize_symbol

    try:
        info = yf.Ticker(normalize_symbol(ticker)).info or {}
    except Exception as exc:  # noqa: BLE001 — fail open, never block the run
        logger.debug("Could not resolve instrument identity for %s: %s", ticker, exc)
        return {}

    identity: dict[str, str] = {}
    company_name = _clean_identity_value(info.get("longName")) or _clean_identity_value(
        info.get("shortName")
    )
    if company_name:
        identity["company_name"] = company_name
    for source_key, target_key in (
        ("sector", "sector"),
        ("industry", "industry"),
        ("exchange", "exchange"),
        ("quoteType", "quote_type"),
    ):
        value = _clean_identity_value(info.get(source_key))
        if value:
            identity[target_key] = value
    return identity


def build_instrument_context(
    ticker: str,
    asset_type: str = "stock",
    identity: Mapping[str, str] | None = None,
    mapped_tickers: list[str] | None = None,
) -> str:
    """Describe the exact instrument so agents preserve identity and ticker.

    When ``identity`` is provided (resolved deterministically via
    :func:`resolve_instrument_identity`), the company name and business
    classification are injected so agents anchor to the real company rather
    than pattern-matching the price chart to a wrong one (#814).

    When ``mapped_tickers`` is provided the instrument is a fund identified by
    ISIN. A note is appended explaining that market and fundamentals reports
    contain data sections for each proxy, so downstream agents (researchers,
    risk debaters, trader, PM) know to treat proxy data as representative of
    the fund.
    """
    is_crypto = asset_type == "crypto"
    instrument_label = "asset" if is_crypto else "instrument"
    context = (
        f"The {instrument_label} to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`, `-USD`)."
    )

    details = []
    if identity:
        name = identity.get("company_name") or identity.get("name")
        if name:
            details.append(f"{'Name' if is_crypto else 'Company'}: {name}")
        sector, industry = identity.get("sector"), identity.get("industry")
        if sector and industry:
            details.append(f"Business classification: {sector} / {industry}")
        elif sector:
            details.append(f"Sector: {sector}")
        elif industry:
            details.append(f"Industry: {industry}")
        if identity.get("exchange"):
            details.append(f"Exchange: {identity['exchange']}")

    if details:
        context += (
            f" Resolved identity: {'; '.join(details)}. "
            "Do not substitute a different company or ticker unless a tool "
            "result explicitly disproves this resolved identity."
        )

    if is_crypto:
        context += (
            " Treat it as a crypto asset rather than a company, and do not "
            "assume company fundamentals are available."
        )

    if mapped_tickers:
        context += (
            f" This instrument is a fund identified by ISIN {ticker}. Because fund"
            f" vehicles do not report exchange-traded volume or corporate financial"
            f" statements, the following proxy tickers have been mapped as"
            f" representative underlying holdings: {', '.join(mapped_tickers)}."
            f" The market and fundamentals reports contain data sections for each"
            f" proxy. Treat data from these proxy tickers as representative of the"
            f" fund's performance and characteristics."
        )

    return context


def get_instrument_context_from_state(state: Mapping[str, Any]) -> str:
    """Return the instrument context for the current run.

    Prefers the identity-resolved context computed once at run start and
    stored on the state (see ``TradingAgentsGraph.resolve_instrument_context``).
    Falls back to a ticker-only context — with no network lookup — when the
    state was constructed without it (bare programmatic states, tests), so a
    consumer is never forced to make a yfinance call mid-graph.
    """
    context = state.get("instrument_context")
    if isinstance(context, str) and context.strip():
        return context
    return build_instrument_context(
        str(state["company_of_interest"]),
        state.get("asset_type", "stock"),
    )


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add a context-anchored placeholder.

        The placeholder must not be a bare ``"Continue"``: some
        OpenAI-compatible providers interpret that literally as the user task
        and produce output about the word "continue" instead of analysing the
        instrument (#888). Anchoring it to the resolved instrument context and
        date keeps the next analyst on-task even if the provider treats the
        placeholder as a standalone request.
        """
        messages = state["messages"]
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        instrument_context = get_instrument_context_from_state(state)
        trade_date = state.get("trade_date", "the requested date")
        placeholder = HumanMessage(
            content=(
                f"Proceed with your assigned analysis for this workflow. "
                f"{instrument_context} The analysis date is {trade_date}."
            )
        )
        return {"messages": removal_operations + [placeholder]}

    return delete_messages
