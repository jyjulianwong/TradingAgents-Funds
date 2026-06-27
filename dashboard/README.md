# TradingAgents Research Archive Dashboard

Bloomberg Terminal-style browser for `~/.tradingagents/` — view and manage all
research reports and visualizer event logs in one place.

## Features

- Browse all analysis runs (`logs/<TICKER>/<DATE>/`) with their trade signal (BUY / OVERWEIGHT / HOLD / UNDERWEIGHT / SELL)
- Read every report file with full markdown rendering
- Browse visualizer event JSONL logs as structured timelines
- Delete individual files, entire runs, or event logs (with confirmation)
- Resizable sidebar, live filter, keyboard shortcuts (F1/F2)

## Quick start

**Option A — uv (recommended, uses the project lockfile)**

```bash
# From the repo root:
uv run python dashboard/server.py
```

**Option B — isolated virtual environment**

```bash
cd dashboard
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python server.py
```

**Option C — plain Python (if fastapi/uvicorn already installed)**

```bash
python dashboard/server.py
```

Then open **http://127.0.0.1:7843** in your browser.

## Options

```
python server.py [PORT]          # default port is 7843
```

Set `TRADINGAGENTS_DIR` to override the default `~/.tradingagents/` base path:

```bash
TRADINGAGENTS_DIR=/custom/path python server.py
```

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `F1` | Switch to Reports tab |
| `F2` | Switch to Visualizer Events tab |
| `Esc` | Close confirmation modal |

## Directory layout browsed

```
~/.tradingagents/
├── logs/
│   └── {TICKER}/
│       └── {DATE}/
│           ├── reports/
│           │   ├── final_trade_decision.md   ← signal extracted from here
│           │   ├── market_report.md
│           │   ├── sentiment_report.md
│           │   ├── news_report.md
│           │   ├── fundamentals_report.md
│           │   ├── investment_plan.md
│           │   └── trader_investment_plan.md
│           └── message_tool.log
└── visualizer_events/
    └── {TIMESTAMP}_{TICKER}.jsonl
```
