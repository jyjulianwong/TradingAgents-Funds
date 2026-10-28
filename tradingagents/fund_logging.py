"""Silence known third-party warnings that flood a run's output (fork-only).

yfinance still passes ``inplace=True`` to pandas 3 calls that deprecate it, and
emits one warning per call: hundreds per run, none actionable from here. The filter
is limited to that message from yfinance's own modules, so a pandas deprecation raised
by this project's code, or any other library, still shows. Set
``TRADINGAGENTS_SHOW_LIBRARY_WARNINGS=1`` to see them all again.
"""

import os
import warnings

_YFINANCE_INPLACE = r"The inplace keyword in DataFrame\.\w+ is deprecated"


def quiet_library_warnings() -> None:
    """Install the filters, unless ``TRADINGAGENTS_SHOW_LIBRARY_WARNINGS`` is set."""
    if os.environ.get("TRADINGAGENTS_SHOW_LIBRARY_WARNINGS", "").strip().lower() in {"1", "true", "yes"}:
        return
    warnings.filterwarnings(
        "ignore", message=_YFINANCE_INPLACE, category=DeprecationWarning, module=r"yfinance(\..*)?$"
    )
