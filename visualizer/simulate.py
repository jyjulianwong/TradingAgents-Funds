"""Simulate a TradingAgents run and stream events to the Visualizer.

Lets you preview every animation phase — out-of-hours office, analyst typing,
handoff walks, thinking clouds, debate rounds, and the final BUY/SELL/HOLD
result — without spending a single LLM token.

Usage
-----
    uv run python -m visualizer.simulate
    uv run python -m visualizer.simulate --ticker TSLA --signal SELL
    uv run python -m visualizer.simulate --fast
    uv run python -m visualizer.simulate --speed 2 --debate-rounds 3

Options
-------
    --ticker TEXT       Ticker to display on the LED board        [NVDA]
    --date  TEXT        Analysis date (YYYY-MM-DD)                [today]
    --signal TEXT       Final rating: BUY | HOLD | SELL           [BUY]
    --speed FLOAT       Playback speed multiplier                  [1.0]
    --fast              Shortcut for --speed 4
    --debate-rounds N   Bull/Bear and risk debate rounds           [2]
    --port INT          Visualizer server port                     [7842]
"""

import argparse
import datetime
import sys
import time
import webbrowser


# ─── ANSI helpers ─────────────────────────────────────────────────────────────

_NO_COLOR = not sys.stdout.isatty()

def _c(code, text):
    return text if _NO_COLOR else f"\033[{code}m{text}\033[0m"

