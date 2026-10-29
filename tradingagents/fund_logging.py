"""Silence known third-party warnings that flood a run's output (fork-only).

yfinance still passes ``inplace=True`` to pandas 3 calls that deprecate it, and
emits one warning per call: hundreds per run, none actionable from here. The filter
is limited to that message from yfinance's own modules, so a pandas deprecation raised
by this project's code, or any other library, still shows. Set
``TRADINGAGENTS_SHOW_LIBRARY_WARNINGS=1`` to see them all again.

yfinance's own ``__init__.py`` installs ``filterwarnings('default',
category=DeprecationWarning, module='^yfinance')`` the first time it is imported.
``filterwarnings`` inserts at the front of ``warnings.filters`` by default, so
whichever of the two filters is installed *second* wins (first-match-wins list,
most recent insert at the front). Called once at ``tradingagents`` import time,
this filter is installed *before* yfinance ever is (yfinance is only imported
later, lazily, by the data layer), so yfinance's own filter ends up in front and
shadows this one. ``quiet_library_warnings()`` is called again from
``tradingagents/dataflows/vendors/yahoo/common.py``, right after its
``import yfinance``, to re-install this filter in front of yfinance's.
"""

import os
import warnings

_YFINANCE_INPLACE = r"The inplace keyword in DataFrame\.\w+ is deprecated"


def quiet_library_warnings() -> None:
    """Install the filters, unless ``TRADINGAGENTS_SHOW_LIBRARY_WARNINGS`` is set."""
    if os.environ.get("TRADINGAGENTS_SHOW_LIBRARY_WARNINGS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return
    warnings.filterwarnings(
        "ignore", message=_YFINANCE_INPLACE, category=DeprecationWarning, module=r"yfinance(\..*)?$"
    )
