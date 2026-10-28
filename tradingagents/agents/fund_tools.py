"""Symbol-selectable variants of upstream's data tools, for fund runs (fork-only).

Upstream pins every per-instrument tool to the run's instrument: the symbol is
injected from graph state (``InjectedState("company_of_interest")``) and whatever
the model passes is ignored. For a fund ISIN that means the model cannot ask for
a proxy ticker's prices or fundamentals; every request returns the ISIN's own data.

This module builds, for each upstream tool with such an injected symbol, a twin
with the same name, description and arguments plus an optional ``symbol``. The twin
accepts only the run's instrument or a proxy the Fund Analyst resolved, then calls
upstream's own function (``tool.func``), so vendor fixes and signature changes made
upstream to a tool reach the twin without any edit here. ``tests/test_fund_tools.py``
fails loudly if upstream changes how a tool is declared in a way the twin can't follow.
"""

import inspect
import typing
from typing import Annotated, Any

from langchain_core.tools import BaseTool, StructuredTool
from langgraph.prebuilt import InjectedState

from tradingagents.agents.fund_context import is_isin, resolve_isin_ticker_list

_INSTRUMENT_KEY = "company_of_interest"

_SYMBOL_HELP = (
    " For a fund run, pass `symbol` to choose the fund's ISIN or one of its proxy "
    "tickers named in your instructions; omit it for the fund itself."
)


def _injection(annotation) -> InjectedState | None:
    for meta in getattr(annotation, "__metadata__", ()):
        if isinstance(meta, InjectedState):
            return meta
        if meta is InjectedState:  # bare ``InjectedState``: the whole state
            return InjectedState()
    return None


def _pick_symbol(requested: str | None, state: dict) -> tuple[str | None, str | None]:
    """The symbol to serve and, when the request must be refused, the reason.

    A fund run accepts its ISIN or a resolved proxy ticker (case-insensitively). Any
    other run keeps upstream's rule: the run's instrument is served whatever is passed.
    """
    instrument = state[_INSTRUMENT_KEY]
    if not requested or not requested.strip() or not is_isin(instrument):
        return instrument, None
    allowed = resolve_isin_ticker_list(instrument, state)
    by_upper = {s.upper(): s for s in allowed}
    chosen = by_upper.get(requested.strip().upper())
    if chosen is None:
        return None, (
            f"`{requested}` is not one of this run's instruments. Use one of: "
            f"{', '.join(allowed)}."
        )
    return chosen, None


def with_symbol(upstream: BaseTool) -> BaseTool:
    """The twin of ``upstream`` that lets the model choose among the run's symbols.

    Returns ``upstream`` unchanged when it has no injected instrument argument
    (global news, macro series, prediction markets).
    """
    func = upstream.func
    signature = inspect.signature(func)
    hints = typing.get_type_hints(func, include_extras=True)

    symbol_param: str | None = None
    whole_state = False
    injected: dict[str, str] = {}  # parameter -> state key, other than the instrument
    visible: list[inspect.Parameter] = []
    for name, param in signature.parameters.items():
        marker = _injection(hints[name])
        if marker is None:
            visible.append(param.replace(annotation=hints[name]))
        elif marker.field == _INSTRUMENT_KEY:
            symbol_param = name
        elif marker.field:
            injected[name] = marker.field
        else:
            whole_state = True
    if symbol_param is None:
        return upstream
    if whole_state:
        raise TypeError(f"{upstream.name}: whole-state injection is not supported by with_symbol")

    def run(**kwargs: Any) -> str:
        state = kwargs.pop("state")
        requested = kwargs.pop("symbol", None)
        symbol, refusal = _pick_symbol(requested, state)
        if refusal:
            return refusal
        call = dict(kwargs)
        call[symbol_param] = symbol
        for name, key in injected.items():
            if key in state:
                call[name] = state[key]
        return func(**call)

    symbol_arg = inspect.Parameter(
        "symbol",
        inspect.Parameter.KEYWORD_ONLY,
        default=None,
        annotation=Annotated[
            str | None,
            "Fund runs only: the fund's ISIN or one of its proxy tickers. Omit for the instrument under analysis.",
        ],
    )
    state_arg = inspect.Parameter(
        "state",
        inspect.Parameter.KEYWORD_ONLY,
        annotation=Annotated[dict, InjectedState],
    )
    params = [p.replace(kind=inspect.Parameter.KEYWORD_ONLY) for p in visible] + [symbol_arg, state_arg]
    # Keyword-only parameters may follow one another in any order of defaults.
    run.__signature__ = inspect.Signature(params, return_annotation=str)  # type: ignore[attr-defined]
    run.__annotations__ = {p.name: p.annotation for p in params} | {"return": str}
    run.__name__ = upstream.name
    run.__doc__ = upstream.description

    return StructuredTool.from_function(
        func=run,
        name=upstream.name,
        description=upstream.description + _SYMBOL_HELP,
        infer_schema=True,
    )


def tool_node_tools(tools) -> list[BaseTool]:
    """The tools an analyst's tool node runs: each upstream tool's symbol-selectable twin."""
    return [with_symbol(t) for t in tools]


def tools_for_run(tools, state) -> list[BaseTool]:
    """The tools to offer the model: the twins for a fund run, upstream's tools otherwise.

    Ordinary tickers see exactly upstream's tool schemas.
    """
    if is_isin(state[_INSTRUMENT_KEY]):
        return tool_node_tools(tools)
    return list(tools)
