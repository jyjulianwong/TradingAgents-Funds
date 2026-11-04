from tradingagents.agents.state import AgentState


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    # FORK(funds): debate-order — Bear opens, Bull closes (was Bull-then-Bear). A
    # 2026-10-29 run review found a 14-Underweight/1-Hold skew and traced one
    # structural candidate to the fixed order: at the default max_debate_rounds=1,
    # Bear always spoke last, giving the bearish side recency advantage before the
    # Research Manager read the transcript. Risk debate order is left unchanged.
    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue."""

        if (
            state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
        ):  # max_debate_rounds turns each for bull and bear
            return "Research Manager"
        if state["investment_debate_state"]["current_response"].startswith("Bear"):
            return "Bull Researcher"
        return "Bear Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue."""
        if (
            state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds
        ):  # max_risk_discuss_rounds turns each for the three risk analysts
            return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
