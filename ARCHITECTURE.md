# TradingAgents — Architecture Deep-Dive

> Research-only. Not financial advice.

This document explains how TradingAgents works under the hood: which AI frameworks are used at each step, how the workflow is structured, how prompts and tools are configured, and how state flows through the system.

---

## Table of Contents

1. [Framework Stack](#1-framework-stack)
2. [End-to-End Pipeline](#2-end-to-end-pipeline)
3. [Workflow Topology — Sequential vs Loops](#3-workflow-topology)
4. [State Management](#4-state-management)
5. [Prompt Construction Styles](#5-prompt-construction-styles)
6. [Tool Calling](#6-tool-calling)
7. [Structured Output](#7-structured-output)
8. [Data Vendor Layer](#8-data-vendor-layer)
9. [LLM Client Abstraction](#9-llm-client-abstraction)
10. [Memory and Reflection](#10-memory-and-reflection)
11. [Checkpointing](#11-checkpointing)

---

## 1. Framework Stack

| Layer | Framework | Where used |
|---|---|---|
| **Agent orchestration** | [LangGraph](https://langchain-ai.github.io/langgraph/) `StateGraph` | `graph/setup.py`, `graph/trading_graph.py` |
| **LLM integration** | [LangChain Core](https://python.langchain.com/) | Prompts, messages, tool binding, structured output |
| **Prompt templates** | `langchain_core.prompts.ChatPromptTemplate` | Tool-calling analysts |
| **Tool nodes** | LangGraph `ToolNode` | `graph/trading_graph.py` |
| **Structured output** | Pydantic v2 `BaseModel` + `with_structured_output` | Schemas for 4 decision nodes |
| **LLM providers** | `langchain-openai`, `langchain-anthropic`, `langchain-google-genai`, `langchain-aws` | `llm_clients/` |
| **State schema** | LangGraph `MessagesState` (TypedDict) | `agents/utils/agent_states.py` |
| **Checkpointing** | `langgraph-checkpoint-sqlite` | `graph/checkpointer.py` |
| **Data fetching** | `yfinance`, `stockstats`, `requests` | `dataflows/` |

TradingAgents does **not** use LangChain Agents or LangChain Expression Language (LCEL) chains as its primary orchestration mechanism — it uses LangGraph's `StateGraph` directly, giving explicit control over every routing decision.

---

## 2. End-to-End Pipeline

```
Config + Ticker + Date
        │
        ▼
┌──────────────────────────────────┐
│  resolve_instrument_identity()   │  yfinance lookup — deterministic grounding
│  TradingMemoryLog.resolve()      │  deferred reflections from prior runs
└──────────────────────────────────┘
        │  initial AgentState
        ▼
┌───────────────────────────────────────────────────────────────┐
│                    ANALYST PHASE  (sequential)                │
│                                                               │
│  ┌─────────────┐   ┌─────────────┐   ┌──────────┐   ┌──────┐ │
│  │   Market    │   │  Sentiment  │   │   News   │   │ Fund │ │
│  │  Analyst    │──▶│  Analyst    │──▶│ Analyst  │──▶│ amen │ │
│  │ (tool loop) │   │ (no tools)  │   │(tool loop│   │ tals │ │
│  └─────────────┘   └─────────────┘   └──────────┘   └──────┘ │
│                                                               │
│  Each writes a report key to AgentState.                      │
│  Messages are cleared between analysts.                       │
└───────────────────────────────────────────────────────────────┘
        │  market_report, sentiment_report, news_report, fundamentals_report
        ▼
┌───────────────────────────────────────────────────────────────┐
│                  INVESTMENT DEBATE  (loop)                    │
│                                                               │
│   ┌──────────────────────────────────────────┐               │
│   │  Bull Researcher ◀──────────────────────┐│               │
│   │       │                                  ││               │
│   │       ▼                                  ││               │
│   │  Bear Researcher ──────────────────────▶ ││               │
│   └──────────────────────────────────────────┘│               │
│         Runs for max_debate_rounds × 2 turns   │               │
└───────────────────────────────────────────────────────────────┘
        │  investment_debate_state.history
        ▼
┌───────────────────────────────────────────────────────────────┐
│            RESEARCH MANAGER  (single-shot, deep LLM)         │
│            Pydantic ResearchPlan → investment_plan            │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│            TRADER  (single-shot, quick LLM)                  │
│            Pydantic TraderProposal → trader_investment_plan   │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│                  RISK DEBATE  (3-way loop)                    │
│                                                               │
│   Aggressive ──▶ Conservative ──▶ Neutral ──▶ Aggressive …   │
│         Runs for max_risk_discuss_rounds × 3 turns            │
└───────────────────────────────────────────────────────────────┘
        │  risk_debate_state.history
        ▼
┌───────────────────────────────────────────────────────────────┐
│         PORTFOLIO MANAGER  (single-shot, deep LLM)           │
│         Pydantic PortfolioDecision → final_trade_decision     │
│         5-tier rating: Buy / Overweight / Hold /              │
│                        Underweight / Sell                     │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
  SignalProcessor  →  rating enum  →  JSON log + markdown reports
  TradingMemoryLog  →  pending decision stored for next run
```

---

## 3. Workflow Topology

### Overview

| Phase | Pattern | Why |
|---|---|---|
| Analyst nodes | **Sequential** | Reports are independent inputs to debate |
| Analyst ↔ tools | **Tool loop** (per analyst) | LLM decides when it has enough data |
| Bull ↔ Bear | **Conditional debate loop** | `count < 2 × max_debate_rounds` |
| Research Manager | **Single-shot** | Synthesises debate into a plan |
| Trader | **Single-shot** | Translates plan to a trade proposal |
| Aggressive / Conservative / Neutral | **3-way conditional loop** | `count < 3 × max_risk_discuss_rounds` |
| Portfolio Manager | **Terminal** | Final decision |

### LangGraph `StateGraph` wiring (simplified)

```
START
  │
  ▼
Market Analyst  ──has tool_calls?──▶  tools_market  ─┐
  ◀────────────────────────────────────────────────────┘
  │ no tool_calls
  ▼
Msg Clear Market
  │
  ▼
Sentiment Analyst  (single-shot, no tool loop)
  │
  ▼
Msg Clear Sentiment
  │
  ▼
News Analyst  ──has tool_calls?──▶  tools_news  ─┐
  ◀────────────────────────────────────────────────┘
  │ no tool_calls
  ▼
Msg Clear News
  │
  ▼
Fundamentals Analyst  ──has tool_calls?──▶  tools_fundamentals  ─┐
  ◀──────────────────────────────────────────────────────────────┘
  │ no tool_calls
  ▼
Msg Clear Fundamentals
  │
  ▼
Bull Researcher ◀──────────────────────────────────────────────┐
  │                                                            │
  ▼                                                            │
Bear Researcher  ──count < limit?──▶ route to Bull or Bear ───┘
  │ count >= limit
  ▼
Research Manager
  │
  ▼
Trader
  │
  ▼
Aggressive Debater ◀───────────────────────────────────────────┐
  │                                                            │
  ▼                                                            │
Conservative Debater                                           │
  │                                                            │
  ▼                                                            │
Neutral Debater  ──count < limit?──▶ route back to Aggressive ┘
  │ count >= limit
  ▼
Portfolio Manager
  │
  ▼
END
```

### The analyst selection is configurable

The four analysts are user-selectable. `build_analyst_execution_plan()` in `graph/analyst_execution.py` validates and orders the chosen subset. All combinations are supported — e.g. running only Market + News analysts skips Sentiment and Fundamentals entirely, and the graph edges are rebuilt accordingly.

### Non-determinism

The debate and risk loops are **bounded** (configurable via `max_debate_rounds` / `max_risk_discuss_rounds`), so the graph always terminates. The routing is deterministic (round counting + speaker prefix prefix matching), not LLM-driven. The only "non-deterministic" element is LLM token sampling, but that is not graph-structural.

---

## 4. State Management

### `AgentState` (extends `MessagesState`)

All nodes read from and write to a single shared `AgentState` dictionary. LangGraph manages immutable state transitions — each node receives the full state and returns a partial update.

```
AgentState
├── messages: list[BaseMessage]         # LangChain message history; cleared between analysts
├── company_of_interest: str            # Ticker symbol
├── asset_type: str                     # "stock" or "crypto"
├── instrument_context: str             # Deterministic company identity string (anti-hallucination)
├── trade_date: str                     # Analysis date
├── past_context: str                   # Memory log lessons from prior same-ticker runs
│
├── market_report: str                  # Written by Market Analyst
├── sentiment_report: str               # Written by Sentiment Analyst
├── news_report: str                    # Written by News Analyst
├── fundamentals_report: str            # Written by Fundamentals Analyst
│
├── investment_debate_state: InvestDebateState
│   ├── bull_history: str               # Bull researcher's argument history
│   ├── bear_history: str               # Bear researcher's argument history
│   ├── history: str                    # Full interleaved debate
│   ├── current_response: str           # Last speaker's message (routing hint)
│   ├── count: int                      # Turn counter (2 per round)
│   └── judge_decision: str             # Research Manager's verdict
│
├── investment_plan: str                # Written by Research Manager
│
├── trader_investment_plan: str         # Written by Trader
├── sender: str                         # "Trader" (set by Trader node)
│
├── risk_debate_state: RiskDebateState
│   ├── agg_history: str
│   ├── con_history: str
│   ├── neu_history: str
│   ├── history: str
│   ├── latest_speaker: str             # Routing hint ("Aggressive Analyst:…")
│   ├── count: int                      # Turn counter (3 per round)
│   └── judge_decision: str
│
└── final_trade_decision: str           # Written by Portfolio Manager
```

### Message clearing between analysts

After each analyst finishes its tool loop, a `Msg Clear` node runs:

```python
# agent_utils.py — create_msg_delete()
def create_msg_delete(human_message: str):
    def delete_messages(state):
        # Remove every existing message via RemoveMessage
        deletions = [RemoveMessage(id=m.id) for m in state["messages"]]
        # Re-anchor with a minimal human message so the messages list is never empty
        return {"messages": deletions + [HumanMessage(content=human_message)]}
    return delete_messages
```

This gives each analyst a clean context window while keeping the `messages` channel alive in the graph.

---

## 5. Prompt Construction Styles

Three different styles coexist across the codebase:

### Style A — `ChatPromptTemplate` with `MessagesPlaceholder` (tool-calling analysts)

Used by **Market Analyst**, **News Analyst**, **Fundamentals Analyst**.

```python
# market_analyst.py (simplified)
system_message = """You are a helpful AI assistant collaborating with other agents...
Today's date is {current_date}.
You are analysing {instrument_context}.
Available tools: {tool_names}
{system_message}
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", system_message),
    MessagesPlaceholder(variable_name="messages"),
])
prompt = prompt.partial(
    tool_names=", ".join([t.name for t in tools]),
    current_date=state["trade_date"],
    instrument_context=...,
)
chain = prompt | llm.bind_tools(tools)
result = chain.invoke({"messages": state["messages"]})
```

`MessagesPlaceholder` injects the tool call / tool result conversation history so the analyst can iterate across multiple LLM calls within one node invocation.

### Style B — F-string prompts (researchers, risk debaters, managers)

Used by **Bull/Bear Researchers**, **Aggressive/Conservative/Neutral Debaters**, **Research Manager**, **Portfolio Manager**.

```python
# bull_researcher.py (simplified)
prompt = f"""
You are a Bull Researcher. Analyse the following reports and construct a bullish argument.

{instrument_context}

Market report:
{state["market_report"]}

Previous debate:
{debate_state["history"]}

Bear's last argument:
{debate_state["bear_history"]}

{language_instruction}
"""
response = llm.invoke(prompt)
```

Simple and direct — no template engine needed because these agents never call tools.

### Style C — Dict message list (Trader)

```python
# trader.py (simplified)
messages = [
    {"role": "system", "content": "You are an experienced stock trader..."},
    {"role": "user",   "content": f"Based on this investment plan:\n{investment_plan}\nPropose a trade."},
]
response = llm.invoke(messages)
```

### i18n injection

All prompts append the output language directive just before the LLM call:

```python
# agent_utils.py
def get_language_instruction(config) -> str:
    lang = config.get("output_language", "English")
    if lang.lower() == "english":
        return ""
    return f"\nPlease respond in {lang}."
```

---

## 6. Tool Calling

### Which agents use tools

| Agent | Tool calling? | How |
|---|---|---|
| Market Analyst | Yes — loop | `llm.bind_tools(tools)` + `ToolNode` |
| Sentiment Analyst | No | Pre-fetches data before the LLM call |
| News Analyst | Yes — loop | `llm.bind_tools(tools)` + `ToolNode` |
| Fundamentals Analyst | Yes — loop | `llm.bind_tools(tools)` + `ToolNode` |
| Bull/Bear Researchers | No | F-string prompt, raw `llm.invoke` |
| Research Manager | No | Structured output only |
| Trader | No | Structured output only |
| Risk Debaters | No | F-string prompt, raw `llm.invoke` |
| Portfolio Manager | No | Structured output only |

### Tool loop mechanism (LangGraph)

```
Analyst node
  │
  ├── LLM returns AIMessage with tool_calls?
  │     │  YES
  │     ▼
  │   ToolNode  (executes each tool, appends ToolMessage to state["messages"])
  │     │
  │     └──▶  back to Analyst node  (loop)
  │
  └── LLM returns AIMessage without tool_calls?
        │  NO
        ▼
      Extract final content → write report key to state
      Route to Msg Clear node
```

The routing is in `conditional_logic.py`:

```python
def router(state):
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools_market"       # or tools_news, tools_fundamentals
    return "Msg Clear Market"       # done
```

### Available tool sets per analyst

```
Market Analyst
  ├── get_stock_data          (OHLCV, volume)
  ├── get_indicators          (RSI, MACD, Bollinger Bands, …)
  └── get_verified_market_snapshot   (must call before final report)

News Analyst
  ├── get_news                (Yahoo Finance headlines)
  ├── get_global_news         (broader macro news)
  ├── get_macro_indicators    (FRED data)
  └── get_prediction_markets  (Polymarket probabilities)

Fundamentals Analyst
  ├── get_fundamentals        (P/E, EPS, market cap, …)
  ├── get_balance_sheet
  ├── get_cashflow
  └── get_income_statement
```

### Tool definitions

Tools are LangChain `@tool`-decorated functions in `agents/utils/*_tools.py`, e.g.:

```python
@tool
def get_stock_data(ticker: str, start_date: str, end_date: str) -> str:
    """Fetch OHLCV price data for a stock ticker."""
    return route_to_vendor("get_stock_data", ticker, start_date, end_date)
```

The `@tool` decorator exposes the docstring and type hints as the JSON schema the LLM receives. Actual data fetching is delegated to the vendor router (see §8).

### Sentinel values prevent hallucination

When no data is available, tools return string sentinels rather than raising:

```
"NO_DATA_AVAILABLE: <reason>"    — missing market data
"DATA_UNAVAILABLE"               — optional categories (macro, prediction markets)
```

The LLM is instructed to report these sentinels as-is rather than fabricate values.

---

## 7. Structured Output

Four decision nodes use Pydantic schemas for type-safe, parseable output.

| Node | Schema | Key fields |
|---|---|---|
| Research Manager | `ResearchPlan` | `recommendation` (5-tier), `rationale`, `strategic_actions` |
| Trader | `TraderProposal` | `action` (Buy/Hold/Sell), `reasoning`, `entry_price`, `stop_loss` |
| Portfolio Manager | `PortfolioDecision` | `rating` (5-tier), `executive_summary`, `investment_thesis` |
| Sentiment Analyst | `SentimentReport` | `overall_band` (6-tier), `overall_score` (0–10), `confidence` |

### How structured output works

```python
# structured.py
def invoke_structured_or_freetext(llm, structured_llm, prompt, render_fn, plain_fallback):
    try:
        result = structured_llm.invoke(prompt)   # with_structured_output(Schema)
        return render_fn(result)                 # Pydantic → markdown string
    except Exception:
        return plain_fallback.invoke(prompt).content   # raw text fallback
```

`bind_structured()` calls `llm.with_structured_output(schema)` and returns `None` if the provider/model does not support structured output (e.g. some Ollama models), in which case the caller falls back to free-text automatically.

The Pydantic field descriptions double as instructions to the LLM:

```python
class PortfolioDecision(BaseModel):
    rating: Literal["Buy", "Overweight", "Hold", "Underweight", "Sell"] = Field(
        description="Final 5-tier rating for the asset"
    )
    executive_summary: str = Field(
        description="2-3 sentence high-level verdict for a fund manager audience"
    )
```

---

## 8. Data Vendor Layer

All tools ultimately call `dataflows/interface.py`, which acts as a config-driven vendor router:

```
@tool function
    │
    ▼
route_to_vendor(method, *args)
    │
    ├── look up config["tool_vendors"] (tool-specific override)
    │   OR config["data_vendors"] (default chain)
    │
    ├── try vendor 1  →  success  →  return result
    ├── try vendor 2  →  success  →  return result
    └── all failed
          ├── core category  →  raise NoMarketDataError
          └── optional category  →  return "DATA_UNAVAILABLE"
```

**Supported vendors:**

| Category | Vendors |
|---|---|
| Stock prices / OHLCV | `yfinance`, `alpha_vantage` |
| Technical indicators | `yfinance` (via stockstats) |
| Fundamentals | `yfinance`, `alpha_vantage` |
| News | `yfinance`, `alpha_vantage` |
| Macro indicators | `fred` |
| Prediction markets | `polymarket` |
| Social sentiment (pre-fetched) | `reddit`, `stocktwits` |

No vendor is silently substituted — only vendors listed in `data_vendors` / `tool_vendors` config are tried.

---

## 9. LLM Client Abstraction

```
create_llm_client(provider, model, base_url)
    │
    ├── "anthropic"  →  AnthropicClient   (langchain-anthropic)
    ├── "google"     →  GoogleClient      (langchain-google-genai)
    ├── "azure"      →  AzureOpenAIClient (langchain-openai)
    ├── "bedrock"    →  BedrockClient     (langchain-aws)
    └── everything else (openai, xAI, DeepSeek, Qwen, Groq,
                         Ollama, OpenRouter, Mistral, …)
                     →  OpenAIClient      (langchain-openai with custom base_url)
```

All clients expose `.get_llm()` returning a standard LangChain `BaseChatModel`, so the rest of the codebase is provider-agnostic. The graph uses two LLM tiers:

| Tier | Config key | Used by |
|---|---|---|
| Deep think | `deep_think_llm` | Research Manager, Portfolio Manager |
| Quick think | `quick_think_llm` | All analysts, researchers, risk debaters, trader |

Both tiers always use the same provider, configured in `DEFAULT_CONFIG`.

---

## 10. Memory and Reflection

TradingAgents maintains a persistent append-only log at `~/.tradingagents/memory/trading_memory.md` (configurable).

### Decision logging

When `propagate()` completes, the final decision is written as a `PENDING` entry:

```
## NVDA | 2026-01-15 | PENDING
Rating: Buy
Decision: …
```

### Deferred reflection

On the **next** run for the same ticker, `TradingMemoryLog.resolve_pending()` fetches realized returns via yfinance, then calls the `Reflector` (LLM) to produce a lesson:

```python
# graph/reflection.py
prompt = f"You made a {rating} call on {ticker} on {date}. "
         f"The stock moved {return_pct:.1f}% over {days} days. "
         f"Reflect on what you got right or wrong."
```

The lesson is injected into `past_context` in `AgentState` for the **Portfolio Manager** only, closing the learning loop.

---

## 11. Checkpointing

LangGraph's SQLite checkpointer can resume interrupted runs:

```
~/.tradingagents/cache/checkpoints/<TICKER>.db
```

When `checkpoint_enabled = True`, the graph is compiled with `SqliteSaver` and a `thread_id = f"{ticker}_{date}"`. On success the checkpoint DB is cleared. This means a run interrupted mid-debate can resume from exactly the last completed node rather than restarting from the beginning.

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| LangGraph `StateGraph` over LangChain Agents | Explicit routing, bounded loops, no agent autonomy over graph structure |
| Two-tier LLM (deep + quick) | Cost/quality tradeoff — only synthesis nodes need max reasoning |
| Message clearing between analysts | Prevents context bleed; each analyst gets a clean window |
| Pre-fetched data for Sentiment Analyst | Social data APIs are rate-sensitive; tool looping would be wasteful |
| Pydantic schemas for decisions | Machine-readable output for downstream processing and signal extraction |
| Vendor router + sentinels | Prevents silent hallucination when data is unavailable |
| Deterministic instrument grounding | Prevents wrong-company confusions (e.g. TICKER ≠ company name) |
| Bounded debate rounds | Guarantees termination; rounds configurable per run |
