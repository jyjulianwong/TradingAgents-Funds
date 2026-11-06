"""US macro regime context for fund runs (fork-specific).

The Fund Analyst fetches the Market Regime Detector's latest All Weather
nowcast once per live fund run and stores the rendered block on
``state["jyjw_mrd_report"]``. Only the investment debate (Bull, Bear and
the Research Manager) reads it, through ``get_jyjw_mrd_instruction``; the
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


def _feature_value(value: Any, description: str) -> str:
    """Format a model feature by what its description says it measures.

    "% change" features arrive as fractions (0.0096 is 0.96%), so they are
    shown as signed percentages; other changes are signed; levels are plain.
    """
    if not isinstance(value, int | float):
        return "n/a"
    text = description.lower()
    if "% change" in text:
        return f"{value:+.2%}"
    if "change" in text:
        return f"{value:+,.4g}"
    return f"{value:,.4g}"


def _cell(value: Any) -> str:
    return str(value if value is not None else "n/a").replace("|", "/").replace("\n", " ")


def render_jyjw_mrd_block(payload: Mapping[str, Any]) -> str:
    """Render a ``LatestPredictionResponse`` payload as a compact markdown block.

    Shows ``latest.features``, the trend transforms the model actually reads
    (3-month changes, momentum, spreads), each with its description; the raw
    ``latest.data`` levels are left out, since a level alone says little about
    the direction of growth or inflation.
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

    features = [row for row in latest.get("features") or [] if isinstance(row, Mapping)]
    if features:
        lines.extend(
            [
                "",
                "Latest US macro trend features the regime model reads (each description"
                " says whether it signals growth or inflation):",
                "",
                "| Feature | Description | Value | Date |",
                "| --- | --- | --- | --- |",
            ]
        )
        lines.extend(
            f"| {_cell(row.get('name'))} | {_cell(row.get('description'))}"
            f" | {_feature_value(row.get('value'), str(row.get('description') or ''))}"
            f" | {_cell(row.get('date'))} |"
            for row in features
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


def jyjw_mrd_source_note(payload: Mapping[str, Any], model_name: str) -> str:
    """One-line note naming the regime used, for the Fund Analyst's report.

    The full block is saved on its own (``jyjw_mrd.md``), so the fund report
    only records the headline.
    """
    latest = payload.get("latest") or {}
    regime = str(latest.get("regime", "UNKNOWN"))
    stale = ", STALE" if payload.get("is_stale") else ""
    return (
        f"**US macro regime**: `{regime}` (confidence {_pct(latest.get('confidence'))}{stale};"
        f" as of {payload.get('asof', 'n/a')}, model `{model_name}`),"
        " passed to the investment debate."
    )


def jyjw_mrd_unavailable_note(reason: str) -> str:
    """One-line block recorded when the regime could not be fetched for a live run."""
    return f"**US MACRO REGIME**: unavailable for this run ({reason})."


def get_jyjw_mrd_instruction(state: Mapping[str, Any] | None) -> str:
    """Return the US macro regime block for a debate prompt, or ``""``.

    Empty for non-fund runs, historical runs, and states the Fund Analyst
    has not populated, so it is safe to append unconditionally.
    """
    report = (state or {}).get("jyjw_mrd_report")
    if not isinstance(report, str) or not report.strip():
        return ""
    return f"\n\n{report}"
