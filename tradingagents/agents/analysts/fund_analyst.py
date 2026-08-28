"""Fund Analyst — resolves fund-ISIN tickers to exchange-traded proxies.

Runs as the graph's very first node (see ``GraphSetup``). For an ordinary
stock/crypto ticker it is a no-op: ``is_isin`` returns False and the node
returns an empty state update immediately, so nothing downstream changes.

For a fund ISIN, it tries to dynamically derive proxy tickers from the
fund's actual holdings (via the ``get_fund_fact_sheet`` tool, backed by
Morningstar through ``mstarpy``), and only falls back to the static
``isin_ticker_map`` in ``default_config.py`` when that fails or comes back
empty. That fallback decision is made in plain Python, not by the LLM — a
tool failure (network error, ISIN not covered, no Chrome available for the
mstarpy scrape) is a fact, not a judgment call, so it should not depend on
model behaviour to detect correctly.

The resolved tickers are written to ``state["fund_proxy_tickers"]`` and also
baked into a refreshed ``state["instrument_context"]`` (overwriting the
map-only version ``TradingAgentsGraph.resolve_instrument_context`` seeds
before the graph starts), so every downstream node — analysts, researchers,
debaters, trader, portfolio manager — sees the same, dynamically-resolved
proxy list without recomputing it.
"""

from __future__ import annotations

import logging

from tradingagents.agents.schemas import FundHoldingsAnalysis
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_fund_fact_sheet,
    is_isin,
    resolve_instrument_identity,
    resolve_isin_ticker_list,
)
from tradingagents.agents.utils.structured import NO_EXTERNAL_TOOLS, bind_structured

logger = logging.getLogger(__name__)

# Sentinel prefixes route_to_vendor uses for a vendor that produced no usable
# data (see dataflows/interface.py). Checked here, in Python, rather than
# left for the LLM to notice — the fallback-or-not decision must be
# deterministic (a network/vendor failure is a fact, not a judgment call).
_NO_DATA_PREFIXES = ("NO_DATA_AVAILABLE", "DATA_UNAVAILABLE")


def _fetch_fact_sheet(isin: str) -> str | None:
    """Return the fact-sheet text, or None if no vendor had usable data."""
    try:
        text = get_fund_fact_sheet.func(isin)
    except Exception as exc:  # noqa: BLE001 — any failure -> deterministic fallback
        logger.warning("Fund Analyst: get_fund_fact_sheet failed for %r: %s", isin, exc)
        return None
    if text.startswith(_NO_DATA_PREFIXES):
        logger.info("Fund Analyst: no fact-sheet data for %r: %s", isin, text)
        return None
    return text


