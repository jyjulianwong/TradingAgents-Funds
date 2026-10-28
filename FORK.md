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
  `autonomous-agent` / `hotfix #000N` (prompt hotfixes), `cli-presets` (env-driven CLI skips),
  `visualizer`, `reddit-feed-token`, `sentiment-window`.
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
| `default_config.py` | `fund_config.py` (env overrides, fund vendors, `isin_ticker_map`, CLI presets, OHLCV interval) | four `**FUND_*` merges |
| `dataflows/router.py` | `dataflows/fund_vendors.py` (fund fact-sheet and symbol-search routing) | three table merges |
| `reporting.py` | `fund_report.py` (`proxy_banner`) | one import, the Fund Analyst section row, one call |
| `agents/tools.py` (per-instrument tools) | `agents/fund_tools.py` (symbol-selectable twins) | `ToolNode(tool_node_tools(...))` in `graph/setup.py`; `tools_for_run(...)` and a prompt sentence in the market, news and fundamentals analysts |

### Keeping the fund tools in step with upstream

Upstream pins every per-instrument tool to the run's instrument, so a fund run could never fetch a
proxy ticker's data. `fund_tools.with_symbol` builds a twin of each such tool by reading its signature,
adds an optional `symbol` argument (a fund run's ISIN or resolved proxies only), and calls upstream's own
function (`tool.func`). So vendor and router fixes, and fixes inside a tool body, reach fund runs with no
edit here, and a new argument added upstream to a tool appears on its twin automatically.
`tests/test_fund_tools.py` fails if upstream changes how a tool declares its injected symbol or state
in a way the twin can't follow.
