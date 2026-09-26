"""Shared Markdown post-processing for agent-generated report text.

Every renderer this project displays reports through — Rich's ``Markdown``
in the CLI, ``marked.js`` in the dashboard, and GitHub-flavored Markdown
viewers in general — only recognizes a pipe table when its header row is
preceded by a blank line (or is the very first line of the document). A
table whose header row directly follows a non-blank line (e.g. a lead-in
line like "Top holdings:" with no blank line after it) renders as a raw
pipe-delimited paragraph instead of a table.

This bug was first found and fixed in the Fund Analyst's data-fetch
formatting (``dataflows/hl_fund.py``), where a lead-in line was immediately
followed by a table header with no blank line between them. LLM-generated
report text is equally prone to it — models are inconsistent about leaving
a blank line before a table they write — so every agent that asks its LLM
to produce a report (optionally including a Markdown table) should
normalize its output through here before the text is stored in state.
"""

from __future__ import annotations

_TABLE_ROW_CHARS = set("-|: ")


def _is_table_separator_row(line: str) -> bool:
    """True for a GFM table's header-separator row, e.g. ``---- | ----:``."""
    stripped = line.strip()
    if not stripped or "-" not in stripped or "|" not in stripped:
        return False
    return set(stripped) <= _TABLE_ROW_CHARS


def ensure_blank_line_before_tables(text: str) -> str:
    """Insert a blank line before any Markdown table that is missing one.

    A line is treated as a table's header row when the line right after it
    is a valid separator row (``---|---``-style). If such a header row
    directly follows a non-blank line, a blank line is inserted between
    them. Text with no tables, or tables that already have a blank line
    before them, passes through unchanged.
    """
    if not text:
        return text
    lines = text.split("\n")
    out: list[str] = []
    for i, line in enumerate(lines):
        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        is_table_header = "|" in line and _is_table_separator_row(next_line)
        if is_table_header and out and out[-1].strip() != "":
            out.append("")
        out.append(line)
    return "\n".join(out)
