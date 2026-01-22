from trading_graph import TradingGraph
from agent_state import TradingAdvisorState


# ==========================================================
# CONFIG
# ==========================================================
config = {
    "agent_llm_provider": "gemini",
    "graph_llm_provider": "gemini",
    "agent_llm_model": "gemini-2.5-flash",
    "graph_llm_model": "gemini-2.5-flash",
    "agent_llm_temperature": 0.1,
    "graph_llm_temperature": 0.1,
    "gemini_api_key": "AIzaSyDN8gKMA7Atzy-AlvV3pECeL6qNrM6iI9o",
}

trading_graph = TradingGraph(config=config)


# ==========================================================
# INITIAL STATE (EMPTY, CLEAN)
# ==========================================================
state = {
        # Per-query execution fields (reset every turn)
        "user_query": None,
        "data_required_keys": [],
        "required_analysis_keys": {},

        # Planner outputs (set per turn)
        "intent": "",
        "data_requirement": "",
        "symbols": [],
        "horizon": None,
        "timeframe": None,
        "start_date": None,
        "end_date": None,
        "mode": "single",
        "required_analyses": [],
        "need_clarification": False,

        # System fields
        "context_ready": False,
        "kline_data_map": {},

        # Persistent analysis store (NEW)
        "analysis_store": {},

        # Legacy analysis cache (deprecated, kept for backward compatibility)
        "indicators": {},
        "trend": {},
        "pattern": {},

        # Decision layer
        "decision": None,
        "explanation": None,

        # Memory
        "conversation_summary": "",
        "user_preferences": {},
    }


# ==========================================================
# CHAT LOOP (END-TO-END AGENTIC FLOW)
# ==========================================================
print("\n✅ Agentic Trading Advisor Started")
print("Type 'exit' to quit\n")

while True:
    user_input = input("🧑 You: ").strip()
    if user_input.lower() == "exit":
        print("👋 Goodbye")
        break

    # Inject only user query
    state["user_query"] = user_input

    # Run FULL LangGraph
    final_state = trading_graph.run_analysis(state)

    # Clarification path
    if final_state.get("need_clarification"):
        print("\n🤖 AI:", final_state.get("explanation"))
        continue

    # Final answer
    answer = (
        final_state.get("decision")
        or final_state.get("explanation")
        or "No response."
    )

    print("\n🤖 AI:\n", answer)
    print("\n📌 Conversation Summary:")
    print(final_state.get("conversation_summary", "N/A"))
    print("-" * 60)
