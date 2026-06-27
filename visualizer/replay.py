"""Replay a recorded Visualizer event log back through the browser animation.

Reads a JSONL log produced by visualizer/bridge.py and re-emits every
event with the original inter-event timing (optionally scaled).  Use this
to verify animation correctness without running a live LLM analysis.

`handoff` events are skipped: bridge.py re-derives them automatically from
consecutive `agent_active` events, so replaying them directly would produce
duplicates.

Usage
-----
    uv run python -m visualizer.replay                         # pick from list
    uv run python -m visualizer.replay path/to/run.jsonl
    uv run python -m visualizer.replay --latest                # newest log
    uv run python -m visualizer.replay --latest --speed 2      # 2× faster
    uv run python -m visualizer.replay --latest --fast         # 4× faster
    uv run python -m visualizer.replay --port 7843             # alternate port
"""

import argparse
import datetime
import json
import pathlib
import sys
import time
import webbrowser

# ─── ANSI helpers ─────────────────────────────────────────────────────────────

_NO_COLOR = not sys.stdout.isatty()

def _c(code, text):
    return text if _NO_COLOR else f"\033[{code}m{text}\033[0m"


def dim(t):    return _c("2",  t)
def bold(t):   return _c("1",  t)
def green(t):  return _c("92", t)
def red(t):    return _c("91", t)
def yellow(t): return _c("93", t)
def cyan(t):   return _c("96", t)

# ─── Log discovery ────────────────────────────────────────────────────────────

_LOG_DIR = pathlib.Path.home() / ".tradingagents" / "visualizer_events"


