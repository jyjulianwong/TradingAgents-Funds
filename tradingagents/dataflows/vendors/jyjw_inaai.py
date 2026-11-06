"""Investment News Analysis AI client — one dated markdown news report per weekday (fork-specific).

Reports are published as static files at ``{base_url}/reports/{YYYY-MM-DD}/report.md``,
one per weekday. A date with no report (weekend, holiday, or not yet published
today) answers 404 (or 403, which S3 returns for a missing key when listing is
not allowed); that is an absence, not an outage, so it returns ``None``.
"""

from __future__ import annotations

import requests

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.net import get_scrubbed

_TIMEOUT_SECONDS = 15.0
_NOT_PUBLISHED = (403, 404)


class JyjwInaaiUnavailableError(VendorUnavailableError):
    """The news report site could not answer, or answered with an unusable body."""


def jyjw_inaai_url_for(base_url: str, report_date: str) -> str:
    return f"{base_url.rstrip('/')}/reports/{report_date}/report.md"


def fetch_jyjw_inaai_report(base_url: str, report_date: str) -> str | None:
    """Return the markdown report published for ``report_date``, or None if there is none.

    Raises ``JyjwInaaiUnavailableError`` on any other HTTP or network
    failure, and when the body is empty.
    """
    url = jyjw_inaai_url_for(base_url, report_date)
    try:
        response = get_scrubbed(
            url, params={}, timeout=_TIMEOUT_SECONDS, secret="", passthrough=_NOT_PUBLISHED
        )
    except requests.RequestException as exc:
        raise JyjwInaaiUnavailableError(f"news report request failed: {exc}") from exc
    if response.status_code in _NOT_PUBLISHED:
        return None
    # S3 serves text/markdown with no charset, which requests would read as Latin-1.
    text = response.content.decode("utf-8", errors="replace").strip()
    if not text:
        raise JyjwInaaiUnavailableError(f"news report for {report_date} is empty")
    return text
