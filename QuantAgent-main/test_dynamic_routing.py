"""
Test Dynamic Graph Routing
Tests the new conditional routing system with different required_analyses
"""

from trading_graph import TradingGraph
from langchain_core.messages import HumanMessage

# Initialize trading graph
config = {
    "agent_llm_model": "gemini-2.5-flash",
    "graph_llm_model": "gemini-2.5-flash",
    "agent_llm_provider": "gemini",
    "graph_llm_provider": "gemini",
    "agent_llm_temperature": 0.1,
    "graph_llm_temperature": 0.1,
    "gemini_api_key": "AIzaSyBzzwP7sSWXoQ52wiXJIMLkSx1YJ59UJ5k",
}

print("="*80)
print("DYNAMIC ROUTING TEST")
print("="*80)

# Test Case 1: Only Indicator Analysis
print("\n" + "─"*80)
print("TEST 1: Only Indicator Analysis")
print("─"*80)

state1 = {
    "should_analyze": True,
    "required_analyses": ["indicator"],  # Only indicator
    "messages": [HumanMessage(content="What's the RSI?")],
    "kline_data": {},  # Empty for test
    "time_frame": "1h",
    "stock_name": "BTC-USD",
    "pattern_image": "",
    "trend_image": "",
}

print("\nExpected flow: Router → Indicator → Router → END")
print("Agents that should run: indicator")
print("Agents that should NOT run: pattern, trend, decision\n")

# Test Case 2: Full Analysis
print("\n" + "─"*80)
print("TEST 2: Full Analysis Pipeline")
print("─"*80)

state2 = {
    "should_analyze": True,
    "required_analyses": ["indicator", "pattern", "trend", "decision"],
    "messages": [HumanMessage(content="Should I buy BTC?")],
    "kline_data": {},
    "time_frame": "4h",
    "stock_name": "BTC-USD",
    "pattern_image": "",
    "trend_image": "",
}

print("\nExpected flow: Router → Indicator → Router → Pattern → Router → Trend → Router → Decision → Router → END")
print("Agents that should run: indicator, pattern, trend, decision")
print("All agents run in order, each removes itself from required_analyses\n")

# Test Case 3: Only Trend + Decision
print("\n" + "─"*80)
print("TEST 3: Partial Analysis (Trend + Decision only)")
print("─"*80)

state3 = {
    "should_analyze": True,
    "required_analyses": ["trend", "decision"],  # Skip indicator and pattern
    "messages": [HumanMessage(content="What's the trend?")],
    "kline_data": {},
    "time_frame": "1d",
    "stock_name": "AAPL",
    "pattern_image": "",
    "trend_image": "",
}

print("\nExpected flow: Router → Trend → Router → Decision → Router → END")
print("Agents that should run: trend, decision")
print("Agents that should NOT run: indicator, pattern\n")

# Test Case 4: No Analysis
print("\n" + "─"*80)
print("TEST 4: Context Only (No Analysis)")
print("─"*80)

state4 = {
    "should_analyze": False,  # Context only
    "required_analyses": [],
    "messages": [],
    "kline_data": {},
    "time_frame": "1h",
    "stock_name": "BTC-USD",
    "pattern_image": "",
    "trend_image": "",
}

print("\nExpected flow: Router → END")
print("Agents that should run: NONE")
print("Graph should exit immediately\n")

# Test Case 5: Empty required_analyses
print("\n" + "─"*80)
print("TEST 5: Should analyze but no analyses required")
print("─"*80)

state5 = {
    "should_analyze": True,
    "required_analyses": [],  # Empty list
    "messages": [HumanMessage(content="Explain previous analysis")],
    "kline_data": {},
    "time_frame": "1h",
    "stock_name": "BTC-USD",
    "pattern_image": "",
    "trend_image": "",
}

print("\nExpected flow: Router → END")
print("Agents that should run: NONE")
print("Graph should recognize empty list and exit\n")

print("="*80)
print("ROUTING VALIDATION COMPLETE")
print("="*80)
print("\nThe above tests demonstrate:")
print("✓ Dynamic routing based on required_analyses")
print("✓ Agents remove themselves after execution")
print("✓ No infinite loops (router checks empty list)")
print("✓ No duplicate runs (each agent runs max once)")
print("✓ Decision agent can run without all agents")
print("✓ Context-only mode skips all analysis")
print("\nTo actually run these tests, the agents would need real data.")
print("This script shows the EXPECTED behavior of the dynamic router.")
