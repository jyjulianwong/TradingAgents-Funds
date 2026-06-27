"""Thread-safe event bus between the CLI thread and the FastAPI WebSocket server.

The CLI thread calls emit() to broadcast events.  The FastAPI server registers
its asyncio event loop via set_server_loop() so that emit() can safely
schedule broadcasts from the CLI thread into that loop.

Event logging
-------------
Every event that passes through emit() — including auto-derived handoff events —
is appended as a JSON line to a timestamped file under
~/.tradingagents/visualizer_events/.  A new file is opened on each
workflow_start so each analysis run produces its own log.

Log filename: <YYYY-MM-DDTHH-MM-SS>[_<TICKER>].jsonl
Log format (one object per line):
    {"ts": "<ISO-8601 ms>", "event": {<event dict>}}
"""

import asyncio
import datetime
import json
import pathlib
from typing import Any

_ws_queues: list[asyncio.Queue] = []
_server_loop: asyncio.AbstractEventLoop | None = None
_current_agent: str | None = None

# Agents that are concurrently active alongside other agents (e.g. research
# team debate members).  They can receive handoffs (other agents walk TO them)
# but they never initiate one: they are excluded from _current_agent tracking
# so that their agent_active events do not trigger spurious handoff animations
# or prematurely remove thinking clouds from their teammates.
_HANDOFF_DISABLED: frozenset[str] = frozenset(
    {"Bull Researcher", "Bear Researcher", "Research Manager"}
)

# ── Event log ────────────────────────────────────────────────────────────────

_LOG_DIR = pathlib.Path.home() / ".tradingagents" / "visualizer_events"
_log_file: "Any | None" = None  # open file handle, or None if no run active


def _open_run_log(ticker: str = "", date: str = "") -> None:
    """Close any existing log and open a fresh one for a new run."""
    global _log_file
    if _log_file is not None:
        try:
            _log_file.flush()
            _log_file.close()
        except OSError:
            pass
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    suffix = f"_{ticker.upper()}" if ticker else ""
    path = _LOG_DIR / f"{ts}{suffix}.jsonl"
    _log_file = path.open("w", encoding="utf-8")


def _append_log(event: dict[str, Any]) -> None:
    """Append a single event to the current run's log file."""
    if _log_file is None:
        return
    try:
        entry = {
            "ts": datetime.datetime.now().isoformat(timespec="milliseconds"),
            "event": event,
        }
        _log_file.write(json.dumps(entry) + "\n")
    except OSError:
        pass


# ── Public API ───────────────────────────────────────────────────────────────

def set_server_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _server_loop
    _server_loop = loop


def emit(event: dict[str, Any]) -> None:
    """Emit an event from the CLI thread to all connected WebSocket clients.

    If two consecutive agent_active events arrive for different agents, a
    handoff event is automatically inserted between them so the browser can
    animate the document-passing walk.

    All events (including auto-derived handoffs) are written to the run log.
    A new log file is opened whenever a workflow_start event is received.
    """
    global _current_agent

    events_to_send: list[dict[str, Any]] = []

    if event.get("type") == "agent_active":
        new_agent = event["agent"]
        if new_agent not in _HANDOFF_DISABLED:
            if _current_agent and _current_agent != new_agent:
                events_to_send.append({"type": "handoff", "from": _current_agent, "to": new_agent})
            _current_agent = new_agent
        # Handoff-disabled agents (research team) are active concurrently with
        # others.  Skip _current_agent update so they never initiate a handoff.

    elif event.get("type") in ("workflow_idle", "workflow_complete"):
        _current_agent = None

    events_to_send.append(event)

    # Open a fresh log file at the start of each run so every analysis run
    # gets its own timestamped file.
    if event.get("type") == "workflow_start":
        _open_run_log(
            ticker=event.get("ticker", ""),
            date=event.get("date", ""),
        )

    for e in events_to_send:
        _append_log(e)

    if _server_loop and not _server_loop.is_closed():
        for e in events_to_send:
            _server_loop.call_soon_threadsafe(_broadcast_in_loop, e)


# ── Internal ─────────────────────────────────────────────────────────────────

def _broadcast_in_loop(event: dict[str, Any]) -> None:
    """Called inside the FastAPI asyncio event loop to fanout to all WS queues."""
    for q in list(_ws_queues):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _ws_queues.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    try:
        _ws_queues.remove(q)
    except ValueError:
        pass
