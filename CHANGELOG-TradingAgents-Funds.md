# Changelog: TradingAgents-Funds

Changes specific to this fork of [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents).
See `FORK.md` for how to find fork edits (`grep -rn "FORK(funds)"`).

## Unreleased: fund runs can fetch proxy-ticker data

- Fixed: since upstream pinned its data tools to the run's instrument (v0.5.x), a fund run's Market, News and Fundamentals analysts got the ISIN's own data for every proxy request, so no proxy prices, indicators, fundamentals or news were ever used. Added `agents/fund_tools.py`: twins of upstream's tools with an optional `symbol` (the ISIN or its resolved proxies only) that delegate to upstream's own tool functions, so upstream vendor and tool fixes carry through. Ordinary tickers still get upstream's tools and schemas.

## Merge of upstream v0.7.1

- Merged upstream v0.7.1. Upstream fixed the Windows/macOS lock-error handling itself, so the fork's `windows-lock-fix` edit was dropped. Moved the proxy-instruments report banner into `fund_report.py`.

## Merge of upstream v0.7.0

### Still tangled with upstream (needs looking into)

Fork logic that still lives inside upstream-owned files, as small edits tagged `FORK(funds)`.
These cause merge conflicts when upstream touches the same lines, so they are the places to
look at first when trying to separate the fork further.

Largest remaining edits (lines added/removed against upstream v0.7.0):

- `tradingagents/agents/analysts/sentiment_analyst.py` (+125/-20): ISIN proxy-ticker multi-fetch, fund-aware prompt, and a 30-day news window, all interleaved with upstream's subreddit handling.
- `cli/run.py` (+71): CLI presets and visualizer start-up woven into the run flow.
- `tradingagents/dataflows/vendors/yahoo/ohlcv.py` (+56/-15) and `vendors/alpha_vantage/stock.py` (+37/-20): configurable candle interval (`ohlcv_interval`), unrelated to funds.
- `tradingagents/agents/analysts/market_analyst.py` (+50) and `fundamentals_analyst.py` (+40): per-proxy-ticker loops and fund notes inside the analyst functions.
- `cli/selections.py` (+39/-7): environment-driven skips for the analysis date and analysts prompts.
- `tradingagents/reporting.py`, `graph/setup.py` (+21/-6), `graph/trading_graph.py` (+17/-2), `agents/state.py` (+14), `agents/tools.py` (+20): Fund Analyst section and banner, graph wiring, state fields, tool changes.
- Bull/bear researchers, risk debaters, research manager, portfolio manager and trader: a fund-instruction hook, a markdown-table fix and an autonomous-agent hotfix in each prompt (about 14 lines per file).

Edits that are not fund features and could be split out or proposed upstream:

- `ohlcv_interval` option (OHLCV files above).
- Markdown blank-line-before-table fix applied to every agent output (`agents/markdown.py` plus hooks).
- `get_autonomous_agent_instruction` prompt hotfixes (`FORK(funds): hotfix #0001` and `#0002`).
- Reddit RSS feed-token support (`dataflows/vendors/reddit.py`).
- Prompt wording changes (for example news "past week" became "past month").

Other loose ends:

- Import lines are not tagged `FORK(funds)` (a comment there makes isort reflow them), so fork imports in upstream files are only identifiable through the code that uses them.
- `pyproject.toml` excludes `tradingagents/default_config.py` from ruff and adds a `uv-sort`/ruff-format `.pre-commit-config.yaml`; both differ from upstream conventions, which defers repo-wide formatting.
- `uv.lock` is committed here but not upstream, so it will conflict on every upstream dependency change.
- `README.md` has the fork section prepended above upstream's text, so upstream README edits near the top will conflict.

### Changed

- Merged upstream v0.5.2 to v0.7.0 (Memory Log step, per-tier providers, HTML report, crypto subreddits, update check).
- Reverted formatting-only changes to upstream-owned files.
- Added `FORK(funds)` markers and `FORK.md`.
- Moved fund logic out of `context.py`, `schemas.py`, `default_config.py` and `router.py` into `fund_context.py`, `fund_schemas.py`, `fund_config.py` and `dataflows/fund_vendors.py`.
