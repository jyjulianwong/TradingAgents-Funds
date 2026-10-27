"""Fork-only configuration defaults, kept out of ``default_config.py`` to keep upstream's file intact.

``default_config.py`` merges these into its own tables (each merge is one line
tagged ``FORK(funds)``): env-var overrides, data-vendor choices, the OHLCV interval,
and the fund / CLI-preset defaults.
"""

# Environment variables -> config keys (merged into ``_ENV_OVERRIDES``).
FUND_ENV_OVERRIDES = {
    "TRADINGAGENTS_ISIN_TICKER_MAP_OVERRIDE": "isin_ticker_map_override",
    # CLI-only presets
    "TRADINGAGENTS_ANALYSIS_DATE": "analysis_date",
    "TRADINGAGENTS_ANALYSTS": "analysts",
    "TRADINGAGENTS_ENABLE_VISUALIZER": "enable_visualizer",
}

# Merged into ``data_vendors``.
FUND_DATA_VENDORS = {
    # "hl,mstarpy": try Hargreaves Lansdown first (plain HTML scrape, no
    # Chrome, GB00-ISIN-only, instantly declines anything else) then fall
    # back to mstarpy (Morningstar via Selenium, any ISIN, needs Chrome).
    "fund_fact_sheet_data": "hl,mstarpy",
    # Verifies a Fund Analyst-picked proxy ticker against a live symbol
    # database; optional (needs ALPHA_VANTAGE_API_KEY) -- see fund_analyst.py.
    "ticker_symbol_search": "alpha_vantage",
}

# Merged into ``tool_vendors``.
# "ohlcv_interval" sets the candle interval for every OHLCV fetch
# (get_stock_data and the indicator data loader). yfinance-style values:
#   "1d" (daily, default), "1wk" (weekly), "1mo" (monthly)
#   "1h" (hourly, <=730 days history), "30m", "15m", "5m", "2m", "1m"
# Note: Alpha Vantage only supports "1d", "1wk", and "1mo".
FUND_TOOL_VENDORS = {
    "ohlcv_interval": "1d",
}

