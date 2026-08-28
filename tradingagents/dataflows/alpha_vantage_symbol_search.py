"""Alpha Vantage SYMBOL_SEARCH vendor.

Used to verify a proxy ticker the Fund Analyst has already chosen (via its
own structured-output call) against a live symbol database, catching a
hallucinated, mistyped, or delisted ticker before it reaches downstream
analysts. This is a deterministic, Python-orchestrated check — never a tool
the LLM invokes itself. Schema-only structured-output calls bind no tools
(see ``NO_EXTERNAL_TOOLS`` in ``agents/utils/structured.py``), so any lookup
has to happen in plain Python around that call, the same way
``get_fund_fact_sheet`` is fetched deterministically before the Fund
Analyst's structured call runs.
"""

from __future__ import annotations

import json

from .alpha_vantage_common import _make_api_request
from .errors import NoMarketDataError

# Alpha Vantage can return dozens of loosely-related matches for a common
# word; only the top few by matchScore are useful for a verification check
# or for a human skimming the fund report.
_MAX_MATCHES = 10


def get_symbol_matches(query: str) -> str:
    """Look up `query` (a ticker or company name) against Alpha Vantage's
    symbol database, best matches first.

    Raises NoMarketDataError when the vendor call succeeds but returns no
    matches at all — a real "unknown symbol" verdict, not a vendor failure.
    """
    response_text = _make_api_request("SYMBOL_SEARCH", {"keywords": query})
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise NoMarketDataError(
            query, query, "SYMBOL_SEARCH returned a non-JSON response"
        ) from exc

    matches = payload.get("bestMatches") or []
    if not matches:
        raise NoMarketDataError(query, query, "no symbol matches found")

    matches = sorted(matches, key=lambda m: m.get("9. matchScore", "0"), reverse=True)

    lines = [
        f"**Symbol search results for '{query}'**",
        "",
        "symbol | name | type | region | match_score",
        "------ | ---- | ---- | ------ | -----------",
    ]
    for m in matches[:_MAX_MATCHES]:
        lines.append(
            f"{m.get('1. symbol', '—')} | {m.get('2. name', '—')} | "
            f"{m.get('3. type', '—')} | {m.get('4. region', '—')} | "
            f"{m.get('9. matchScore', '—')}"
        )
    return "\n".join(lines)
