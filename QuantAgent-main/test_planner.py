"""
Test script for Planner Agent
Tests planner in isolation using TradingAdvisorState
"""

from trading_graph import TradingGraph
from planner_agent import create_planner_agent

# ==========================================================
# CONFIG
# ==========================================================
config = {
    "agent_llm_model": "gemini-2.5-flash",
    "graph_llm_model": "gemini-2.5-flash",
    "agent_llm_provider": "gemini",
    "graph_llm_provider": "gemini",
    "agent_llm_temperature": 0.1,
    "graph_llm_temperature": 0.1,
    "gemini_api_key": "AIzaSyDN8gKMA7Atzy-AlvV3pECeL6qNrM6iI9o",
}

trading_graph = TradingGraph(config=config)

# Create planner agent
planner_agent = create_planner_agent(trading_graph.graph_llm)

# ==========================================================
# TEST QUERIES
# ==========================================================
test_queries = [
    "Should I buy zomato for intraday?"
]

print("=" * 80)
print("PLANNER AGENT TEST")
print("=" * 80)

for i, query in enumerate(test_queries, 1):
    print(f"\n{'─' * 80}")
    print(f"TEST {i}: {query}")
    print(f"{'─' * 80}")

    # ------------------------------------------------------
    # Minimal valid TradingAdvisorState
    # ------------------------------------------------------
    state = {
        # 🔑 THIS IS THE KEY FIX
        "user_query": query,

        # Planner outputs (initially empty)
        "intent": "",
        "data_requirement": "",
        "symbols": [],
        "horizon": None,
        "timeframe": None,
        "start_date": None,
        "end_date": None,
        "mode": "single",
        "required_analyses": [],

        # System fields (not used by planner but required by state)
        "context_ready": False,
        "kline_data_map": {},

        # Cached analysis (unused here)
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

    # ------------------------------------------------------
    # Run planner
    # ------------------------------------------------------
    try:
        result = planner_agent(state)

        print("\n✅ Planner executed successfully!")
        print("\nParsed Output:")
        print(f"  Intent: {result.get('intent')}")
        print(f"  Data Requirement: {result.get('data_requirement')}")
        print(f"  Symbols: {result.get('symbols', [])}")
        print(f"  Horizon: {result.get('horizon')}")
        print(f"  Timeframe: {result.get('timeframe')}")
        print(f"  Start Date: {result.get('start_date')}")
        print(f"  End Date: {result.get('end_date')}")
        print(f"  Mode: {result.get('mode')}")
        print(f"  Required Analyses: {result.get('required_analyses', [])}")

        if result.get("explanation"):
            print(f"  Clarification: {result.get('explanation')}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
