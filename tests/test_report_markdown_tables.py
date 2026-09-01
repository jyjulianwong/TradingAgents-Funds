"""Tests for the shared Markdown-table blank-line normalizer.

Companion to the Fund Analyst table-rendering fix (``dataflows/hl_fund.py``):
this covers the general-purpose helper in ``agents/utils/markdown.py`` that
every report-producing agent now runs its LLM output through, so a table
whose header row directly follows a non-blank line still renders as a table
instead of a raw pipe-delimited paragraph.
"""

import pytest

from tradingagents.agents.utils.markdown import ensure_blank_line_before_tables


@pytest.mark.unit
class TestEnsureBlankLineBeforeTables:
    def test_inserts_blank_line_when_missing(self):
        text = "Top 10 holdings:\nsecurity_name | weighting_pct\n------------- | -------------\nApple | 5.5%"
        result = ensure_blank_line_before_tables(text)
        assert result == (
            "Top 10 holdings:\n"
            "\n"
            "security_name | weighting_pct\n"
            "------------- | -------------\n"
            "Apple | 5.5%"
        )

    def test_leaves_existing_blank_line_untouched(self):
        text = "Top 10 holdings:\n\nsecurity_name | weighting_pct\n------------- | -------------\nApple | 5.5%"
        assert ensure_blank_line_before_tables(text) == text

    def test_table_at_start_of_document_untouched(self):
        text = "security_name | weighting_pct\n------------- | -------------\nApple | 5.5%"
        assert ensure_blank_line_before_tables(text) == text

    def test_no_table_passes_through_unchanged(self):
        text = "Just some prose.\nWith multiple lines.\nNo tables here."
        assert ensure_blank_line_before_tables(text) == text

    def test_multiple_tables_each_get_a_blank_line(self):
        text = (
            "Summary:\n"
            "signal | source\n"
            "------ | ------\n"
            "Bullish | News\n"
            "Risks:\n"
            "risk | severity\n"
            "---- | --------\n"
            "Rates | High"
        )
        result = ensure_blank_line_before_tables(text)
        lines = result.split("\n")
        assert lines[1] == ""
        assert "risk | severity" in lines
        assert lines[lines.index("risk | severity") - 1] == ""

    def test_empty_string_returns_empty_string(self):
        assert ensure_blank_line_before_tables("") == ""

    def test_pipe_line_without_separator_row_is_not_a_table(self):
        text = "Ratio A|B was discussed.\nNext line."
        assert ensure_blank_line_before_tables(text) == text
