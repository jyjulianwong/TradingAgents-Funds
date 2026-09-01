from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_autonomous_agent_instruction,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_instrument_context_from_state,
    get_language_instruction,
    resolve_isin_ticker_list,
)
from tradingagents.agents.utils.markdown import ensure_blank_line_before_tables


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        ticker = state["company_of_interest"]
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)

        symbol_list = resolve_isin_ticker_list(ticker, state)
        mapped_tickers = symbol_list[1:] if len(symbol_list) > 1 else []

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
        ]

        if mapped_tickers:
            symbols_fmt = ", ".join(f"`{s}`" for s in symbol_list)
            proxies_fmt = ", ".join(f"`{t}`" for t in mapped_tickers)
            isin_note = (
                f" This instrument is a fund identified by ISIN `{ticker}`."
                f" Financial statement data (balance sheet, cash flow, income"
                f" statement) is not available for fund vehicles — only basic market"
                f" metrics (52-week range, dividend yield, moving averages) will be"
                f" returned for the ISIN itself. To provide meaningful fundamental"
                f" analysis, retrieve data for all of the following symbols:"
                f" {symbols_fmt}. `{ticker}` is the fund's ISIN; {proxies_fmt} are"
                f" exchange-traded proxy tickers representing the fund's underlying"
                f" holdings, with full financial statement coverage. Call all available"
                f" tools for each symbol. Clearly label every section of your report"
                f" with the ticker it covers. Synthesise all data into a unified"
                f" fundamental analysis of the fund as a whole."
            )
        else:
            isin_note = ""

        system_message = (
            "You are a researcher tasked with analyzing fundamental information over the past year about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + isin_note
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
            + get_autonomous_agent_instruction()  # TODO: Hotfix #0001
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}."
                    " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
                    "{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = ensure_blank_line_before_tables(result.content)

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