def _build_prompt(isin: str, fact_sheet: str) -> list[dict[str, str]]:
    system = (
        "You are a fund analyst. Below is a fact sheet listing the largest "
        f"holdings (by weight) of the fund identified by ISIN {isin}. Select a "
        "short list of exchange-traded proxy tickers that downstream analysts "
        "can pull real price, volume, and fundamentals data for, standing in "
        "for this fund — which, as an OEIC/ETF, typically has no tradeable "
        "volume or corporate financial statements of its own.\n\n"
        "Selection rules:\n"
        "- If the fact sheet gives an explicit ticker/symbol per holding, you "
        "may pick verbatim from that column.\n"
        "- If the fact sheet lists holdings by company name only (no ticker "
        "column — some providers show name + SEDOL/ISIN instead of a "
        "ticker), you may identify the ticker yourself from your own "
        "knowledge of the company. Only do this when you are confident which "
        "exchange listing is meant (e.g. a well-known large-cap with one "
        "obvious primary listing); if a name is ambiguous, obscure, or "
        "multi-listed and you are not sure, leave it out rather than "
        "guessing.\n"
        "- You are not limited to the fund's literal current holdings. If a "
        "sector, industry, thematic, or index ticker/ETF would be a more "
        "representative signal of the fund's overall exposure and likely "
        "future trends than its individual top holdings — for example the "
        "fund is broadly diversified with no single dominant position, or "
        "its stated sector/theme says more about where its intrinsic value "
        "is headed than today's largest holding does — prefer that broader "
        "ticker instead, or alongside the holdings-derived ones. This is a "
        "judgment call in service of what will be most useful to the "
        "downstream analysts and trader forming a view on the fund: pick "
        "whichever tickers, holding-derived or thematic, will best inform "
        "their read on this fund's future performance. Any such substitution "
        "must still be a real, currently-traded, well-known ticker you are "
        "genuinely confident about — never fabricate one — and explain the "
        "choice in your rationale.\n"
        "- Findability is a narrow, last-resort tie-breaker, not a general "
        "preference — representativeness always comes first. Downstream News "
        "and Sentiment analysts search the market by ticker, so a holding "
        "that is genuinely obscure (a micro-cap or niche name with "
        "essentially no news or social-media footprint of its own) is a weak "
        "signal source regardless of how accurately it represents the fund. "
        "Only in that narrow case may you swap it for a well-known large-cap "
        "peer, sector leader, or sector/index ETF that still fairly "
        "represents the same exposure. A holding does NOT need to be a "
        "household name to be a valid pick — an accurate, moderately-covered "
        "holding should stay as-is. Do not default to the same handful of "
        "famous mega-cap or broad-index tickers across many different funds "
        "just because they are well-known and always discoverable; that "
        "defeats the purpose of fund-specific analysis and makes unrelated "
        "funds look artificially correlated. If in doubt, keep the fund's "
        "own holding.\n"
        "- Aim for 3 to 5 tickers, ordered by relevance, and never return "
        "more than 5. Fewer than 3 is fine when the fund is narrow or "
        "concentrated and that many distinct representative tickers genuinely "
        "don't exist — for a broad, diversified fund, a sector/index proxy "
        "per the rule above may serve better than any single holding.\n"
        "- If nothing usable can be identified (e.g. holdings are entirely "
        "bonds/cash and no sector/thematic proxy is a good fit either), "
        "return an empty list.\n"
        f"- {NO_EXTERNAL_TOOLS}\n\n"
        f"Fact sheet:\n{fact_sheet}"
    )
    return [{"role": "system", "content": system}]


def _render_fund_report(
    isin: str, source: str, proxy_tickers: list[str], rationale: str, fact_sheet: str | None
) -> str:
    lines = [
        f"**Instrument**: `{isin}` (fund ISIN)",
        f"**Proxy source**: {source}",
        f"**Proxy tickers**: {', '.join(proxy_tickers) if proxy_tickers else 'none found'}",
    ]
    if rationale:
        lines.extend(["", f"**Rationale**: {rationale}"])
    if fact_sheet:
        lines.extend(["", "**Fact sheet (mstarpy)**:", fact_sheet])
    return "\n".join(lines)


def create_fund_analyst(llm):
    """Create the Fund Analyst node for the trading graph."""
    structured_llm = bind_structured(llm, FundHoldingsAnalysis, "Fund Analyst")

    def fund_analyst_node(state):
        ticker = state["company_of_interest"]
        if not is_isin(ticker):
            return {}

        fact_sheet = _fetch_fact_sheet(ticker)

        proxy_tickers: list[str] = []
        rationale = ""
        if fact_sheet is not None and structured_llm is not None:
            try:
                result = structured_llm.invoke(_build_prompt(ticker, fact_sheet))
                if result is not None:
                    proxy_tickers = result.proxy_tickers
                    rationale = result.rationale
            except Exception as exc:  # noqa: BLE001 — fall through to static fallback
                logger.warning(
                    "Fund Analyst: structured synthesis failed for %r: %s", ticker, exc
                )

        if proxy_tickers:
            source = "mstarpy fund holdings"
        else:
            # Deterministic fallback: the static map is the backup, not the
            # primary path. resolve_isin_ticker_list(ticker) with no state
            # arg does exactly this lookup.
            proxy_tickers = resolve_isin_ticker_list(ticker)[1:]
            source = "isin_ticker_map fallback" if proxy_tickers else "none"

        identity = resolve_instrument_identity(ticker)
        instrument_context = build_instrument_context(
            ticker,
            state.get("asset_type", "stock"),
            identity,
            mapped_tickers=proxy_tickers or None,
        )

        return {
            "fund_proxy_tickers": proxy_tickers,
            "fund_proxy_source": source,
            "instrument_context": instrument_context,
            "fund_report": _render_fund_report(
                ticker, source, proxy_tickers, rationale, fact_sheet
            ),
        }

    return fund_analyst_node
