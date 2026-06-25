"""Sentiment analyst — multi-source sentiment analysis for a target ticker.

Previously named ``social_media_analyst``. Renamed and redesigned because
the old version had a prompt that demanded social-media analysis but the
only tool available was Yahoo Finance news — which led LLMs to fabricate
Reddit/X/StockTwits content under prompt pressure (verified live).

The redesigned agent pre-fetches three complementary data sources before
the LLM is invoked and injects them into the prompt as structured blocks:

  1. News headlines     — Yahoo Finance (institutional framing)
  2. StockTwits messages — retail-trader posts indexed by cashtag, with
                           user-labeled Bullish/Bearish sentiment tags
  3. Reddit posts        — r/wallstreetbets, r/stocks, r/investing

The agent does not use tool-calling; the data is in the prompt from
turn 0. Output uses the structured-output pattern (json_schema for
OpenAI/xAI, response_schema for Gemini, tool-use for Anthropic), falling
back to free-text generation for providers that lack native support, so
the sentiment header (band + score + confidence) is deterministic across
runs and providers instead of free-form per-model prose.

See: https://github.com/TauricResearch/TradingAgents/issues/557
See: https://github.com/TauricResearch/TradingAgents/issues/796
"""

import logging
import re
from datetime import datetime, timedelta

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.schemas import SentimentReport, render_sentiment_report
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_news,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.dataflows.reddit import fetch_reddit_posts
from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages


logger = logging.getLogger(__name__)

# Matches the standard 12-character ISIN format: 2-letter country code,
# 9 alphanumeric characters, 1 numeric check digit.
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def _resolve_sentiment_tickers(ticker: str) -> list[str]:
    """Return the list of tickers to use for sentiment data fetching.

    For ordinary stock/crypto tickers this is simply ``[ticker]``. When the
    input looks like an ISIN (fund identifier), the function checks
    ``DEFAULT_CONFIG['isin_ticker_map']`` for a user-defined mapping:

    - If a mapping exists, the mapped tickers are returned so that
      StockTwits / Reddit / news fetches target symbols people actually
      discuss on social platforms.
    - If no mapping exists, a ``WARNING`` is logged and ``[ticker]`` is
      returned unchanged (the ISIN will typically yield empty results from
      all three sentiment sources).
    """
    if not _ISIN_RE.match(ticker.upper()):
        return [ticker]

    from tradingagents.dataflows.config import get_config

    isin_map = get_config().get("isin_ticker_map", {})
    mapped = isin_map.get(ticker.upper()) or isin_map.get(ticker)
    if mapped:
        return list(mapped)

    logger.warning(
        "Sentiment Analyst: %r looks like an ISIN but has no entry in "
        "DEFAULT_CONFIG['isin_ticker_map']. Searching as-is — results will "
        "likely be empty. Add a mapping to fix this, e.g. "
        '"%s": ["TICKER1", "TICKER2"].',
        ticker,
        ticker.upper(),
    )
    return [ticker]


def _fetch_multi_ticker_blocks(
    isin: str,
    mapped_tickers: list[str],
    start_date: str,
    end_date: str,
) -> tuple[str, str, str]:
    """Fetch and label sentiment data blocks for multiple mapped tickers.

    Each source block (news, StockTwits, Reddit) is prefixed with a header
    that identifies the ticker and its parent ISIN, then all blocks for
    that source are concatenated so the LLM receives one unified string
    per source.
    """
    news_parts: list[str] = []
    stocktwits_parts: list[str] = []
    reddit_parts: list[str] = []

    for t in mapped_tickers:
        header = f"### {t} (mapped from fund ISIN {isin})"
        news_parts.append(f"{header}\n{get_news.func(t, start_date, end_date)}")
        stocktwits_parts.append(f"{header}\n{fetch_stocktwits_messages(t, limit=30)}")
        reddit_parts.append(f"{header}\n{fetch_reddit_posts(t)}")

    return (
        "\n\n".join(news_parts),
        "\n\n".join(stocktwits_parts),
        "\n\n".join(reddit_parts),
    )


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


def create_sentiment_analyst(llm):
    """Create a sentiment analyst node for the trading graph.

    Pre-fetches news + StockTwits + Reddit data, injects them into the
    prompt as structured blocks, and produces a deterministic sentiment
    report via structured output (with a free-text fallback for providers
    that do not support it).
    """
    structured_llm = bind_structured(llm, SentimentReport, "Sentiment Analyst")

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = get_instrument_context_from_state(state)

        # Resolve which ticker(s) to query for sentiment data. For ordinary
        # tickers this is a no-op ([ticker]). For fund ISINs it returns the
        # user-configured mapped tickers from isin_ticker_map, or falls back
        # to [ticker] with a warning when no mapping is found.
        sentiment_tickers = _resolve_sentiment_tickers(ticker)
        is_mapped = sentiment_tickers != [ticker]

        # Pre-fetch all three sources. Each fetcher degrades gracefully and
        # returns a string (no exceptions surface from here), so the LLM
        # always sees something — either real data or a clear placeholder.
        if is_mapped:
            news_block, stocktwits_block, reddit_block = _fetch_multi_ticker_blocks(
                isin=ticker,
                mapped_tickers=sentiment_tickers,
                start_date=start_date,
                end_date=end_date,
            )
        else:
            news_block = get_news.func(ticker, start_date, end_date)
            stocktwits_block = fetch_stocktwits_messages(ticker, limit=30)
            reddit_block = fetch_reddit_posts(ticker)

        system_message = _build_system_message(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            news_block=news_block,
            stocktwits_block=stocktwits_block,
            reddit_block=reddit_block,
            mapped_tickers=sentiment_tickers if is_mapped else None,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}"
                    "\n{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=end_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        # Format the template into a concrete message list so the structured
        # and free-text paths receive the same input. No bind_tools — the
        # data is already in the prompt.
        formatted_messages = prompt.format_messages(messages=state["messages"])

        report_text = invoke_structured_or_freetext(
            structured_llm,
            llm,
            formatted_messages,
            render_sentiment_report,
            "Sentiment Analyst",
        )

        return {
            "messages": [AIMessage(content=report_text)],
            "sentiment_report": report_text,
        }

    return sentiment_analyst_node


