"""The symbol-selectable twins of upstream's data tools (fork-only, see agents/fund_tools.py)."""

from typing import Annotated
from unittest import mock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import InjectedState, ToolNode

from tradingagents.agents import tools as upstream_tools
from tradingagents.agents.analysts import fundamentals_analyst, market_analyst, news_analyst
from tradingagents.agents.fund_context import get_symbol_argument_instruction
from tradingagents.agents.fund_tools import tool_node_tools, tools_for_run, with_symbol
from tradingagents.agents.state import AgentState

ISIN = "GB00BVLL5586"
FUND_STATE = {
    "company_of_interest": ISIN,
    "trade_date": "2026-10-28",
    "fund_proxy_tickers": ["GDX", "NEM"],
}
STOCK_STATE = {"company_of_interest": "AAPL", "trade_date": "2026-10-28"}

ALL_UPSTREAM = [
    getattr(upstream_tools, name)
    for name in dir(upstream_tools)
    if hasattr(getattr(upstream_tools, name), "func") and hasattr(getattr(upstream_tools, name), "args")
]


def _run(tool_, state, **args):
    """Call ``tool_`` the way the analyst's tool node does, with the run's state injected."""
    graph = StateGraph(AgentState)
    graph.add_node("tools", ToolNode([tool_]))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    call = AIMessage(content="", tool_calls=[{"name": tool_.name, "args": args, "id": "1"}])
    out = graph.compile().invoke({**state, "messages": [call]})
    return out["messages"][-1].content


@pytest.mark.unit
@pytest.mark.parametrize("upstream", ALL_UPSTREAM, ids=lambda t: t.name)
def test_every_upstream_tool_keeps_its_arguments_and_gains_only_symbol(upstream):
    twin = with_symbol(upstream)
    assert twin.name == upstream.name
    if twin is upstream:  # no instrument argument (global news, macro, prediction markets)
        assert "symbol" not in upstream.args
        return
    assert list(twin.args) == [*upstream.args, "symbol"]
    for name, schema in upstream.args.items():
        assert twin.args[name].get("type") == schema.get("type")
    assert upstream.description in twin.description


@pytest.mark.unit
def test_the_instrument_tools_are_all_wrapped():
    wrapped = {t.name for t in ALL_UPSTREAM if with_symbol(t) is not t}
    assert {"get_stock_data", "get_indicators", "get_fundamentals", "get_news"} <= wrapped
    assert "get_global_news" not in wrapped


@pytest.mark.unit
def test_a_proxy_symbol_reaches_the_vendor_not_the_isin():
    with mock.patch.object(upstream_tools, "route_to_vendor", side_effect=lambda *a, **k: f"ROUTED {a}") as route:
        out = _run(with_symbol(upstream_tools.get_stock_data), FUND_STATE,
                   start_date="2026-10-01", end_date="2026-10-28", symbol="gdx")
    assert "'GDX'" in out and ISIN not in out
    assert route.call_args.args[:2] == ("get_stock_data", "GDX")


@pytest.mark.unit
def test_omitting_symbol_serves_the_fund_itself():
    with mock.patch.object(upstream_tools, "route_to_vendor", side_effect=lambda *a, **k: f"ROUTED {a}"):
        out = _run(with_symbol(upstream_tools.get_fundamentals), FUND_STATE, curr_date="2026-10-28")
    assert ISIN in out


@pytest.mark.unit
def test_a_symbol_outside_the_run_is_refused_not_served_as_the_fund():
    with mock.patch.object(upstream_tools, "route_to_vendor") as route:
        out = _run(with_symbol(upstream_tools.get_news), FUND_STATE,
                   start_date="2026-10-01", end_date="2026-10-28", symbol="TSLA")
    route.assert_not_called()
    assert "not one of this run's instruments" in out and "GDX" in out


@pytest.mark.unit
def test_an_ordinary_ticker_is_served_whatever_symbol_is_passed_as_upstream_does():
    with mock.patch.object(upstream_tools, "route_to_vendor", side_effect=lambda *a, **k: f"ROUTED {a}"):
        out = _run(with_symbol(upstream_tools.get_news), STOCK_STATE,
                   start_date="2026-10-01", end_date="2026-10-28", symbol="TSLA")
    assert "'AAPL'" in out and "TSLA" not in out


