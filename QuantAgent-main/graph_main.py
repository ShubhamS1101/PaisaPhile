"""
Main Agentic Trading System Graph

Complete conversational agentic system with:
- Persistent analysis_store (not flushed until conversation ends)
- Per-agent ran_at timestamps for freshness tracking
- Automatic decision staleness detection
- Dual data contexts (analyses_required vs data_contexts_required)
- Sequential agent execution with caching

Architecture:
1. Planner → determines intent and required analyses
2. Validator → ensures all required fields present
3. Fetcher → fetches data for analyses_required contexts
4. Agents (indicator/pattern/trend/decision) → run for each data context
5. Dialogue → generates user-facing response using analysis_store + data_contexts_required
6. Memory → updates conversation summary
"""

from typing import Dict, Any
from langgraph.graph import StateGraph, START, END

from agent_state import TradingAdvisorState
from agents.planner_agent import create_planner_agent, validate_and_route
from agents.indicator_agent_new import create_indicator_agent
from agents.pattern_agent_new import create_pattern_agent
from agents.trend_agent_new import create_trend_agent
from agents.decision_agent_new import create_decision_agent
from agents.dialogue_agent import create_dialogue_agent
from agents.conversation_memory import update_conversation_summary
from decision_freshness import should_run_decision

import yfinance as yf
import pandas as pd
from datetime import timedelta