dim    = lambda t: _c("2",   t)
bold   = lambda t: _c("1",   t)
green  = lambda t: _c("92",  t)
red    = lambda t: _c("91",  t)
yellow = lambda t: _c("93",  t)
cyan   = lambda t: _c("96",  t)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulate a TradingAgents run for the Visualizer (no LLM calls).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--ticker",        default="NVDA",  metavar="SYMBOL",
                        help="Ticker symbol shown on the LED board (default: NVDA)")
    parser.add_argument("--date",          default=None,    metavar="YYYY-MM-DD",
                        help="Analysis date (default: today)")
    parser.add_argument("--signal",        default="BUY",
                        choices=["BUY", "HOLD", "SELL"],
                        help="Final rating to display when complete (default: BUY)")
    parser.add_argument("--speed",         default=1.0,     type=float, metavar="N",
                        help="Playback speed multiplier — 2 = twice as fast (default: 1.0)")
    parser.add_argument("--fast",          action="store_true",
                        help="Shortcut for --speed 4")
    parser.add_argument("--debate-rounds", default=2,       type=int,   metavar="N",
                        help="Number of Bull/Bear and risk debate rounds (default: 2)")
    parser.add_argument("--port",          default=7842,    type=int,
                        help="Port for the visualizer server (default: 7842)")
    args = parser.parse_args()

    speed  = args.speed * (4.0 if args.fast else 1.0)
    ticker = args.ticker.upper()
    date   = args.date or datetime.date.today().strftime("%Y-%m-%d")
    signal = args.signal.upper()
    rounds = max(1, args.debate_rounds)

    # ── Start server ──────────────────────────────────────────────────────────
    from visualizer import bridge, server as viz_server  # noqa: PLC0415

    port = viz_server.start(port=args.port)
    url  = f"http://127.0.0.1:{port}"

    print()
    print(bold("  TradingAgents Visualizer — Simulation"))
    print(dim("  ──────────────────────────────────────"))
    print(f"  {dim('URL   :')} {cyan(url)}")
    print(f"  {dim('Ticker:')} {bold(ticker)}   {dim('Date:')} {date}   "
          f"{dim('Signal:')} {bold(signal)}   {dim('Speed:')} {speed:.1f}×")
    print(f"  {dim('Debate rounds:')} {rounds}")
    print()

    webbrowser.open_new_tab(url)

    # ── Wait for a browser client to connect ──────────────────────────────────
    print(dim("  Waiting for browser to connect…"))
    deadline = time.time() + 12
    while time.time() < deadline:
        if bridge._ws_queues:
            break
        time.sleep(0.2)
    else:
        print(dim("  (no client connected yet — continuing anyway)"))

    # Small grace period so the browser finishes rendering the loading screen.
    time.sleep(max(0.6, 1.5 / speed))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def wait(seconds: float, note: str = "") -> None:
        if note:
            print(dim(f"        {note}"))
        time.sleep(seconds / speed)

    def activate(agent: str) -> None:
        """Emit agent_active; bridge auto-derives the handoff from the previous agent."""
        bridge.emit({"type": "agent_active", "agent": agent})
        print(f"  {cyan('▶')}  {bold(agent)}")

    def message(agent: str, text: str) -> None:
        """Emit an agent_message event to populate the dialog box."""
        bridge.emit({"type": "agent_message", "agent": agent, "text": text})

    # ── Workflow start ─────────────────────────────────────────────────────────
    print(f"\n  {green('[OFFICE LIGHTS ON]')}  —  ticker: {bold(ticker)}")
    bridge.emit({"type": "workflow_start", "ticker": ticker, "date": date})
    wait(1.2)

    # ── Analyst team ──────────────────────────────────────────────────────────
    print(f"\n  {dim('── Analyst Team')} {'─'*35}")
    analyst_specs = [
        (
            "Market Analyst", 5.5, "Fetching OHLCV, computing RSI/MACD/BB…",
            [
                (1.2, f"Fetching 365 days of OHLCV data for {ticker}…\nRetrieved daily bars from Yahoo Finance."),
                (2.5, f"RSI(14): 67.3 — approaching overbought territory\n"
                      f"MACD: 2.45 > signal 1.87, bullish crossover confirmed\n"
                      f"Bollinger Bands: price at upper band (+1.9σ)\n"
                      f"Volume: +34% above 20-day average on breakout session"),
                (4.2, f"Technical summary for {ticker}: Momentum indicators are bullish "
                      f"with RSI trending upward but not yet in overbought territory. "
                      f"MACD crossover suggests continuation of the current uptrend. "
                      f"Support level identified at the 50-day SMA ($421.80)."),
            ],
        ),
        (
            "Sentiment Analyst", 4.5, "Reading Reddit & StockTwits posts…",
            [
                (1.0, f"Fetching recent posts from r/wallstreetbets, r/stocks, r/investing…\n"
                      f"Scanning StockTwits feed for ${ticker} mentions…"),
                (2.8, f"Social sentiment analysis ({ticker}):\n"
                      f"  Reddit — 847 mentions (↑ 23% vs. prior week), sentiment: 68% bullish\n"
                      f"  StockTwits — 312 posts, Bull/Bear ratio: 2.4:1\n"
                      f"  Key themes: AI chip demand, data centre buildout, earnings beat"),
            ],
        ),
        (
            "News Analyst", 5.0, "Scanning news, FRED macro, Polymarket…",
            [
                (1.3, f"Scanning news headlines for {ticker} (last 7 days)…\n"
                      f"Fetching FRED macro indicators: Fed Funds Rate, CPI, GDP…\n"
                      f"Querying Polymarket for relevant prediction markets…"),
                (3.5, f"Key news events:\n"
                      f"  • Earnings beat: EPS $5.16 vs. $4.59 consensus (+12.4%)\n"
                      f"  • New data-centre partnership announced with major hyperscaler\n"
                      f"  • Morgan Stanley raises PT to $950; reiterates Overweight\n\n"
                      f"Macro context: Fed held rates steady; CPI softening to 3.1% YoY. "
                      f"Risk-on environment supportive of growth equities."),
            ],
        ),
        (
            "Fundamentals Analyst", 5.5, "Pulling income statement, balance sheet…",
            [
                (1.5, f"Fetching financial statements for {ticker}…\n"
                      f"Income statement, balance sheet, cash flow (TTM + 4 quarters)"),
                (3.8, f"Fundamental snapshot ({ticker}):\n"
                      f"  Revenue: $44.1B TTM (+122% YoY)   Gross margin: 74.3%\n"
                      f"  Operating income: $18.6B           P/E (fwd): 35.2×\n"
                      f"  Free cash flow: $14.9B             Net debt: −$8.1B (net cash)\n"
                      f"  ROIC: 47.8%  —  exceptional capital efficiency"),
            ],
        ),
    ]
    for agent, dur, note, msg_seq in analyst_specs:
        activate(agent)
        elapsed = 0.0
        for delay, text in msg_seq:
            wait(delay - elapsed, note if elapsed == 0 else "")
            elapsed = delay
            message(agent, text)
        wait(dur - elapsed)

    # ── Research debate ────────────────────────────────────────────────────────
    print(f"\n  {dim('── Research Debate')} ({rounds} round{'s' if rounds > 1 else ''}) {'─'*26}")
    for rnd in range(1, rounds + 1):
        print(dim(f"    Round {rnd}:"))
        activate("Bull Researcher")
        wait(1.2, "Constructing bull case from analyst reports…")
        message("Bull Researcher",
                f"[Round {rnd}] Bull case for {ticker}:\n"
                f"The technical breakout above the 52-week high, combined with a 122% "
                f"YoY revenue surge and strong free-cash-flow generation, makes a "
                f"compelling upside argument. Insider ownership is high, and the "
                f"forward P/E of 35× is justified by the AI infrastructure supercycle.")
        wait(1.6)
        activate("Bear Researcher")
        wait(1.2, "Countering with bear thesis…")
        message("Bear Researcher",
                f"[Round {rnd}] Bear case for {ticker}:\n"
                f"Valuation at 35× forward earnings prices in near-perfection. "
                f"Export restrictions on advanced chips to China could dent 20–25% of "
                f"revenues. RSI approaching overbought at 67 suggests near-term "
                f"consolidation risk. Capex cycle pull-forward may compress margins.")
        wait(1.6)

    print(dim("    → Research Manager adjudicates"))
    activate("Research Manager")
    wait(1.2, "Synthesising bull/bear arguments into a verdict…")
    message("Research Manager",
            f"Verdict: The bull case prevails on a 12-month horizon. Revenue growth and "
            f"margin expansion outweigh near-term valuation concerns. Export risk is real "
            f"but management has demonstrated supply-chain agility. Recommend LONG with "
            f"a stop-loss at the 50-day SMA. Risk/reward favours buyers at current levels.")
    wait(1.3)

    # ── Trading desk ──────────────────────────────────────────────────────────
    print(f"\n  {dim('── Trading Desk')} {'─'*37}")
    activate("Trader")
    wait(1.4, "Formulating trade proposal with sizing & entry…")
    message("Trader",
            f"Trade proposal — {ticker}:\n"
            f"  Action: BUY\n"
            f"  Entry: market open, limit $487.50\n"
            f"  Position size: 2.5% of AUM\n"
            f"  Target: $560 (12-month, +15%)\n"
            f"  Stop-loss: $441 (50-day SMA, −10%)\n"
            f"  Rationale: Strong fundamental and technical confluence; "
            f"risk/reward 1.5:1 at current price.")
    wait(1.4)

    # ── Risk management debate ─────────────────────────────────────────────────
    print(f"\n  {dim('── Risk Management')} ({rounds} round{'s' if rounds > 1 else ''}) {'─'*25}")
    risk_specs = [
        ("Aggressive Analyst",   1.8, "Stress-testing upside scenario…",
         f"Upside scenario: AI adoption accelerates beyond consensus. "
         f"Data-centre spend from hyperscalers could push revenues to $60B+ next year. "
         f"Recommend a 3.5% position — the asymmetric payoff justifies above-average sizing."),
        ("Conservative Analyst", 1.8, "Evaluating tail risks & drawdown…",
         f"Tail-risk assessment: A 20-25% China revenue headwind from export controls "
         f"represents the primary downside. Elevated valuation leaves little margin of "
         f"safety. Cap position at 1.5% of AUM; set stop-loss firmly at 50-day SMA."),
        ("Neutral Analyst",      1.8, "Balancing risk vs reward…",
         f"Balanced view: Fundamental thesis is solid but near-term catalysts are largely "
         f"priced in. A 2.5% position with a trailing stop balances participation in the "
         f"AI upcycle with prudent downside protection. Review on next earnings release."),
    ]
    for rnd in range(1, rounds + 1):
        print(dim(f"    Round {rnd}:"))
        for agent, dur, note, msg_text in risk_specs:
            activate(agent)
            wait(0.9, note)
            message(agent, f"[Round {rnd}] " + msg_text)
            wait(0.9)

    # ── Portfolio Manager ──────────────────────────────────────────────────────
    print(f"\n  {dim('── Portfolio Management')} {'─'*30}")
    activate("Portfolio Manager")
    wait(1.6, "Consolidating all reports into final 5-tier rating…")
    message("Portfolio Manager",
            f"Final assessment — {ticker}:\n"
            f"All four analyst reports, the research team debate, and risk management "
            f"review have been synthesised. The bull case is corroborated by strong "
            f"fundamentals and positive technical momentum. Risk team agrees on a 2.5% "
            f"position size with a defined stop.\n\n"
            f"Rating: {signal}  |  Confidence: High\n"
            f"Price target: $560 (12-month)  |  Stop-loss: $441")
    wait(1.6)

    # ── Completion ────────────────────────────────────────────────────────────
    sig_display = {
        "BUY":  green(f"★  BUY  ★"),
        "SELL": red(  f"★  SELL  ★"),
        "HOLD": yellow(f"★  HOLD  ★"),
    }.get(signal, bold(signal))
    print(f"\n  {dim('── Complete')} {'─'*41}")
    print(f"  {sig_display}  ({ticker})")

    bridge.emit({"type": "workflow_complete", "signal": signal, "ticker": ticker})

    print()
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