# Merged into the top level of the config.
FUND_DEFAULTS = {
    # When True, the Fund Analyst's dynamic resolution (fact-sheet fetch, LLM
    # proxy-ticker synthesis, Alpha Vantage verification) is skipped entirely
    # for every fund ISIN — it goes straight to the static isin_ticker_map
    # below, unconditionally. Set via TRADINGAGENTS_ISIN_TICKER_MAP_OVERRIDE
    # for a deployment that wants to run only off the curated, human-reviewed
    # map (e.g. to avoid LLM/vendor variability run-to-run, or when neither
    # mstarpy/hl nor an LLM/Alpha Vantage key is available).
    "isin_ticker_map_override": False,
    # ISIN-to-ticker mapping — static BACKUP only (unless the override above
    # is set, in which case it's the only source used).
    #
    # The Fund Analyst (the graph's first node) tries to derive proxy tickers
    # dynamically for any fund ISIN, from the fund's actual holdings via the
    # get_fund_fact_sheet tool (mstarpy/Morningstar). This map is only
    # consulted when that fails or returns nothing — no mstarpy data for the
    # ISIN, no Chrome available in the deployment environment, or the LLM's
    # synthesis came back empty. Every downstream agent (analysts, social-media
    # search included) reads whichever list the Fund Analyst resolved, from
    # ``state["fund_proxy_tickers"]``, not this map directly — see
    # ``resolve_isin_ticker_list`` in agents/context.py.
    #
    # Format:
    #   "<ISIN>": ["<TICKER_1>", "<TICKER_2>", ...]
    #
    # Example:
    #   "IE00B4L5Y983": ["IWDA.L", "SWRD.L"],  # iShares Core MSCI World ETF
    #   "IE00B3RBWM25": ["VWRL.L"],             # Vanguard FTSE All-World ETF
    #
    # If an ISIN is not listed here (and mstarpy also had nothing), a warning
    # is logged and the ISIN is used as-is (which will typically return empty
    # results from data vendors and social-media sources alike).
    "isin_ticker_map": {
        # Fidelity Index UK P Acc.
        # FTSE All-Share. FTAL.L (SPDR FTSE UK All Share ETF) tracks the exact index; ISF.L (FTSE 100) kept as a liquid fallback.
        "GB00BJS8SF95": ["FTAL.L", "ISF.L"],
        # Fidelity Index US P Acc.
        # S&P 500.
        "GB00BJS8SH10": ["SPY"],
        # FP WHEB Sustainability Impact C Acc.
        # 44-stock concentrated fund (top 10 ~37%). Top holdings at 31 Jul 2026: Keyence 4.2%, Thermo Fisher 4.0%, Agilent 3.9%,
        # Ecolab 3.8%, Steris 3.7%, Xylem 3.6%, ..., Autodesk 3.3%. Health is the largest theme (~26%) and was missing; TMO/A added.
        # Keyence (6861.T) is #1 but omitted for Tokyo-listing data-gap risk.
        "GB00B8HPRW47": ["TMO", "A", "ECL", "XYL", "ADSK"],
        # HSBC American Index Acc C.
        # S&P 500.
        "GB00B80QG615": ["SPY"],
        # iShares Corporate Bond Index S Acc.
        # Benchmark is Markit iBoxx GBP Non-Gilts (corporates + supranationals/agencies). SLXX.L (iBoxx GBP Corporates) is the closest liquid ETF.
        "GB00BN08ZN29": ["SLXX.L"],
        # iShares Enviro & Low Carbon Tilt Real Estate S Acc.
        # FTSE EPRA Nareit Developed Green Low Carbon Target. Holdings (Welltower, Realty Income, Equinix, Prologis) track the parent
        # FTSE EPRA Nareit Developed index closely, so HPRD.L (exact parent-index ETF) replaces IWDP.L (dividend-screened variant).
        "GB00BN091933": ["HPRD.L", "REET"],
        # iShares Japan Equity Index S Acc.
        # FTSE World Japan. EWJ (MSCI Japan) is a near-identical large/mid-cap proxy.
        "GB00BN08ZG51": ["EWJ"],
        # iShares Pacific ex Japan Equity Index S Acc.
        # FTSE World Asia-Pacific ex Japan INCLUDES Taiwan and South Korea. At Aug 2026: TSMC 19.6%, Samsung 10.5%, SK hynix 7.2%.
        # EPP (MSCI Pacific ex Japan) covers only Australia/HK/Singapore/NZ and missed ~40%+ of the fund. EWT + EWY added.
        "GB00BN08ZQ59": ["EWT", "EWY", "EPP"],
        # L&G European Index C Acc.
        # FTSE World Europe ex UK. VERX.L (Vanguard FTSE Developed Europe ex UK) replaces VGK, which holds ~20%+ UK stocks the fund excludes.
        # ASML retained as the fund's largest holding.
        "GB00BG0QP042": ["VERX.L", "ASML"],
        # L&G Future World ESG Tilted & Opt Emerging Markets C Acc.
        # ESGE (iShares ESG Aware MSCI EM ETF) has correct ESG tilt.
        "GB00BL6C2119": ["ESGE"],
        # L&G Future World ESG Tilted & Opt Developed C Acc.
        # MSCI World proxy; ESG tilt is mild so headline developed-market beta dominates.
        "GB00BMFXWS95": ["IWDA.L"],
        # L&G Global Technology Index Trust C Acc.
        # FTSE World Technology uses ICB, which classes Alphabet (10.7% combined) and Meta (3.5%) as Technology.
        # IXN (GICS IT) excludes both, so GOOGL and META are added to cover ~14% of the fund.
        "GB00BJLP1W53": ["IXN", "GOOGL", "META"],
        # abrdn Global REIT Tracker N Acc.
        # FTSE EPRA Nareit Developed. HPRD.L tracks the exact index; IWDP.L tracks the Dividend+ subset.
        "GB00BK5HLJ16": ["HPRD.L"],
        # AXA Framlington Biotech Z Acc.
        # Large-cap tilted (VRTX, REGN, AMGN, GILD each ~6-7%); IBB is cap-weighted with the same leaders.
        "GB00B784NS11": ["IBB"],
        # AXA Framlington Health Z Acc.
        # IXJ (iShares Global Healthcare) covers global mandate incl. AZN/Novo.
        "GB00B6WZJX05": ["IXJ"],
        # Barings Global Agriculture I Acc.
        # MOO (VanEck Agribusiness ETF) covers CTVA, NTR, DE, ADM, Kubota etc.
        "GB00B3B9VD63": ["MOO"],
        # BlackRock Natural Resources D Acc.
        # ~35% energy / ~55% materials incl. ag inputs and gold. GNR mirrors this mix (XOM, SHEL, CVX, Glencore, Nutrien, Corteva).
        "GB00B6865B79": ["GNR"],
        # JPMorgan Natural Resources C Acc.
        # Gold/precious metals are now the largest theme: top 10 (Feb 2026) includes NEM 4.8%, AEM 4.3%, KGC 3.7%, WPM 3.0%,
        # alongside XOM 4.7%, SHEL 4.0% and copper (Southern Copper, Grupo Mexico). GDX restores gold exposure; COPX adds copper.
        "GB00B88MP089": ["GNR", "GDX", "XOM", "COPX"],
        # Ninety One Global Gold B Inc.
        # 34 holdings, top 10 ~56%. NEM 8.9%, Barrick 8.7%, AngloGold 7.0%, Gold Fields 6.6%.
        # Barrick renamed Barrick Mining in May 2025 and its NYSE ticker changed from GOLD to B.
        "GB00BVLL5586": ["GDX", "NEM", "B", "AU", "GFI"],
        # Schroder Global Healthcare Z Acc.
        # IXJ (iShares Global Healthcare) provides global coverage.
        "GB00B76V7Q08": ["IXJ"],
        # WS Guinness Global Energy I Acc.
        # IXC (iShares Global Energy ETF) as primary proxy; XOM and SHEL are top holdings of this ~30-stock equal-weight fund.
        "GB00B56FW078": ["IXC", "XOM", "SHEL"],
    },
    # CLI-only settings — consumed by cli/selections.py and cli/run.py; ignored
    # by the programmatic API. None means "ask interactively"; a non-None value
    # skips the matching prompt (see the "CLI presets" section in .env.example).
    "analysis_date": None,  # YYYY-MM-DD string; None → prompt
    "analysts": None,  # comma-separated analyst keys; None → prompt
    "enable_visualizer": True,  # False → skip the 3-D visualizer server / browser tab
}
