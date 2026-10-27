"""Structured-output schema for the Fund Analyst (fork-only; upstream's schemas.py is untouched)."""

from pydantic import BaseModel, Field, field_validator


class FundHoldingsAnalysis(BaseModel):
    """Structured proxy-ticker selection produced by the Fund Analyst.

    The Fund Analyst reads a fund's holdings fact sheet (top positions by
    weight) and selects a small set of exchange-traded proxy tickers that
    downstream analysts (Market, Sentiment, Fundamentals) can pull real
    price/volume/fundamentals/social data for, standing in for the fund
    itself (which, as an OEIC/ETF, typically has no tradeable volume or
    corporate financials of its own).
    """

    proxy_tickers: list[str] = Field(
        default_factory=list,
        description=(
            "Ordered list of exchange-traded ticker symbols — aim for 3 to 5, and never "
            "more than 5 (extras beyond the 5th are dropped) — that will best inform "
            "downstream analysts' read on this fund's likely future performance: its "
            "largest individual holdings, and/or a sector, industry, thematic, or index "
            "ticker/ETF when that is a more representative signal of the fund's forward "
            "exposure and intrinsic value than its current top holdings are. Findability "
            "is a narrow tie-breaker only — swap a holding for a well-known large-cap peer "
            "or sector/index ticker solely when that holding is so obscure it would return "
            "essentially no news or social-media coverage on its own, never as a general "
            "preference for bigger or more familiar names; an accurate, moderately-covered "
            "holding should stay, and unrelated funds should not converge on the same "
            "famous tickers just because they are well-known. Fewer than 3 is fine only "
            "when the fund is narrow/concentrated and 3 distinct representative tickers "
            "genuinely don't exist. Empty if the fact sheet does not give enough "
            "information to pick representative tickers; the caller falls back to a static "
            "mapping in that case. Every ticker must be real and one you are genuinely "
            "confident about — never fabricate one, whether holding-derived or thematic."
        ),
    )
    rationale: str = Field(
        default="",
        description=(
            "One or two sentences on why these tickers were chosen — e.g. which top "
            "holdings or sector concentration they represent, or why a thematic/sector "
            "ticker was preferred over the fund's literal holdings."
        ),
    )

    @field_validator("proxy_tickers", mode="before")
    @classmethod
    def _normalize_tickers(cls, v):
        if not isinstance(v, list):
            return v
        seen: dict[str, None] = {}
        for item in v:
            if not isinstance(item, str):
                continue
            cleaned = item.strip().upper()
            if cleaned and cleaned.lower() not in {"none", "n/a", "unknown"}:
                seen.setdefault(cleaned, None)
        # Hard cap: the prompt asks for 3-5, but never trust the model to
        # honor a limit on its own — truncate rather than let a run-away
        # list dilute downstream analysis.
        return list(seen)[:5]