class TradingGraphV2:
    """
    Production trading graph with proper freshness tracking and dual context handling.
    """
    
    def __init__(self, config: Dict[str, Any], agent_llm, graph_llm, toolkit):
        self.config = config
        self.agent_llm = agent_llm
        self.graph_llm = graph_llm
        self.toolkit = toolkit
    
    def _normalize_node(self):
        """Initialize state defaults."""
        def node(state: TradingAdvisorState) -> Dict[str, Any]:
            state.setdefault("kline_data", {})
            state.setdefault("analysis_store", {})
            state.setdefault("data_contexts_required", [])
            state.setdefault("analyses_required", {})
            state.setdefault("conversation_summary", "")
            state.setdefault("user_preferences", {})
            return state
        return node
    
    def _fetch_data_node(self):
        """
        Fetch OHLCV data for all contexts in analyses_required.
        
        Key insight: We fetch for analyses_required (not data_contexts_required).
        data_contexts_required are raw slices passed directly to dialogue.
        """
        def node(state: TradingAdvisorState) -> Dict[str, Any]:
            analyses_required = state.get("analyses_required", {})
            data_contexts_required = state.get("data_contexts_required", [])
            
            # Combine both sources for fetching
            all_contexts_to_fetch = set()
            
            # Add from analyses_required
            for context_key in analyses_required.keys():
                all_contexts_to_fetch.add(context_key)
            
            # Add from data_contexts_required
            for ctx in data_contexts_required:
                if ctx.get("key"):
                    all_contexts_to_fetch.add(ctx["key"])
            
            if not all_contexts_to_fetch:
                return {"kline_data": {}}
            
            kline_data: Dict[str, Dict[str, Any]] = state.get("kline_data", {})
            
            print(f"\n{'='*60}")
            print(f"FETCHING DATA")
            print(f"{'='*60}")
            
            for context_key in all_contexts_to_fetch:
                # Parse context_key: "{symbol}|{timeframe}|{start}:{end}"
                # Note: datetimes contain colons (e.g., 2026-01-13T10:30:00+05:30)
                parts = context_key.split("|")
                if len(parts) != 3:
                    print(f"  ⚠️ Invalid context_key format: {context_key}")
                    continue
                
                symbol = parts[0]
                timeframe = parts[1]
                datetime_range = parts[2]
                
                # Parse datetime range: "start_iso:end_iso"
                # ISO datetimes can end with timezone like +05:30 or -08:00 or Z
                # Strategy: Find the LAST colon that separates two complete ISO timestamps
                # Split by finding timezone end pattern
                try:
                    import re
                    # Match pattern: (ISO_datetime_with_tz):(ISO_datetime_with_tz)
                    # Timezone patterns: +XX:XX or -XX:XX or Z
                    # After timezone, there's a colon separator, then next datetime starts
                    
                    # Try timezone with +XX:XX or -XX:XX format
                    match = re.match(r'^(.+?[+-]\d{2}:\d{2}):(.+)$', datetime_range)
                    if not match:
                        # Try Z timezone
                        match = re.match(r'^(.+?Z):(.+)$', datetime_range)
                    
                    if not match:
                        print(f"  ⚠️ Could not parse datetime range: {datetime_range}")
                        continue
                    
                    start_datetime = match.group(1)
                    end_datetime = match.group(2)
                    
                except Exception as e:
                    print(f"  ⚠️ Error parsing datetime range: {e}")
                    continue
                
                # Skip if already fetched
                if context_key in kline_data and kline_data[context_key]:
                    print(f"✓ Data cached: {context_key}")
                    continue
                
                print(f"⬇️  Fetching: {symbol}|{timeframe} ({start_datetime[:10]} to {end_datetime[:10]})")
                
                try:
                    start_dt = pd.to_datetime(start_datetime, errors="coerce")
                    end_dt = pd.to_datetime(end_datetime, errors="coerce")
                    
                    if pd.isna(start_dt) or pd.isna(end_dt):
                        print(f"  ⚠️ Invalid datetime: {start_datetime} - {end_datetime}")
                        continue
                    
                    # yfinance end is exclusive; pad slightly
                    fetch_end = end_dt + timedelta(days=1) if end_dt == start_dt else end_dt
                    
                    df = yf.download(
                        tickers=symbol,
                        start=start_dt,
                        end=fetch_end,
                        interval=timeframe,
                        auto_adjust=True,
                        progress=False
                    )
                    
                    if df is None or df.empty:
                        print(f"  ❌ No data available for {symbol} (possibly delisted or invalid symbol)")
                        # Store empty marker so agents know fetch was attempted
                        kline_data[context_key] = None
                        continue
                    
                    df = df.reset_index()
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    
                    # Standardize datetime column
                    time_col = "Datetime" if "Datetime" in df.columns else ("Date" if "Date" in df.columns else None)
                    if not time_col:
                        print(f"  ⚠️ No datetime column")
                        kline_data[context_key] = None
                        continue
                    
                    if time_col != "Datetime":
                        df = df.rename(columns={time_col: "Datetime"})
                    
                    # Ensure required columns
                    required_cols = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
                    missing_cols = [col for col in required_cols if col not in df.columns]
                    if missing_cols:
                        print(f"  ⚠️ Missing columns: {missing_cols}")
                        if "Volume" in missing_cols:
                            df["Volume"] = 0
                        else:
                            kline_data[context_key] = None
                            continue
                    
                    df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce")
                    df = df.dropna(subset=["Datetime"])
                    
                    if df.empty:
                        print(f"  ❌ No valid data after processing")
                        kline_data[context_key] = None
                        continue
                    
                    # Store in kline_data with full context_key
                    kline_data[context_key] = {
                        "Datetime": df["Datetime"].dt.strftime("%Y-%m-%d %H:%M:%S").tolist(),
                        "Open": df["Open"].astype(float).tolist(),
                        "High": df["High"].astype(float).tolist(),
                        "Low": df["Low"].astype(float).tolist(),
                        "Close": df["Close"].astype(float).tolist(),
                        "Volume": df["Volume"].astype(float).tolist()
                    }
                    
                    print(f"  ✓ Fetched {len(df)} candles")
                    
                except Exception as e:
                    print(f"  ❌ Error fetching {symbol}: {e}")
                    kline_data[context_key] = None
            
            print(f"{'='*60}\n")
            return {"kline_data": kline_data}
        
        return node
    
    def _dialogue_node(self):
        """
        Dialogue agent runs ONCE per query.
        
        Receives:
        - analysis_store: All analysis results
        - data_contexts_required: Raw data slices for direct inspection
        
        Returns:
        - Updated state with explanation field (ALWAYS)
        """
        dialogue = create_dialogue_agent(self.agent_llm)
        
        def node(state: TradingAdvisorState) -> Dict[str, Any]:
            print(f"\n{'='*60}")
            print(f"DIALOGUE AGENT")
            print(f"{'='*60}")
            
            result = dialogue(state)
            
            # Verify explanation was generated and propagated
            if "explanation" in result and result["explanation"]:
                print(f"✓ Response generated ({len(result['explanation'])} chars)")
            else:
                print(f"⚠️  WARNING: No explanation in result!")
                # Fallback
                result["explanation"] = "An error occurred while generating the response."
            
            print(f"{'='*60}\n")
            
            return result
        
        return node
    
    def _memory_node(self):
        """Update conversation summary."""
        def node(state: TradingAdvisorState) -> Dict[str, Any]:
            summary = update_conversation_summary(
                state,  # Pass full state (contains conversation_summary, user_preferences)
                state.get("user_query") or "",
                state.get("explanation") or "",
                self.agent_llm  # Pass LLM for summary rewriting
            )
            return {"conversation_summary": summary}
        
        return node
    
    def _cleanup_node(self):
        """
        Clear per-turn temporary data for NEXT turn.
        
        PERSISTENT (kept across queries):
        - analysis_store: Cached analysis results
        - conversation_summary: Conversation history
        - explanation: Current turn's response (kept until next query)
        
        CLEARED (reset after each query):
        - user_query: Current user input
        - intent: Current query intent
        - need_clarification: Planner flag
        - data_contexts_required: Data slices for this query
        - analyses_required: Analysis plan for this query
        - kline_data: Temporary market data
        - user_preferences: (cleared - can be kept if needed)
        """
        def node(state: TradingAdvisorState) -> Dict[str, Any]:
            # Note: We DON'T clear explanation here because it's the output
            # It will be cleared at the start of the NEXT query in test_interactive.py
            return {
                "user_query": None,
                "intent": "trade",  # Reset to default
                "need_clarification": False,
                "data_contexts_required": [],
                "analyses_required": {},
                "kline_data": {},
                "user_preferences": {}  # Clear preferences (or keep if you want persistence)
            }
        
        return node
    
    def set_graph(self):
        """Build the complete graph."""
        
        # Create agent nodes
        planner_node = create_planner_agent(self.graph_llm)
        indicator_agent = create_indicator_agent(self.graph_llm, self.toolkit)
        pattern_agent = create_pattern_agent(self.agent_llm, self.graph_llm, self.toolkit)
        trend_agent = create_trend_agent(self.agent_llm, self.graph_llm, self.toolkit)
        decision_agent = create_decision_agent(self.agent_llm)
        
        graph: StateGraph = StateGraph(TradingAdvisorState)
        
        # Add nodes
        graph.add_node("normalize", self._normalize_node())
        graph.add_node("planner", planner_node)
        graph.add_node("validator", validate_and_route)
        graph.add_node("fetch", self._fetch_data_node())
        graph.add_node("indicator", indicator_agent)
        graph.add_node("pattern", pattern_agent)
        graph.add_node("trend", trend_agent)
        graph.add_node("decision", decision_agent)
        graph.add_node("dialogue", self._dialogue_node())
        graph.add_node("memory", self._memory_node())
        graph.add_node("cleanup", self._cleanup_node())
        
        # Routing logic
        def route_after_normalize(state: Dict[str, Any]) -> str:
            if state.get("user_query"):
                return "planner"
            return "end"
        
        def route_after_validate(state: Dict[str, Any]) -> str:
            if state.get("intent") == "clarify" and state.get("explanation"):
                return "dialogue"
            if state.get("analyses_required"):
                return "fetch"
            return "dialogue"
        
        def route_after_fetch(state: Dict[str, Any]) -> str:
            """
            Check if any data was successfully fetched.
            If all fetches failed (all values are None), skip to dialogue with error.
            """
            kline_data = state.get("kline_data", {})
            
            # Check if we have any valid data
            has_valid_data = any(data is not None for data in kline_data.values())
            
            if not has_valid_data and kline_data:
                # All fetches failed - skip analysis and go to dialogue with error
                print("⚠️  All data fetches failed - skipping analysis agents")
                return "dialogue"
            
            # At least some data is available, proceed to analysis
            return "indicator"
        
        # Main flow
        graph.add_edge(START, "normalize")
        graph.add_conditional_edges(
            "normalize",
            route_after_normalize,
            {"planner": "planner", "end": END}
        )
        
        graph.add_edge("planner", "validator")
        graph.add_conditional_edges(
            "validator",
            route_after_validate,
            {"fetch": "fetch", "dialogue": "dialogue"}
        )
        
        # Route after fetch - check if data was successfully retrieved
        graph.add_conditional_edges(
            "fetch",
            route_after_fetch,
            {"indicator": "indicator", "dialogue": "dialogue"}
        )
        graph.add_edge("indicator", "pattern")
        graph.add_edge("pattern", "trend")
        graph.add_edge("trend", "decision")
        graph.add_edge("decision", "dialogue")
        graph.add_edge("dialogue", "memory")
        graph.add_edge("memory", "cleanup")
        graph.add_edge("cleanup", END)
        
        return graph.compile()


def create_trading_graph(config: Dict[str, Any]) -> Any:
    """Factory function to create the trading graph."""
    from trading_graph import TradingGraph
    
    # Use existing TradingGraph for LLM initialization
    temp_graph = TradingGraph(config=config)
    
    return TradingGraphV2(
        config=config,
        agent_llm=temp_graph.agent_llm,
        graph_llm=temp_graph.graph_llm,
        toolkit=temp_graph.toolkit
    ).set_graph()
