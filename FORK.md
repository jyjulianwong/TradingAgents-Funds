# Fork guide

This repository is a fork of [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
that adds investment-fund (ISIN) analysis. Upstream is the `TradingAgents` git remote;
merge it with `git fetch TradingAgents main && git merge TradingAgents/main`.

## Finding what the fork changed

- **Fork-only files** (not present upstream): `git diff --name-status TradingAgents/main HEAD | grep ^A`
- **Fork edits inside upstream-owned files** carry a `FORK(funds)` marker comment:

  ```bash
  grep -rn "FORK(funds)" --include=* . --exclude-dir=.git --exclude-dir=.venv
  ```

  The text after the colon names the topic: `fund` (Fund Analyst / ISIN proxy support),
  `ohlcv-interval` (configurable candle interval), `markdown-tables` (blank line before tables),
  `cli-presets` (env-driven CLI skips), `visualizer`, `reddit-feed-token`, `sentiment-window`,
  `valuation-history` and `earnings-outlook` (the Fundamentals Analyst's valuation tools),
  `debate-order` (Bear opens the research debate, Bull closes it),
  `macro-regime` (the US All Weather regime the investment debate weighs on fund runs),
  `investment-news` (the Investment News Analysis AI report the investment debate reads on fund runs).
  A bare `FORK(funds)` marks a fork edit with no topic, such as the autonomous-agent prompt
  instruction in the analysts.
  Import lines are left unmarked (a comment there makes isort reflow them); the code that
  uses the import is marked.

## Conventions

- Do not run a formatter over upstream-owned files; keep their layout so upstream merges stay small.
- Prefer new fork-only modules plus a one-line hook in the upstream file, tagged `# FORK(funds): <topic>`.

## Where the fork's logic lives

Fork behaviour is kept in fork-only modules; the upstream files carry only tagged hooks.

| Upstream file | Fork module | Hook in the upstream file |
| --- | --- | --- |
| `agents/context.py` | `agents/fund_context.py` (ISIN detection, proxy-ticker resolution, fund and autonomous-agent prompt notes) | re-export import, `mapped_tickers` parameter, one `fund_instrument_note` call |
| `agents/schemas.py` | `agents/fund_schemas.py` (`FundHoldingsAnalysis`) | none (untouched) |
| `default_config.py` | `fund_config.py` (env overrides, fund vendors, `isin_ticker_map`, CLI presets, OHLCV interval, earnings-outlook vendor) | four `**FUND_*` merges |
| `dataflows/router.py` | `dataflows/fund_vendors.py` (fund fact-sheet, symbol-search and earnings-outlook routing) | three table merges |
| `reporting.py` | `fund_report.py` (`proxy_banner`) | one import, the Fund Analyst section row, one call |
| `agents/tools.py` (per-instrument tools) | `agents/fund_tools.py` (symbol-selectable twins) | `ToolNode(tool_node_tools(...))` in `graph/setup.py`; `tools_for_run(...)` and a prompt sentence in the market, news and fundamentals analysts |
| `agents/tools.py` (new tools) | `agents/fund_valuation_tools.py` (`get_valuation_history`, `get_earnings_outlook`); prompt text in `fund_context.get_valuation_instruction` | `TOOLS += VALUATION_TOOLS` and one `get_valuation_instruction()` call in the fundamentals analyst |
| `dataflows/date_window.py` | `dataflows/fund_date_window.py` (`withhold_live_estimates`) | none (untouched) |
| `agents/state.py`, Bull/Bear researchers, Research Manager | `dataflows/vendors/market_regime.py` (Market Regime Detector client), `agents/fund_macro_regime.py` (rendered block, `get_macro_regime_instruction`); fetched in `agents/analysts/fund_analyst.py` for live fund runs only | one `macro_regime_report` state field; one `+ get_macro_regime_instruction(state)` line in each of the three debate prompts |
| `agents/state.py`, Bull/Bear researchers, Research Manager, `reporting.py` | `dataflows/vendors/investment_news.py` (dated report client), `agents/fund_investment_news.py` (lookback to the latest report on or before the trade date, rendered block, `get_investment_news_instruction`); fetched in `agents/analysts/fund_analyst.py` for every fund run | one `investment_news_analysis_ai_report` state field; one `+ get_investment_news_instruction(state)` line in each of the three debate prompts; one `_SECTIONS` row saving `1_analysts/investment_news.md` |

### Keeping the fund tools in step with upstream

Upstream pins every per-instrument tool to the run's instrument, so a fund run could never fetch a
proxy ticker's data. `fund_tools.with_symbol` builds a twin of each such tool by reading its signature,
adds an optional `symbol` argument (a fund run's ISIN or resolved proxies only), and calls upstream's own
function (`tool.func`). So vendor and router fixes, and fixes inside a tool body, reach fund runs with no
edit here, and a new argument added upstream to a tool appears on its twin automatically.
`tests/test_fund_tools.py` fails if upstream changes how a tool declares its injected symbol or state
in a way the twin can't follow.
