"""Market Regime Detector client — the latest US All Weather regime nowcast (fork-specific).

The Market Regime Detector is a separate, read-only API that nowcasts the
Bridgewater All Weather quadrant (growth x inflation) from US macro series.
Only the ``/latest`` endpoint is used: it always describes *today*, so the
Fund Analyst calls it for live runs only (see ``fund_analyst.py``).
"""

from __future__ import annotations

import requests

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.net import get_scrubbed

_TIMEOUT_SECONDS = 15.0


class JyjwMrdUnavailableError(VendorUnavailableError):
    """The Market Regime Detector could not answer, or answered with an unusable body."""


def fetch_jyjw_mrd_latest(base_url: str, model_name: str) -> dict:
    """Return the ``LatestPredictionResponse`` JSON for ``model_name``.

    Raises ``JyjwMrdUnavailableError`` on any HTTP, network or decoding
    failure, and when the response carries no ``latest`` snapshot.
    """
    url = f"{base_url.rstrip('/')}/v1/models/{model_name}/predictions/latest"
    try:
        payload = get_scrubbed(url, params={}, timeout=_TIMEOUT_SECONDS, secret="").json()
    except (requests.RequestException, ValueError) as exc:
        raise JyjwMrdUnavailableError(f"Market Regime Detector request failed: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("latest"), dict):
        raise JyjwMrdUnavailableError(
            f"Market Regime Detector returned no latest snapshot for model {model_name!r}"
        )
    return payload
