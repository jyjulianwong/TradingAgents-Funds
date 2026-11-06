"""US macro regime context for fund runs (fork-specific).

The Fund Analyst fetches the Market Regime Detector's latest All Weather
nowcast once per live fund run and stores the rendered block on
``state["macro_regime_report"]``. Only the investment debate (Bull, Bear and
the Research Manager) reads it, through ``get_macro_regime_instruction``; the
analysts never see it, so their reports stay about the instrument itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tradingagents.agents.markdown import ensure_blank_line_before_tables

_QUADRANT_LABELS = {
    "GROWTH_UP_INFLATION_DOWN": "Rising growth, falling inflation (goldilocks)",
    "GROWTH_UP_INFLATION_UP": "Rising growth, rising inflation (reflation / overheating)",
    "GROWTH_DOWN_INFLATION_UP": "Falling growth, rising inflation (stagflation)",
    "GROWTH_DOWN_INFLATION_DOWN": "Falling growth, falling inflation (deflationary slowdown)",
}

# Typical All Weather tendencies per quadrant: (tends to benefit, tends to suffer).
_QUADRANT_TENDENCIES = {
    "GROWTH_UP_INFLATION_DOWN": (
        "equities broadly, especially long-duration growth (technology, consumer "
        "discretionary); corporate credit; nominal bonds hold up",
        "commodities and energy; defensives lag the market",
    ),
    "GROWTH_UP_INFLATION_UP": (
        "commodities, energy, materials, industrials, financials, value/cyclicals, "
        "emerging markets",
        "long-duration nominal bonds; long-duration growth stocks (rate-sensitive)",
    ),
    "GROWTH_DOWN_INFLATION_UP": (
        "commodities, gold, inflation-linked bonds, energy",
        "equities broadly, especially consumer discretionary and long-duration "
        "growth; nominal bonds",
    ),
    "GROWTH_DOWN_INFLATION_DOWN": (
        "long-duration nominal government bonds; defensives (utilities, consumer "
        "staples, healthcare); quality",
        "cyclicals, commodities, energy, financials, small caps",
    ),
}


def _pct(value: Any) -> str:
    return f"{value:.0%}" if isinstance(value, int | float) else "n/a"


def _number(value: Any) -> str:
    if not isinstance(value, int | float):
        return "n/a"
    return f"{value:,.0f}" if abs(value) >= 1000 else f"{value:.4g}"


def _cell(value: Any) -> str:
    return str(value if value is not None else "n/a").replace("|", "/").replace("\n", " ")


def render_regime_block(payload: Mapping[str, Any]) -> str:
    """Render a ``LatestPredictionResponse`` payload as a compact markdown block.

    Leaves out ``latest.features`` (the model's transformed inputs); the raw
    ``latest.data`` series carry the same information in readable units.
    """
    latest = payload.get("latest") or {}
    regime = str(latest.get("regime", "UNKNOWN"))
    quadrants = latest.get("quadrants") or {}

    lines = [
        "**US MACRO REGIME (All Weather nowcast, Market Regime Detector):**",
        "This is macroeconomic data specific to the United States. Use it as the"
        " macro backdrop for the proxy tickers and the fund's sectors; for exposure"
        " outside the US, treat it as an indirect signal through global demand,"
        " US rates and the US dollar, not as a description of local conditions.",
        "",
        f"- **Regime**: `{regime}` — {_QUADRANT_LABELS.get(regime, 'unrecognised quadrant')}",
        f"- **Confidence**: {_pct(latest.get('confidence'))}"
        f" (P(growth up) {_pct(latest.get('p_growth_up'))},"
        f" P(inflation up) {_pct(latest.get('p_inflation_up'))})",
        "- **Quadrant probabilities**: "
        + ", ".join(f"{name} {_pct(quadrants.get(name))}" for name in _QUADRANT_LABELS),
        f"- **As of**: {payload.get('asof', 'n/a')}"
        f" (latest observation {payload.get('observation_date') or 'n/a'})",
    ]
    if payload.get("is_stale"):
        lines.append("- **Warning**: this nowcast is STALE; weight it accordingly.")
    lines.extend(f"- **Warning**: {_cell(w)}" for w in payload.get("warnings") or [])

    data = latest.get("data") or []
    if data:
        lines.extend(
            [
                "",
                "Latest US macro data:",
                "",
                "| Series | Description | Value | Date |",
                "| --- | --- | --- | --- |",
            ]
        )
        lines.extend(
            f"| {_cell(row.get('name'))} | {_cell(row.get('description'))}"
            f" | {_number(row.get('value'))} | {_cell(row.get('date'))} |"
            for row in data
            if isinstance(row, Mapping)
        )

    lines.extend(
        ["", "Typical asset-class and sector tendencies by quadrant (tendencies, not rules):"]
    )
    for name, (benefit, suffer) in _QUADRANT_TENDENCIES.items():
        marker = " ← current" if name == regime else ""
        lines.append(f"- `{name}`{marker}: tends to benefit {benefit}; tends to suffer {suffer}.")

    lines.extend(
        [
            "",
            "Weigh how sensitive each proxy ticker's sector, and the fund as a whole,"
            " is to this regime and to a shift towards the next most likely quadrant."
            " Treat it as one input alongside the analyst reports, and say explicitly"
            " where the regime strengthens or weakens your argument.",
        ]
    )
    return ensure_blank_line_before_tables("\n".join(lines))


def regime_unavailable_note(reason: str) -> str:
    """One-line block recorded when the regime could not be fetched for a live run."""
    return f"**US MACRO REGIME**: unavailable for this run ({reason})."


def get_macro_regime_instruction(state: Mapping[str, Any] | None) -> str:
    """Return the US macro regime block for a debate prompt, or ``""``.

    Empty for non-fund runs, historical runs, and states the Fund Analyst
    has not populated, so it is safe to append unconditionally.
    """
    report = (state or {}).get("macro_regime_report")
    if not isinstance(report, str) or not report.strip():
        return ""
    return f"\n\n{report}"
