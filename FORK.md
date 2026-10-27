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
  `visualizer`, `reddit-feed-token`, `sentiment-window`, `windows-lock-fix`.
  Import lines are left unmarked (a comment there makes isort reflow them); the code that
  uses the import is marked.

## Conventions

- Do not run a formatter over upstream-owned files; keep their layout so upstream merges stay small.
- Prefer new fork-only modules plus a one-line hook in the upstream file, tagged `# FORK(funds): <topic>`.
