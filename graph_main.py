"""
Main Agentic Trading System Graph

Complete conversational agentic system with:
- Persistent analysis_store (keyed by ROLLING/HISTORICAL window identities)
- Per-agent ran_at timestamps for freshness tracking
- Automatic decision staleness detection
- Sequential agent execution with caching

Architecture:
1. Planner → determines intent and required windows
2. Validator → ensures all required fields present
3. Fetcher → resolves window keys to date ranges, fetches OHLCV data
4. Agents (indicator/pattern/trend/decision) → run for each window
5. Dialogue → generates user-facing response using analysis_store
6. Memory → updates conversation summary
"""

from typing import Any, Dict, List
import re
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_qwq import ChatQwen
from langgraph.graph import StateGraph, START, END

from agent_state import TradingAdvisorState
from agents.planner_agent import create_planner_agent, validate_and_route
from agents.indicator_agent import create_indicator_agent
from agents.pattern_agent import create_pattern_agent
from agents.trend_agent import create_trend_agent
from agents.decision_agent import create_decision_agent
from agents.dialogue_agent import create_dialogue_agent
from agents.conversation_memory import update_conversation_summary
from decision_freshness import should_run_decision

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


def _resolve_lookback(lookback: str):
    """
    Resolve a lookback string to (start_datetime, end_datetime).
    
    Supported formats:
        "4d"  → 4 days back from now
        "30d" → 30 days back
        "6m"  → 6 months back
        "3y"  → 3 years back
        "100C" → 100 candles (treated as ~100 days for daily; caller adjusts)
    
    Returns:
        (start_dt: datetime, end_dt: datetime)
    """
    end_dt = datetime.now()
    lookback = lookback.strip()
    
    match = re.match(r'^(\d+)([dDwWmMyYcC])$', lookback)
    if not match:
        # Fallback: try to interpret as days
        try:
            days = int(lookback)
            return (end_dt - timedelta(days=days), end_dt)
        except ValueError:
            raise ValueError(f"Cannot parse lookback: {lookback}")
    
    value = int(match.group(1))
    unit = match.group(2).lower()
    
    if unit == 'd':
        start_dt = end_dt - timedelta(days=value)
    elif unit == 'w':
        start_dt = end_dt - timedelta(weeks=value)
    elif unit == 'm':
        start_dt = end_dt - relativedelta(months=value)
    elif unit == 'y':
        start_dt = end_dt - relativedelta(years=value)
    elif unit == 'c':
        # Candle count: approximate as trading days (5/7 of calendar days)
        # Add 50% buffer so yfinance returns enough candles
        estimated_calendar_days = int(value * 7 / 5 * 1.5)
        start_dt = end_dt - timedelta(days=estimated_calendar_days)
    else:
        raise ValueError(f"Unknown lookback unit: {unit}")
    
    return (start_dt, end_dt)