@pytest.mark.unit
def test_the_run_date_still_caps_the_window():
    with mock.patch.object(upstream_tools, "route_to_vendor", side_effect=lambda *a, **k: f"ROUTED {a}") as route:
        _run(with_symbol(upstream_tools.get_stock_data), FUND_STATE,
             start_date="2026-10-01", end_date="2027-01-01", symbol="NEM")
    assert route.call_args.args[3] == "2026-10-28"


@pytest.mark.unit
def test_the_indicator_tool_still_declines_atr_for_the_isin_but_not_for_a_proxy():
    with mock.patch.object(upstream_tools, "route_to_vendor", side_effect=lambda *a, **k: f"ROUTED {a}"):
        twin = with_symbol(upstream_tools.get_indicators)
        fund = _run(twin, FUND_STATE, indicator="atr", curr_date="2026-10-28")
        proxy = _run(twin, FUND_STATE, indicator="atr", curr_date="2026-10-28", symbol="GDX")
    assert "not applicable" in fund
    assert "ROUTED" in proxy and "GDX" in proxy


@pytest.mark.unit
def test_a_twin_follows_a_tool_upstream_changes_without_edits_here():
    """A new argument, or a new tool, declared the upstream way is carried by the twin."""
    seen = {}

    @tool
    def get_new_thing(
        ticker: Annotated[str, InjectedState("company_of_interest")],
        window: Annotated[int, "days"] = 7,
        trade_date: Annotated[str, InjectedState("trade_date")] = "",
    ) -> str:
        """A tool upstream adds later."""
        seen.update(ticker=ticker, window=window, trade_date=trade_date)
        return "ok"

    twin = with_symbol(get_new_thing)
    assert list(twin.args) == ["window", "symbol"]
    assert _run(twin, FUND_STATE, window=3, symbol="NEM") == "ok"
    assert seen == {"ticker": "NEM", "window": 3, "trade_date": "2026-10-28"}


@pytest.mark.unit
def test_an_injection_the_twin_cannot_follow_fails_loudly():
    @tool
    def get_odd(
        ticker: Annotated[str, InjectedState("company_of_interest")],
        state: Annotated[dict, InjectedState],
    ) -> str:
        """Takes the whole state."""
        return ""

    with pytest.raises(TypeError, match="whole-state"):
        with_symbol(get_odd)


@pytest.mark.unit
@pytest.mark.parametrize("module", [market_analyst, news_analyst, fundamentals_analyst])
def test_analysts_offer_upstream_tools_for_a_stock_and_twins_for_a_fund(module):
    assert tools_for_run(module.TOOLS, STOCK_STATE) == list(module.TOOLS)
    assert [t.name for t in tools_for_run(module.TOOLS, FUND_STATE)] == [t.name for t in module.TOOLS]
    assert [t.name for t in tool_node_tools(module.TOOLS)] == [t.name for t in module.TOOLS]
    assert any("symbol" in t.args for t in tools_for_run(module.TOOLS, FUND_STATE))


@pytest.mark.unit
def test_the_prompt_tells_a_fund_run_how_to_pick_a_symbol():
    text = get_symbol_argument_instruction(ISIN, FUND_STATE)
    assert "`symbol`" in text and "`GDX`" in text and "`NEM`" in text
    assert get_symbol_argument_instruction("AAPL", STOCK_STATE) == ""
    assert get_symbol_argument_instruction(ISIN, {**FUND_STATE, "fund_proxy_tickers": []}) == ""


@pytest.mark.unit
def test_a_fund_runs_market_analyst_gets_a_proxys_data_through_the_real_graph():
    """Scripted model + the analyst's real tool node: its proxy request is served as that proxy."""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS
    from tradingagents.graph.setup import _analyst_graph

    class Scripted(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    asked = AIMessage(content="", tool_calls=[
        {"name": "get_stock_data", "id": "1",
         "args": {"start_date": "2026-10-01", "end_date": "2026-10-28", "symbol": "GDX"}},
    ])
    llm = Scripted(messages=iter([asked, AIMessage(content="Report on GDX.")]))
    spec = ANALYST_NODE_SPECS["market"]
    graph = _analyst_graph(spec, market_analyst.create_market_analyst(llm), max_tool_rounds=3)
    state = {**FUND_STATE, "asset_type": "stock", "instrument_context": "", "messages": []}
    with mock.patch.object(upstream_tools, "route_to_vendor", side_effect=lambda *a, **k: f"ROUTED {a}") as route:
        out = graph.invoke(state)
    assert route.call_args.args[:2] == ("get_stock_data", "GDX")
    assert out["market_report"] == "Report on GDX."
