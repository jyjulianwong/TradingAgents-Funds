"""The yfinance deprecation-warning filter (fork-only, see tradingagents/fund_logging.py)."""

import warnings

import pytest

from tradingagents.fund_logging import quiet_library_warnings

MESSAGE = "The inplace keyword in DataFrame.sort_index is deprecated and will be removed in a future version (PDEP-8)."


def _emit(module: str, message: str = MESSAGE) -> list:
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        quiet_library_warnings()
        warnings.warn_explicit(message, DeprecationWarning, filename=f"{module}.py", lineno=1, module=module)
    return seen


@pytest.mark.unit
def test_yfinance_inplace_warnings_are_silenced(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_SHOW_LIBRARY_WARNINGS", raising=False)
    assert _emit("yfinance.utils") == []


@pytest.mark.unit
def test_the_same_warning_from_other_code_still_shows(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_SHOW_LIBRARY_WARNINGS", raising=False)
    assert len(_emit("tradingagents.somewhere")) == 1


@pytest.mark.unit
def test_other_yfinance_warnings_still_show(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_SHOW_LIBRARY_WARNINGS", raising=False)
    assert len(_emit("yfinance.utils", "something else is deprecated")) == 1


@pytest.mark.unit
def test_the_env_switch_restores_the_warnings(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_SHOW_LIBRARY_WARNINGS", "1")
    assert len(_emit("yfinance.utils")) == 1