class TradingGraphV2:
    """
    Production trading graph with proper freshness tracking and dual context handling.
    """
    
    def __init__(self, config: Dict[str, Any], agent_llm, graph_llm, conversation_summary_llm, toolkit):
        self.config = config
        self.agent_llm = agent_llm
        self.graph_llm = graph_llm
        self.conversation_summary_llm = conversation_summary_llm
        self.toolkit = toolkit
    
    def _normalize_node(self):
        """Initialize state defaults and flush temporary files."""
        def node(state: TradingAdvisorState) -> Dict[str, Any]:
            # Flush record.csv at the start of each query
            import os
            record_path = "data/record.csv"
            if os.path.exists(record_path):
                try:
                    os.remove(record_path)
                except Exception:
                    pass  # Ignore errors if file is in use
            
            state.setdefault("kline_data", {})
            state.setdefault("analysis_store", {})
            state.setdefault("windows_required", [])
            state.setdefault("analyses_required", {})
            state.setdefault("data_required", [])
            state.setdefault("conversation_summary", "")
            state.setdefault("user_preferences", {})
            return state
        return node
    
    def _fetch_data_node(self):
        """
        Fetch OHLCV data for:
        1. All windows in analyses_required (for analysis pipeline)
        2. All items in data_required (raw data for dialogue, e.g. price_check)
        
        Stores fetched_start/fetched_end timestamps in the window entry
        so agents and freshness logic know the actual data range.
        """
        def node(state: TradingAdvisorState) -> Dict[str, Any]:
            from analysis_store_util import (
                parse_window_key,
                set_window_fetch_timestamps,
                init_window_entry,
            )
            analyses_required = state.get("analyses_required", {})
            data_required = state.get("data_required", [])
            analysis_store = state.get("analysis_store", {})
            
            if not analyses_required and not data_required:
                return {"kline_data": {}, "analysis_store": analysis_store}
            
            kline_data: Dict[str, Dict[str, Any]] = state.get("kline_data", {})
            
            print(f"\n{'='*60}")
            print(f"FETCHING DATA")
            print(f"{'='*60}")
            print(f"📋 Analysis windows: {len(analyses_required)}")
            print(f"📋 Data requests: {len(data_required)}")
            
            # --- Helper: fetch one symbol/timeframe/date-range into kline_data ---
            def _do_fetch(key: str, symbol: str, timeframe: str, start_dt, end_dt):
                """Fetch from yfinance and store in kline_data[key]. Returns candle count or 0."""
                if key in kline_data and kline_data[key]:
                    print(f"  ✓ Data cached: {key}")
                    return len(kline_data[key].get("Datetime", []))
                
                print(f"  ⬇️  Fetching: {symbol}|{timeframe} ({start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')})")
                
                try:
                    fetch_end = end_dt + timedelta(days=1)
                    
                    df = yf.download(
                        tickers=symbol,
                        start=start_dt,
                        end=fetch_end,
                        interval=timeframe,
                        auto_adjust=True,
                        progress=False
                    )
                    
                    if df is None or df.empty:
                        print(f"  ❌ No data for {symbol}")
                        kline_data[key] = None
                        return 0
                    
                    df = df.reset_index()
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    
                    time_col = "Datetime" if "Datetime" in df.columns else ("Date" if "Date" in df.columns else None)
                    if not time_col:
                        kline_data[key] = None
                        return 0
                    if time_col != "Datetime":
                        df = df.rename(columns={time_col: "Datetime"})
                    
                    required_cols = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
                    missing = [c for c in required_cols if c not in df.columns]
                    if missing:
                        if missing == ["Volume"]:
                            df["Volume"] = 0
                        else:
                            kline_data[key] = None
                            return 0
                    
                    df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce")
                    df = df.dropna(subset=["Datetime"])
                    
                    if df.empty:
                        kline_data[key] = None
                        return 0
                    
                    kline_data[key] = {
                        "Datetime": df["Datetime"].dt.strftime("%Y-%m-%d %H:%M:%S").tolist(),
                        "Open": df["Open"].astype(float).tolist(),
                        "High": df["High"].astype(float).tolist(),
                        "Low": df["Low"].astype(float).tolist(),
                        "Close": df["Close"].astype(float).tolist(),
                        "Volume": df["Volume"].astype(float).tolist()
                    }
                    
                    print(f"  ✓ Fetched {len(df)} candles")
                    return len(df)
                    
                except Exception as e:
                    print(f"  ❌ Error: {e}")
                    kline_data[key] = None
                    return 0
            
            # ────────────────────────────────────────────
            # 1. Fetch for analysis windows
            # ────────────────────────────────────────────
            for window_key, spec in analyses_required.items():
                if not spec.get("data_needed", True):
                    continue
                
                try:
                    parsed = parse_window_key(window_key)
                except ValueError:
                    print(f"  ⚠️ Invalid window key: {window_key}")
                    continue
                
                symbol = parsed["symbol"]
                timeframe = parsed["timeframe"]
                wtype = parsed["window_type"]
                
                if wtype == "ROLLING":
                    lookback = parsed.get("lookback", "30d")
                    start_dt, end_dt = _resolve_lookback(lookback)
                elif wtype == "HISTORICAL":
                    start_dt = pd.to_datetime(parsed["start"])
                    end_dt = pd.to_datetime(parsed["end"])
                else:
                    continue
                
                count = _do_fetch(window_key, symbol, timeframe, start_dt, end_dt)
                
                # Store actual fetched timestamps in the window entry
                if count > 0 and kline_data.get(window_key):
                    datetimes = kline_data[window_key]["Datetime"]
                    set_window_fetch_timestamps(
                        analysis_store,
                        window_key,
                        fetched_start=datetimes[0],
                        fetched_end=datetimes[-1],
                        candles_fetched=count,
                    )
            
            # ────────────────────────────────────────────
            # 2. Fetch for raw data requests (price_check etc.)
            # ────────────────────────────────────────────
            for item in data_required:
                data_id = item.get("data_id", "")
                symbol = item.get("symbol", "")
                timeframe = item.get("timeframe", "1d")
                
                if not data_id or not symbol:
                    continue
                
                # data_required always fetches recent data (last 5 trading days)
                start_dt, end_dt = _resolve_lookback("5d")
                _do_fetch(data_id, symbol, timeframe, start_dt, end_dt)
            
            print(f"{'='*60}\n")
            return {"kline_data": kline_data, "analysis_store": analysis_store}
        
        return node
    
    def _resolve_deps_node(self):
        """
        Pre-execution dependency resolution.

        Runs ONCE after fetch and BEFORE any agent.
        Checks freshness of each agent and cascades staleness
        through the dependency graph:

            indicator → trend → decision
            pattern  ──────→ decision

        Modifies analyses_required[window_key]["run"] in-place.
        """
        def node(state: TradingAdvisorState) -> Dict[str, Any]:
            from analysis_store_util import propagate_staleness
            print(f"\n{'─'*60}")
            print(f"RESOLVING DEPENDENCIES")
            print(f"{'─'*60}")
            propagate_staleness(state)
            # Show final run lists
            for wk, sp in state.get("analyses_required", {}).items():
                print(f"  {wk}: run={sp.get('run', [])}")
            print(f"{'─'*60}\n")
            return {"analyses_required": state.get("analyses_required", {})}

        return node

    def _dialogue_node(self):
        """
        Dialogue agent runs ONCE per query.
        
        Receives:
        - analysis_store: All analysis results
        
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
                self.conversation_summary_llm  # Pass conversation summary LLM
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
        - windows_required: Window specs for this query
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
                "windows_required": [],
                "analyses_required": {},
                "data_required": [],
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
        graph.add_node("resolve_deps", self._resolve_deps_node())
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
            intent = state.get("intent")
            has_explanation = state.get("explanation")
            analyses_required = state.get("analyses_required", {})
            
            print(f"\n🔀 ROUTING AFTER VALIDATE:")
            print(f"   Intent: {intent}")
            print(f"   Has explanation: {bool(has_explanation)}")
            print(f"   Analyses required: {len(analyses_required)} contexts")
            
            data_required = state.get("data_required", [])
            
            if intent == "clarify" and has_explanation:
                print(f"   \u2192 Routing to DIALOGUE (clarification needed)")
                return "dialogue"
            
            if analyses_required or data_required:
                print(f"   \u2192 Routing to FETCH ({len(analyses_required)} windows + {len(data_required)} data requests)")
                return "fetch"
            
            print(f"   → Routing to DIALOGUE (no analyses required)")
            return "dialogue"
        
        def route_after_fetch(state: Dict[str, Any]) -> str:
            """
            After fetch, decide whether to run analysis agents or skip to dialogue.
            - If analyses_required has items: go to analysis pipeline
            - If only data_required (price_check): skip straight to dialogue
            - If all fetches failed: skip to dialogue with error
            """
            kline_data = state.get("kline_data", {})
            analyses_required = state.get("analyses_required", {})
            
            # If no analysis windows, skip to dialogue (data_required only)
            if not analyses_required:
                print("   \u2192 Data-only request, skipping to DIALOGUE")
                return "dialogue"
            
            # Check if we have any valid data
            has_valid_data = any(data is not None for data in kline_data.values())
            
            if not has_valid_data and kline_data:
                print("\u26a0\ufe0f  All data fetches failed - skipping analysis agents")
                return "dialogue"
            
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
            {"indicator": "resolve_deps", "dialogue": "dialogue"}
        )
        graph.add_edge("resolve_deps", "indicator")
        graph.add_edge("indicator", "pattern")
        graph.add_edge("pattern", "trend")
        graph.add_edge("trend", "decision")
        graph.add_edge("decision", "dialogue")
        graph.add_edge("dialogue", "memory")
        graph.add_edge("memory", "cleanup")
        graph.add_edge("cleanup", END)
        
        return graph.compile()


def _get_api_key(config: Dict[str, Any], provider: str = "openai", use_conversation_api_key: bool = False) -> str:
    """Get API key with proper validation and error handling."""
    if provider == "openai":
        if use_conversation_api_key:
            api_key = config.get("conversation_summary_api_key") or config.get("api_key")
        else:
            api_key = config.get("api_key")
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key or api_key == "your-openai-api-key-here" or api_key == "":
            raise ValueError("OpenAI API key not found or invalid")
    elif provider == "anthropic":
        api_key = config.get("anthropic_api_key")
        if not api_key:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key or api_key == "":
            raise ValueError("Anthropic API key not found")
    elif provider == "qwen":
        api_key = config.get("qwen_api_key")
        if not api_key:
            api_key = os.environ.get("DASHSCOPE_API_KEY")
        if not api_key or api_key == "":
            raise ValueError("Qwen API key not found")
    elif provider == "gemini":
        api_key = config.get("gemini_api_key")
        if not api_key:
            api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key or api_key == "":
            raise ValueError("Gemini API key not found")
    else:
        raise ValueError(f"Unsupported provider: {provider}")
    return api_key


def _create_llm(config: Dict[str, Any], provider: str, model: str, temperature: float, use_conversation_api_key: bool = False) -> BaseChatModel:
    """Create an LLM instance based on the provider."""
    api_key = _get_api_key(config, provider, use_conversation_api_key)
    
    if provider == "openai":
        return ChatOpenAI(model=model, temperature=temperature, api_key=api_key)
    elif provider == "anthropic":
        return ChatAnthropic(model=model, temperature=temperature, api_key=api_key)
    elif provider == "qwen":
        return ChatQwen(model=model, temperature=temperature, api_key=api_key, max_retries=4)
    elif provider == "gemini":
        return ChatGoogleGenerativeAI(model=model, temperature=temperature, google_api_key=api_key)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def create_trading_graph(config: Dict[str, Any]) -> Any:
    """Factory function to create the trading graph with LLM initialization."""
    from graph_util import TechnicalTools
    from default_config import DEFAULT_CONFIG
    
    # Merge with defaults
    full_config = DEFAULT_CONFIG.copy()
    full_config.update(config)
    
    # Initialize LLMs
    agent_llm = _create_llm(
        config=full_config,
        provider=full_config.get("agent_llm_provider", "openai"),
        model=full_config.get("agent_llm_model", "gpt-4o-mini"),
        temperature=full_config.get("agent_llm_temperature", 0.1),
    )
    graph_llm = _create_llm(
        config=full_config,
        provider=full_config.get("graph_llm_provider", "openai"),
        model=full_config.get("graph_llm_model", "gpt-4o"),
        temperature=full_config.get("graph_llm_temperature", 0.1),
    )
    conversation_summary_llm = _create_llm(
        config=full_config,
        provider=full_config.get("conversation_summary_llm_provider", "openai"),
        model=full_config.get("conversation_summary_llm_model", "gpt-4o-mini"),
        temperature=full_config.get("conversation_summary_llm_temperature", 0.3),
        use_conversation_api_key=True,
    )
    toolkit = TechnicalTools()
    
    return TradingGraphV2(
        config=full_config,
        agent_llm=agent_llm,
        graph_llm=graph_llm,
        conversation_summary_llm=conversation_summary_llm,
        toolkit=toolkit
    ).set_graph()
