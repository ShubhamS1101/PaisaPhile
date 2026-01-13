"""Simple interactive runner for the Planner Agent.

Asks for a user query and prints the planner output JSON.
"""

import json

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

def create_initial_state(query: str) -> dict:
    """Create minimal state required by the planner."""
    return {
        # Core input
        "user_query": query,
        
        # Planner outputs (will be populated)
        "intent": "",
        "need_clarification": False,
        "data_contexts_required": [],
        "analyses_required": {},
        
        # System fields
        "kline_data": {},
        "analysis_store": {},
        
        # Output fields
        "explanation": None,
        
        # Memory
        "conversation_summary": "",
        "user_preferences": {},
    }


def main() -> None:
    trading_graph = TradingGraph(config=config)
    planner_agent = create_planner_agent(trading_graph.graph_llm)

    query = input("Enter your query: ").strip()
    if not query:
        print("No query provided.")
        return

    state = create_initial_state(query)
    result = planner_agent(state)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
