"""Fork-only report pieces for fund runs (kept out of ``reporting.py``)."""


def proxy_banner(final_state: dict, ticker: str) -> str:
    """Render a top-of-report callout naming the instruments actually analyzed.

    A fund ISIN has no tradeable price/volume/fundamentals of its own, so
    every downstream analyst, debater, and the final rating are computed
    against Fund Analyst-resolved proxy tickers instead — see fund_analyst.py.
    That substitution is easy to miss buried inside the analyst section, so
    surface it immediately after the title instead of relying on a reader to
    dig through "I. Analyst Team Reports" to find it.
    """
    if not final_state.get("fund_report"):
        return ""
    proxy_tickers = final_state.get("fund_proxy_tickers") or []
    if not proxy_tickers:
        return (
            f"> **Proxy instruments analyzed**: none found — downstream analysis "
            f"for `{ticker}` may be limited or absent.\n\n"
        )
    proxy_source = final_state.get("fund_proxy_source") or "unknown"
    return (
        f"> **Proxy instruments analyzed**: {', '.join(proxy_tickers)} "
        f"(source: {proxy_source})\n"
        f">\n"
        f"> `{ticker}` is a fund with no tradeable price/volume/fundamentals of "
        f"its own — every downstream analyst, debate, and the final rating "
        f"below are based on these proxy tickers standing in for it, not the "
        f"fund itself. See the Fund Analyst section for the full rationale.\n\n"
    )