def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    stocktwits_block: str,
    reddit_block: str,
    mapped_tickers: list[str] | None = None,
) -> str:
    """Assemble the sentiment-analyst system message with structured data blocks.

    When ``mapped_tickers`` is provided the subject is a fund identified by
    ``ticker`` (an ISIN). The data blocks contain labelled sections for each
    mapped ticker and the intro paragraph tells the LLM to interpret them in
    aggregate as a proxy for the fund's sentiment.
    """
    if mapped_tickers:
        subject_description = (
            f"{ticker} (a fund). Because funds are identified by ISIN on "
            f"exchanges but discussed on social media by their exchange-listed "
            f"ticker symbols or constituent holdings, sentiment data has been "
            f"collected for the following mapped tickers: "
            f"{', '.join(mapped_tickers)}. Each section in the data blocks "
            f"below is labelled by ticker. Synthesise all sections into a "
            f"single, unified sentiment picture for the fund as a whole."
        )
    else:
        subject_description = ticker
    return f"""You are a financial market sentiment analyst. Your task is to produce a comprehensive sentiment report for {subject_description} covering the period from {start_date} to {end_date}, drawing on three complementary data sources that have already been collected for you.

## Data sources (pre-fetched, in this prompt)

### News headlines — Yahoo Finance, past 7 days
Institutional framing. Fact-driven, slower-moving signal.

<start_of_news>
{news_block}
<end_of_news>

### StockTwits messages — retail-trader social platform indexed by cashtag
Fast-moving signal. Each message carries a user-labeled sentiment tag (Bullish / Bearish / no-label) plus the message body.

<start_of_stocktwits>
{stocktwits_block}
<end_of_stocktwits>

### Reddit posts — r/wallstreetbets, r/stocks, r/investing (past 7 days)
Community discussion. Engagement signal via upvote score and comment count. Subreddit character matters (r/wallstreetbets is often contrarian/exuberant; r/stocks more measured; r/investing longer-term).

<start_of_reddit>
{reddit_block}
<end_of_reddit>

## How to analyze this data (best practices)

1. **Read the StockTwits Bullish/Bearish ratio as a leading retail-sentiment signal.** A 70/30 bullish/bearish split is moderately bullish; ≥90/10 may indicate over-extension and contrarian risk; 50/50 is uncertainty. Sample size matters — base rates on the actual message count, not percentages alone.

2. **Look for cross-source divergences.** If news framing is bearish but StockTwits is overwhelmingly bullish, that mismatch is itself a signal — it can mean retail is leaning into a thesis the news flow hasn't caught up to (or vice versa, that retail is chasing while institutions are cautious).

3. **Weight Reddit posts by engagement.** A 400-upvote / 200-comment thread reflects community attention; a 3-upvote post is noise. Read the body excerpts for context — the title alone often misleads.

4. **Distinguish opinion from event.** A news headline ("Nvidia announces $500M Corning deal") is an event; a StockTwits post ("buying NVDA, this is going to moon") is opinion. Both are inputs but should be weighted differently in your conclusions.

5. **Identify recurring narrative themes.** What topic keeps coming up across sources? That's the dominant narrative driving current sentiment.

6. **Be honest about data limits.** If StockTwits returned only a handful of messages, or one or more sources returned an "<unavailable>" placeholder, the sentiment read is less robust — flag this explicitly in the `confidence` field and the narrative. If the sources are silent on a given subreddit, say so.

7. **Identify catalysts and risks** that emerge across sources — news of upcoming earnings, product launches, competitive threats, macro headlines, etc.

8. **Past sentiment is not predictive.** Frame your conclusions as signal for the trader to weigh alongside fundamentals and technicals, not as a price call.

## Output fields

Fill the following fields:

- **overall_band**: Exactly one of Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish. Use Mixed when sources point in clearly different directions; Neutral only when all sources are genuinely silent.
- **overall_score**: A number from 0 (maximally bearish) to 10 (maximally bullish); 5 is neutral. Keep it consistent with overall_band.
- **confidence**: low / medium / high, based on data quality and sample size.
- **narrative**: Full source-by-source breakdown, divergences, dominant narrative themes, catalysts and risks, and a markdown summary table of key sentiment signals (direction, source, supporting evidence).

{get_language_instruction()}"""


# ---------------------------------------------------------------------------
# Backwards-compatibility shim
# ---------------------------------------------------------------------------
def create_social_media_analyst(llm):
    """Deprecated alias for :func:`create_sentiment_analyst`.

    Kept so existing code that imports ``create_social_media_analyst``
    continues to work.

    .. deprecated::
        Import :func:`create_sentiment_analyst` directly instead.
    """
    import warnings
    warnings.warn(
        "create_social_media_analyst is deprecated and will be removed in a "
        "future version. Use create_sentiment_analyst instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_sentiment_analyst(llm)
