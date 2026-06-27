# TradingAgents Visualizer

A local 3-D trading-floor animation that plays alongside a live TradingAgents run.

---

## Table of Contents

- [How it works](#how-it-works)
  - [Components](#components)
  - [Event protocol](#event-protocol)
  - [How the CLI integrates](#how-the-cli-integrates)
- [Setup](#setup)
- [Running the simulation script](#running-the-simulation-script)
  - [Camera controls](#camera-controls)
- [Running alongside a live analysis](#running-alongside-a-live-analysis)

---

## Overview

Each agent in the LangGraph pipeline is represented by a blocky character at their own desk.
The office transitions from an out-of-hours state to a fully lit, animated floor as the
analysis progresses, and the large LED board on the back wall reveals the final rating
(`BUY` / `HOLD` / `SELL`) when the Portfolio Manager is done.

---

## How it works

```
┌─────────────────────────┐        events       ┌───────────────────────┐
│   cli/main.py           │ ──────────────────► │  visualizer/bridge.py │
│   (CLI thread)          │                     │  (thread-safe queue)  │
└─────────────────────────┘                     └──────────┬────────────┘
                                                           │  call_soon_threadsafe
                                                           ▼
                                                ┌───────────────────────┐
                                                │  visualizer/server.py │
                                                │  FastAPI + WebSocket  │
                                                └──────────┬────────────┘
                                                           │  JSON over WS
                                                           ▼
                                                ┌───────────────────────┐
                                                │  static/main.js       │
                                                │  Three.js scene       │
                                                └───────────────────────┘
```

### Components

| File | Role |
|---|---|
| `bridge.py` | Module-level singleton event bus. `emit(event)` is called from the CLI thread and fans the event out to every connected WebSocket client via the server's asyncio loop using `call_soon_threadsafe`. Also auto-derives a `handoff` event whenever two consecutive `agent_active` events arrive for different agents. |
| `server.py` | Thin FastAPI app. Starts on port **7842** (auto-increments on conflict) in a daemon thread. Serves `static/` and exposes `/ws` for the browser. Polled for readiness before the browser tab is opened. |
| `static/office.js` | Builds the static 3-D environment: semi-transparent walls, tiled floor, ceiling light panels, the canvas-texture LED board, and the following distinct zones — a lounge area (water cooler, coffee station, plants) near the ticker wall; a glass-walled meeting room with an oval conference table for the research team; a continuous five-desk trading row (Trader + four NPC desks with static silhouettes); and the Portfolio Manager's glass corner office at the back with an executive desk, visitor chairs, and a brass nameplate. Exports helpers to toggle office lighting and draw the scrolling / signal text on the board. |
| `static/characters.js` | Defines `AGENT_CONFIGS` (name, desk position, colour, and optional `homeRotation` / `seated` flags per agent) and the `CharacterManager` / `Character` classes. `seated: true` agents (researchers) start at their exact desk coordinate rather than 1.3 units in front of it, and their `homeRotation` controls which direction they face around the conference table. `goHome()` always restores the agent's `homeRotation` rather than the default -Z facing. Each character is assembled from `BoxGeometry` parts with a pivoted arm/leg group for animation, a `CSS2DObject` floating label, and a `MeshBasicMaterial` thinking cloud. |
| `static/events.js` | `EventHandler` maps incoming WebSocket events to scene mutations: office lights on, thinking clouds, handoff walks, document prop, final signal. |
| `static/main.js` | Entry point. Sets up the WebGL renderer, `CSS2DRenderer` (for labels), `OrbitControls`, builds the office and characters, connects the WebSocket, and runs the animation loop. |
| `simulate.py` | Standalone demo script — emits the full agent event sequence with realistic delays so you can preview every animation without running real LLM calls. |

### Event protocol

The server sends JSON objects over the WebSocket:

| Event | Fields | Meaning |
|---|---|---|
| `workflow_idle` | — | Office is empty / out-of-hours (sent on connect) |
| `workflow_start` | `ticker`, `date` | Lights on, characters appear, LED board starts scrolling |
| `agent_active` | `agent` | Thinking cloud appears above that character |
| `agent_idle` | `agent` | Thinking cloud removed |
| `handoff` | `from`, `to` | `from` character walks to `to`'s desk, shows document, walks back |
| `workflow_complete` | `signal`, `ticker` | LED board switches to BUY / HOLD / SELL |
| `ping` | — | Keepalive (no action needed) |

`handoff` events are derived automatically by `bridge.py` — callers only need to emit `agent_active` events in sequence.

### How the CLI integrates

`cli/main.py` (`run_analysis`) makes three small additions when the visualizer package is importable:

1. **Server start** — `visualizer.server.start()` is called at the top of `run_analysis`, before the interactive prompts. The browser tab opens immediately so the out-of-hours office is visible while the user fills in config.
2. **Status hook** — `message_buffer.update_agent_status` is wrapped to call `bridge.emit` whenever an agent transitions to `in_progress` or `completed`. The CLI already tracks every agent transition, so no LangGraph internals need to be touched.
3. **Lifecycle events** — `workflow_start` is emitted just before the graph stream loop; `workflow_complete` (with the final signal from `graph.process_signal`) is emitted after it finishes.

The visualizer is fully optional. If `fastapi` / `uvicorn` are not installed, the `try/except` in `run_analysis` silently skips everything and the analysis runs as normal.

---

## Setup

```bash
pip install -r visualizer/requirements.txt
```

Or, if you use `uv`:

```bash
uv pip install -r visualizer/requirements.txt
```

No other configuration is needed. The server binds to `127.0.0.1:7842` by default.

### Event logs

Every event that passes through the bridge — including auto-derived `handoff` events — is
written to a timestamped JSONL file under `~/.tradingagents/visualizer_events/`. A new file
is opened on each `workflow_start`, so every run (or every `simulate.py` invocation) gets
its own log.

```
~/.tradingagents/visualizer_events/<YYYY-MM-DDTHH-MM-SS>[_<TICKER>].jsonl
```

Each line is one JSON object:

```json
{"ts": "2026-06-27T14:30:01.234", "event": {"type": "agent_active", "agent": "Bull Researcher"}}
{"ts": "2026-06-27T14:30:01.235", "event": {"type": "handoff", "from": "Bull Researcher", "to": "Bear Researcher"}}
```

Useful one-liners for inspecting logs:

```bash
# All handoff events from a specific run
jq 'select(.event.type == "handoff")' ~/.tradingagents/visualizer_events/2026-06-27T14-30-01_NVDA.jsonl

# Full event sequence from the most recent run (chronological)
ls -t ~/.tradingagents/visualizer_events/*.jsonl | head -1 | xargs jq .event
```

---

## Running the simulation script

`visualizer/simulate.py` fires the complete agent event sequence through the bridge with
realistic timing so you can inspect every animation phase without any API keys or LLM costs.

```bash
# Default run — NVDA, BUY signal, real-time pacing (~60 s end-to-end)
uv run python -m visualizer.simulate

# Custom ticker and final signal
uv run python -m visualizer.simulate --ticker TSLA --signal SELL

# 4× speed — good for a quick visual check (~15 s)
uv run python -m visualizer.simulate --fast

# Fine-grained control
uv run python -m visualizer.simulate --ticker AAPL --signal HOLD --speed 2 --debate-rounds 3

# All options
uv run python -m visualizer.simulate --help
```

The script:
1. Starts the FastAPI server and opens a browser tab automatically.
2. Waits until the browser's WebSocket connection is established before sending any events (so no animations are missed).
3. Sends events in this order, with configurable delays between each:
   - `workflow_start` → office lights on, all 12 characters appear
   - Market / Sentiment / News / Fundamentals Analyst (sequentially, longest delays — they do tool calls)
   - Bull / Bear debate rounds (back-and-forth handoff walks)
   - Research Manager adjudicates → hands off to Trader
   - Aggressive / Conservative / Neutral risk debate rounds
   - Portfolio Manager → `workflow_complete` with the chosen signal
4. Stays alive afterwards so you can orbit the camera freely. Press **Ctrl-C** to exit.

### Camera controls

| Action | Input |
|---|---|
| Orbit | Left-drag |
| Zoom | Scroll wheel |
| Pan | Right-drag |

---

## Replaying an event log

`visualizer/replay.py` reads any `.jsonl` log from `~/.tradingagents/visualizer_events/`
and plays it back through the browser animation with the original inter-event timing.
Use this to verify a fix without re-running a full LLM analysis.

```bash
# Pick from an interactive numbered list
uv run python -m visualizer.replay

# Replay the most recent log automatically
uv run python -m visualizer.replay --latest

# Replay a specific file
uv run python -m visualizer.replay ~/.tradingagents/visualizer_events/2026-06-27T04-03-33_NVDA.jsonl

# Speed options (same as simulate.py)
uv run python -m visualizer.replay --latest --speed 2   # 2× faster
uv run python -m visualizer.replay --latest --fast       # 4× faster

# Use an alternate port if 7842 is busy
uv run python -m visualizer.replay --latest --port 7843
```

`handoff` events are automatically skipped during replay: the bridge re-derives them
from consecutive `agent_active` events, so replaying them directly would produce
duplicates in the animation.

---

## Running alongside a live analysis

No extra steps needed beyond installing the requirements. Just run the CLI as normal:

```bash
python -m cli.main
```

The browser tab opens before the interactive prompts appear. Fill in the ticker, date, and
model config in the terminal as usual — the office will activate and the animations will
follow the real LangGraph execution automatically.