def _list_logs() -> list[pathlib.Path]:
    """Return all .jsonl files in the log dir, newest first."""
    if not _LOG_DIR.exists():
        return []
    return sorted(_LOG_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


def _pick_log_interactively() -> pathlib.Path:
    """Print numbered menu and return the chosen path."""
    logs = _list_logs()
    if not logs:
        print(red("  No event logs found in") + f" {_LOG_DIR}")
        print(dim("  Run a live analysis or `visualizer.simulate` first to generate one."))
        sys.exit(1)

    print()
    print(bold("  Available event logs:"))
    print(dim("  " + "─" * 50))
    for i, p in enumerate(logs, 1):
        size_kb = p.stat().st_size / 1024
        mtime   = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {cyan(str(i)):>5}  {p.name:<45} {dim(f'{size_kb:5.1f} KB  {mtime}')}")
    print()

    while True:
        try:
            raw = input(f"  Select log [1–{len(logs)}]: ").strip()
            idx = int(raw) - 1
            if 0 <= idx < len(logs):
                return logs[idx]
        except (ValueError, KeyboardInterrupt):
            pass
        print(dim(f"  Please enter a number between 1 and {len(logs)}."))


# ─── Parsing ──────────────────────────────────────────────────────────────────

def _parse_log(path: pathlib.Path) -> list[tuple[datetime.datetime, dict]]:
    """Return [(timestamp, event_dict), …] sorted by timestamp."""
    entries: list[tuple[datetime.datetime, dict]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj   = json.loads(line)
                ts    = datetime.datetime.fromisoformat(obj["ts"])
                event = obj["event"]
                entries.append((ts, event))
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                print(dim(f"  [warn] line {lineno}: {exc} — skipped"))
    entries.sort(key=lambda x: x[0])
    return entries


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay a Visualizer event log through the browser animation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "log", nargs="?", default=None, metavar="LOG",
        help="Path to a .jsonl event log (omit to pick interactively)",
    )
    parser.add_argument(
        "--latest", action="store_true",
        help="Auto-select the most recently modified log file",
    )
    parser.add_argument(
        "--speed", default=1.0, type=float, metavar="N",
        help="Playback speed multiplier — 2 = twice as fast (default: 1.0)",
    )
    parser.add_argument(
        "--fast", action="store_true",
        help="Shortcut for --speed 4",
    )
    parser.add_argument(
        "--port", default=7842, type=int,
        help="Port for the visualizer server (default: 7842)",
    )
    args = parser.parse_args()

    speed = args.speed * (4.0 if args.fast else 1.0)

    # Resolve log path
    if args.log:
        log_path = pathlib.Path(args.log).expanduser()
        if not log_path.exists():
            print(red(f"  Log not found: {log_path}"))
            sys.exit(1)
    elif args.latest:
        logs = _list_logs()
        if not logs:
            print(red(f"  No event logs found in {_LOG_DIR}"))
            sys.exit(1)
        log_path = logs[0]
    else:
        log_path = _pick_log_interactively()

    # Parse events
    entries = _parse_log(log_path)
    if not entries:
        print(red("  Log is empty or contains no valid events."))
        sys.exit(1)

    # Filter: skip handoff events — bridge re-derives them from agent_active pairs
    entries = [(ts, ev) for ts, ev in entries if ev.get("type") != "handoff"]

    # Count useful event types for the summary line
    event_counts: dict[str, int] = {}
    for _, ev in entries:
        event_counts[ev.get("type", "?")] = event_counts.get(ev.get("type", "?"), 0) + 1

    total_span = (entries[-1][0] - entries[0][0]).total_seconds() if len(entries) > 1 else 0

    # ── Start server ──────────────────────────────────────────────────────────
    from visualizer import bridge, server as viz_server  # noqa: PLC0415

    port = viz_server.start(port=args.port)
    url  = f"http://127.0.0.1:{port}"

    print()
    print(bold("  TradingAgents Visualizer — Log Replay"))
    print(dim("  ──────────────────────────────────────"))
    print(f"  {dim('Log   :')} {log_path.name}")
    print(f"  {dim('URL   :')} {cyan(url)}")
    events_summary = "  ".join(
        f"{dim(k + ':')} {v}" for k, v in sorted(event_counts.items())
    )
    print(f"  {dim('Events:')} {events_summary}")
    original_dur = f"{total_span:.0f}s"
    replay_dur   = f"{total_span / speed:.0f}s" if speed != 1.0 else ""
    dur_str = f"{original_dur} → {replay_dur}" if replay_dur else original_dur
    print(f"  {dim('Duration:')} {dur_str}   {dim('Speed:')} {speed:.1f}×")
    print()

    webbrowser.open_new_tab(url)

    # ── Wait for a browser client ─────────────────────────────────────────────
    print(dim("  Waiting for browser to connect…"))
    deadline = time.time() + 12
    while time.time() < deadline:
        if bridge._ws_queues:
            break
        time.sleep(0.2)
    else:
        print(dim("  (no client connected — continuing anyway)"))

    time.sleep(max(0.6, 1.5 / speed))

    # ── Replay ────────────────────────────────────────────────────────────────
    print(dim("  Replaying…"))
    print()

    type_icons = {
        "workflow_start":    green("▶ start"),
        "workflow_complete": green("■ done "),
        "agent_active":      cyan( "● active"),
        "agent_idle":        dim(  "○ idle  "),
        "workflow_idle":     dim(  "  idle  "),
    }

    prev_ts: datetime.datetime | None = None
    for ts, event in entries:
        etype = event.get("type", "?")

        # Sleep for the scaled inter-event gap
        if prev_ts is not None:
            gap = (ts - prev_ts).total_seconds()
            if gap > 0:
                time.sleep(gap / speed)
        prev_ts = ts

        bridge.emit(event)

        # Console feedback
        icon  = type_icons.get(etype, dim(f"  {etype:<7}"))
        agent = event.get("agent") or event.get("ticker") or event.get("signal") or ""
        print(f"  {icon}  {bold(agent) if agent else ''}")

    print()
    print(dim("  Replay complete."))
    print(dim(f"  Visualizer still running at {url}"))
    print(dim("  Press Ctrl+C to exit."))
    print()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
