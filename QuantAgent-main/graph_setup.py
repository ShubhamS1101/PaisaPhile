from typing import Dict, Any
from datetime import datetime, timedelta

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

from agent_state import TradingAdvisorState, IndicatorAgentState
from decision_agent import create_final_trade_decider
from indicator_agent import create_indicator_agent
from pattern_agent import create_pattern_agent
from trend_agent import create_trend_agent
from planner_agent import create_planner_agent
from planner_agent import validate_and_route

from graph_util import TechnicalTools
from conversation_memory import update_conversation_summary
from analysis_store_util import get_filtered_analysis_store

import yfinance as yf
import pandas as pd


class SetGraph:
    def __init__(
        self,
        agent_llm: ChatOpenAI,
        graph_llm: ChatOpenAI,
        toolkit: TechnicalTools,
        use_new_state: bool = True,
    ):
        self.agent_llm = agent_llm
        self.graph_llm = graph_llm
        self.toolkit = toolkit
        self.use_new_state = use_new_state

    # ============================================================
    # DATA FETCH NODE
    # ============================================================
    def _fetch_data_node(self):
     def fetch_node(state: TradingAdvisorState) -> TradingAdvisorState:
        """
        Data fetch node - fetches OHLCV data for keys specified in data_required_keys.
        
        STRICT RULES:
        1. Fetch ONLY for keys in data_required_keys
        2. Parse each key to extract: symbol, timeframe, start_date, end_date
        3. Store fetched data ONLY in kline_data_map (temporary storage)
        4. Set context_ready=true if at least one dataset is fetched
        5. NEVER infer dates
        6. NEVER modify planner output
        7. NEVER write into analysis_store directly
        
        Args:
            state: TradingAdvisorState with populated data_required_keys
            
        Returns:
            Updated state with fetched data in kline_data_map
        """
        
        # --------------------------------------------------
        # 1. Check if data is required
        # --------------------------------------------------
        if state.get("data_requirement") != "required":
            print("ℹ️  Data not required for this query")
            return state
        
        data_keys = state.get("data_required_keys", [])
        if not data_keys:
            print("⚠️ Fetch skipped: no data_required_keys specified")
            return state
        
        # --------------------------------------------------
        # 2. Import analysis_store_util for key parsing
        # --------------------------------------------------
        from analysis_store_util import make_analysis_key
        
        fetched_count = 0
        
        # --------------------------------------------------
        # 3. Fetch data for each key
        # --------------------------------------------------
        for key in data_keys:
            # Parse the key: "{symbol}|{timeframe}|{start_date}:{end_date}"
            try:
                parts = key.split("|")
                if len(parts) != 3:
                    print(f"⚠️ Invalid key format: {key}")
                    continue
                
                symbol = parts[0]
                timeframe = parts[1]
                date_range = parts[2]
                
                date_parts = date_range.split(":")
                if len(date_parts) != 2:
                    print(f"⚠️ Invalid date range format in key: {key}")
                    continue
                
                start_date = date_parts[0]
                end_date = date_parts[1]
                
            except Exception as e:
                print(f"⚠️ Failed to parse key {key}: {e}")
                continue
            
            # --------------------------------------------------
            # 4. Check if already cached in kline_data_map
            # --------------------------------------------------
            # Note: We use simple symbol-based caching for now
            # In future, could use key-based caching for better granularity
            if symbol in state.get("kline_data_map", {}):
                print(f"✓ Using cached data for {symbol}")
                fetched_count += 1
                continue
            
            # --------------------------------------------------
            # 5. Fetch data from yfinance
            # --------------------------------------------------
            from datetime import datetime, timedelta
            
            fetch_start = start_date
            fetch_end = end_date
            
            # Adjust end_date for yfinance (exclusive end)
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                
                # If querying a single date, extend end by 1 day
                if start_dt == end_dt:
                    fetch_end = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                    print(f"ℹ️  Single date query detected - extending end_date to {fetch_end}")
            except ValueError as e:
                print(f"⚠️ Date parsing error for {key}: {e}")
                continue
            
            print(f"📥 Fetching {symbol} | TF={timeframe} | {fetch_start} → {fetch_end}")
            
            df = yf.download(
                tickers=symbol,
                start=fetch_start,
                end=fetch_end,
                interval=timeframe,
                auto_adjust=True,
                progress=False,
            )
            
            if df.empty:
                print(f"⚠️ No data returned for {symbol}")
                
                # Try fallback with wider range (7 days lookback)
                try:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    fallback_start = (start_dt - timedelta(days=7)).strftime("%Y-%m-%d")
                    fallback_end = (start_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                    
                    print(f"🔄 Retrying with wider range: {fallback_start} → {fallback_end}")
                    
                    df = yf.download(
                        tickers=symbol,
                        start=fallback_start,
                        end=fallback_end,
                        interval=timeframe,
                        auto_adjust=True,
                        progress=False,
                    )
                    
                    if df.empty:
                        print(f"❌ Still no data - symbol may be invalid or delisted")
                        continue
                    else:
                        print(f"✓ Fallback successful - got {len(df)} data points")
                except Exception as e:
                    print(f"❌ Fallback fetch failed: {e}")
                    continue
                
                continue
            
            df.reset_index(inplace=True)
            
            # --------------------------------------------------
            # 6. Normalize columns (handle MultiIndex)
            # --------------------------------------------------
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            df.columns = df.columns.astype(str)
            
            # --------------------------------------------------
            # 7. Normalize time column
            # --------------------------------------------------
            if "Datetime" in df.columns:
                time_col = "Datetime"
            elif "Date" in df.columns:
                time_col = "Date"
            else:
                print(f"⚠️ No valid time column for {symbol}")
                continue
            
            # Verify required columns exist
            required_cols = ["Open", "High", "Low", "Close", "Volume"]
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                print(f"⚠️ Missing required columns for {symbol}: {missing_cols}")
                continue
            
            # Rename time column to Datetime for consistency
            if time_col != "Datetime":
                df = df.rename(columns={time_col: "Datetime"})
            
            # --------------------------------------------------
            # 8. Save to record.csv (for debugging)
            # --------------------------------------------------
            csv_cols = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
            df[csv_cols].to_csv("record.csv", index=False)
            print(f"💾 Saved {len(df)} rows to record.csv")
            
            # --------------------------------------------------
            # 9. Store in kline_data_map (TEMPORARY storage)
            # --------------------------------------------------
            state["kline_data_map"][symbol] = {
                "Datetime": df["Datetime"].astype(str).tolist(),
                "Open": df["Open"].tolist(),
                "High": df["High"].tolist(),
                "Low": df["Low"].tolist(),
                "Close": df["Close"].tolist(),
                "Volume": df["Volume"].tolist(),
            }
            
            fetched_count += 1
        
        # --------------------------------------------------
        # 10. Set context_ready if at least one dataset fetched
        # --------------------------------------------------
        if fetched_count > 0:
            state["context_ready"] = True
            print(f"✓ Fetch complete: {fetched_count}/{len(data_keys)} datasets ready")
        else:
            print(f"⚠️ No data fetched - context_ready remains false")
        
        return state

     return fetch_node


    # ============================================================
    # MAIN GRAPH
    # ============================================================
    def set_graph(self):

        # ----------------------------
        # AGENTS
        # ----------------------------
        indicator_agent = create_indicator_agent(self.graph_llm, self.toolkit)
        pattern_agent = create_pattern_agent(
            self.agent_llm, self.graph_llm, self.toolkit
        )
        trend_agent = create_trend_agent(
            self.agent_llm, self.graph_llm, self.toolkit
        )
        decision_agent = create_final_trade_decider(self.graph_llm)

        planner_node = create_planner_agent(self.graph_llm)
        fetch_node = self._fetch_data_node()

        # ----------------------------
        # ROUTER NODE (PASS STATE)
        # ----------------------------
        def router_node(state: TradingAdvisorState):
            return state

        # ----------------------------
        # ROUTE DECIDER (FIXED)
        # ----------------------------
        def route_decider(state: TradingAdvisorState):

            required = state.get("required_analyses", [])

            if not required:
                print("→ Router: No analyses required → END")
                return "end"

            next_step = required[0]

            # Allow decision-only flows without market data
            if next_step != "decision" and not state.get("context_ready", False):
                print("→ Router: context not ready → END")
                return "end"

            routing_map = {
                "indicator": "indicator_node",
                "pattern": "pattern_node",
                "trend": "trend_node",
                "decision": "decision_node",
            }

            route = routing_map.get(next_step, "end")
            print(f"→ Router: Next = {next_step} → {route}")
            return route


        # ----------------------------
        # AGENT WRAPPERS (CACHE-AWARE)
        # ----------------------------
        def run_indicator(state: TradingAdvisorState):
            """
            Run indicator agent with cache awareness.
            
            - Checks analysis_store for each required_analysis_key
            - Skips computation if indicator analysis already exists
            - Computes and stores ONLY indicator field if missing
            - Never overwrites other analysis fields
            """
            print("  ▸ Indicator Agent")
            
            from analysis_store_util import (
                init_analysis_entry, 
                has_field, 
                update_analysis_field,
                make_analysis_key
            )
            
            # Get execution keys for this query
            required_keys = state.get("required_analysis_keys", {})
            analysis_store = state.get("analysis_store", {})
            symbols = state.get("symbols", [])
            timeframe = state.get("timeframe", "")
            start_date = state.get("start_date", "")
            end_date = state.get("end_date", "")
            horizon = state.get("horizon", "")
            
            # Process each key that requires indicator analysis
            for key, analyses_needed in required_keys.items():
                if "indicator" not in analyses_needed:
                    continue
                
                # Check if indicator analysis already exists in cache
                if has_field(analysis_store, key, "indicator"):
                    print(f"  ✓ Indicator analysis cached for {key}")
                    continue
                
                # Initialize entry if needed
                init_analysis_entry(
                    analysis_store, 
                    key.split("|")[0],  # symbol
                    timeframe,
                    start_date,
                    end_date,
                    horizon
                )
                
                # Extract kline_data for the symbol
                symbol = key.split("|")[0]
                if symbol in state.get("kline_data_map", {}):
                    state["kline_data"] = state["kline_data_map"][symbol]
                else:
                    print(f"  ⚠️ No kline_data for {symbol}")
                    continue
                
                # Run indicator agent (computation)
                result = indicator_agent(state)
                
                # Store ONLY indicator field in analysis_store
                indicator_data = {
                    "report": result.get("indicator_report", ""),
                    "messages": result.get("messages", [])
                }
                update_analysis_field(analysis_store, key, "indicator", indicator_data)
                
                # Also update legacy state for backward compatibility
                state.update(result)
                
                print(f"  ✓ Indicator analysis computed and cached for {key}")
            
            # Remove indicator from required_analyses (per-turn tracking)
            state["required_analyses"] = [
                a for a in state.get("required_analyses", []) if a != "indicator"
            ]
            
            return state

        def run_pattern(state: TradingAdvisorState):
            """
            Run pattern agent with cache awareness.
            
            - Checks analysis_store for each required_analysis_key
            - Skips computation if pattern analysis already exists
            - Computes and stores ONLY pattern field if missing
            - Never overwrites other analysis fields
            """
            print("  ▸ Pattern Agent")
            
            from analysis_store_util import (
                init_analysis_entry, 
                has_field, 
                update_analysis_field
            )
            
            # Get execution keys for this query
            required_keys = state.get("required_analysis_keys", {})
            analysis_store = state.get("analysis_store", {})
            timeframe = state.get("timeframe", "")
            start_date = state.get("start_date", "")
            end_date = state.get("end_date", "")
            horizon = state.get("horizon", "")
            
            # Process each key that requires pattern analysis
            for key, analyses_needed in required_keys.items():
                if "pattern" not in analyses_needed:
                    continue
                
                # Check if pattern analysis already exists in cache
                if has_field(analysis_store, key, "pattern"):
                    print(f"  ✓ Pattern analysis cached for {key}")
                    continue
                
                # Initialize entry if needed
                init_analysis_entry(
                    analysis_store, 
                    key.split("|")[0],  # symbol
                    timeframe,
                    start_date,
                    end_date,
                    horizon
                )
                
                # Extract kline_data for the symbol
                symbol = key.split("|")[0]
                if symbol in state.get("kline_data_map", {}):
                    state["kline_data"] = state["kline_data_map"][symbol]
                else:
                    print(f"  ⚠️ No kline_data for {symbol}")
                    continue
                
                # Run pattern agent (computation)
                result = pattern_agent(state)
                
                # Store ONLY pattern field in analysis_store
                pattern_data = {
                    "report": result.get("pattern_report", ""),
                    "image": result.get("pattern_image", None),
                    "messages": result.get("messages", [])
                }
                update_analysis_field(analysis_store, key, "pattern", pattern_data)
                
                # Also update legacy state for backward compatibility
                state.update(result)
                
                print(f"  ✓ Pattern analysis computed and cached for {key}")
            
            # Remove pattern from required_analyses (per-turn tracking)
            state["required_analyses"] = [
                a for a in state.get("required_analyses", []) if a != "pattern"
            ]
            return state

        def run_trend(state: TradingAdvisorState):
            """
            Run trend agent with cache awareness.
            
            - Checks analysis_store for each required_analysis_key
            - Skips computation if trend analysis already exists
            - Computes and stores ONLY trend field if missing
            - Never overwrites other analysis fields
            """
            print("  ▸ Trend Agent")
            
            from analysis_store_util import (
                init_analysis_entry, 
                has_field, 
                update_analysis_field
            )
            
            # Get execution keys for this query
            required_keys = state.get("required_analysis_keys", {})
            analysis_store = state.get("analysis_store", {})
            timeframe = state.get("timeframe", "")
            start_date = state.get("start_date", "")
            end_date = state.get("end_date", "")
            horizon = state.get("horizon", "")
            
            # Process each key that requires trend analysis
            for key, analyses_needed in required_keys.items():
                if "trend" not in analyses_needed:
                    continue
                
                # Check if trend analysis already exists in cache
                if has_field(analysis_store, key, "trend"):
                    print(f"  ✓ Trend analysis cached for {key}")
                    continue
                
                # Initialize entry if needed
                init_analysis_entry(
                    analysis_store, 
                    key.split("|")[0],  # symbol
                    timeframe,
                    start_date,
                    end_date,
                    horizon
                )
                
                # Extract kline_data for the symbol
                symbol = key.split("|")[0]
                if symbol in state.get("kline_data_map", {}):
                    state["kline_data"] = state["kline_data_map"][symbol]
                else:
                    print(f"  ⚠️ No kline_data for {symbol}")
                    continue
                
                # Run trend agent (computation)
                result = trend_agent(state)
                
                # Store ONLY trend field in analysis_store
                trend_data = {
                    "report": result.get("trend_report", ""),
                    "image": result.get("trend_image", None),
                    "messages": result.get("messages", [])
                }
                update_analysis_field(analysis_store, key, "trend", trend_data)
                
                # Also update legacy state for backward compatibility
                state.update(result)
                
                print(f"  ✓ Trend analysis computed and cached for {key}")
            
            # Remove trend from required_analyses (per-turn tracking)
            state["required_analyses"] = [
                a for a in state.get("required_analyses", []) if a != "trend"
            ]
            return state

        def run_decision(state: TradingAdvisorState):
            """
            Decision agent router - selects mode based on intent.
            
            MODE 1: DECISION MODE (intent in ["advice", "trade", "compare", "trend_decision"])
            - Synthesizes cached analysis from analysis_store
            - Outputs BUY/SELL/HOLD decision
            - Stores decision back to analysis_store
            
            MODE 2: EXPLANATION MODE (intent in ["explain", "chat", "why", "price_check"])
            - Conversational responses using cached analysis
            - NO new analysis triggered
            - Uses existing decisions from analysis_store
            
            VALIDATION:
            - Before decision mode: Validates analysis keys match current query
            - Ensures no OHLCV data present in decision input
            - Triggers clarification if validation fails
            """
            print("  ▸ Decision Agent")
            
            # Determine mode based on intent
            intent = state.get("intent", "")
            decision_mode_intents = ["advice", "trade", "compare", "trend_decision"]
            explanation_mode_intents = ["explain", "chat", "why", "price_check", "historical"]
            
            if intent in decision_mode_intents:
                print(f"    → Decision Mode (intent: {intent})")
                
                # ═══════════════════════════════════════════════════════════
                # VALIDATION BEFORE DECISION MODE
                # ═══════════════════════════════════════════════════════════
                validation_failed = False
                validation_errors = []
                
                # VALIDATION 1: Ensure analysis keys match current query
                required_keys = state.get("required_analysis_keys", {})
                filtered_store = get_filtered_analysis_store(state)
                
                if not filtered_store and required_keys:
                    validation_errors.append("❌ No analysis available for required keys")
                    validation_failed = True
                
                # VALIDATION 2: Ensure no OHLCV data present in decision input
                # Decision agent should NEVER see raw kline_data
                kline_data = state.get("kline_data", None)
                if kline_data is not None and len(kline_data) > 0:
                    print("    ⚠️ WARNING: kline_data present in decision input (should be cleared)")
                    # Clear it to prevent pollution
                    state["kline_data"] = {}
                
                # LOGGING WARNINGS: Check for mixed contexts
                symbols = state.get("symbols", [])
                timeframe = state.get("timeframe", "")
                
                # Warning: Mixed symbols
                if len(symbols) > 1:
                    print(f"    ⚠️ WARNING: Mixed symbols in decision: {symbols}")
                
                # Warning: Mixed timeframes in analysis_store
                if filtered_store:
                    timeframes_in_store = set()
                    symbols_in_store = set()
                    for key, entry in filtered_store.items():
                        timeframes_in_store.add(entry.get("timeframe", ""))
                        symbols_in_store.add(entry.get("symbol", ""))
                    
                    if len(timeframes_in_store) > 1:
                        print(f"    ⚠️ WARNING: Mixed timeframes in analysis: {timeframes_in_store}")
                    
                    if len(symbols_in_store) > 1:
                        print(f"    ⚠️ WARNING: Multiple symbols in analysis: {symbols_in_store}")
                    
                    # Warning: Missing analysis fields
                    for key, entry in filtered_store.items():
                        missing_fields = []
                        if "indicator" not in entry or not entry["indicator"]:
                            missing_fields.append("indicator")
                        if "pattern" not in entry or not entry["pattern"]:
                            missing_fields.append("pattern")
                        if "trend" not in entry or not entry["trend"]:
                            missing_fields.append("trend")
                        
                        if missing_fields:
                            print(f"    ⚠️ WARNING: Missing analysis for {key}: {missing_fields}")
                            validation_errors.append(f"Missing analysis: {', '.join(missing_fields)}")
                            validation_failed = True
                
                # If validation failed, trigger clarification
                if validation_failed:
                    print("    ❌ VALIDATION FAILED - Triggering clarification")
                    clarification_msg = "I need to complete the analysis before making a decision.\n\n"
                    clarification_msg += "Issues found:\n"
                    for error in validation_errors:
                        clarification_msg += f"• {error}\n"
                    
                    return {
                        **state,
                        "intent": "clarify",
                        "explanation": clarification_msg,
                        "decision": "HOLD"
                    }
                
                print("    ✓ Validation passed - Proceeding with decision")
                
            elif intent in explanation_mode_intents:
                print(f"    → Explanation Mode (intent: {intent})")
            else:
                print(f"    → Default to Explanation Mode (intent: {intent})")

            # Run decision agent (internally routes based on intent)
            result = decision_agent(state)
            state.update(result)

            # Save decision output to file
            try:
                import os
                os.makedirs("output", exist_ok=True)
                decision = state.get('decision', 'N/A')
                explanation = state.get("explanation", "No explanation")
                # Handle list content
                if isinstance(decision, list):
                    decision = "\n".join(str(item) for item in decision)
                if isinstance(explanation, list):
                    explanation = "\n".join(str(item) for item in explanation)
                with open("output/decision.txt", "w", encoding="utf-8") as f:
                    f.write("=" * 60 + "\n")
                    f.write("FINAL DECISION\n")
                    f.write("=" * 60 + "\n")
                    f.write(f"Decision: {decision}\n\n")
                    f.write("Explanation:\n")
                    f.write(str(explanation) + "\n")
                    f.write("=" * 60 + "\n")
                print("💾 Saved decision to output/decision.txt")
            except Exception as e:
                print(f"⚠️ Could not save decision output: {e}")

            # Extract user question + system answer
            user_question = state.get("user_query", "")
            system_answer = (
                state.get("explanation")
                or state.get("decision")
                or ""
            )

            # ═══════════════════════════════════════════════════════════
            # UPDATE CONVERSATION SUMMARY (AFTER DECISION EXECUTION)
            # ═══════════════════════════════════════════════════════════
            # Summary rules:
            # - Keep concise (5-10 lines max)
            # - Capture: active symbols, horizons, decisions, user intent
            # - DO NOT include: prices, indicators, timestamps, raw text
            # - Passed to planner and decision agent ONLY
            # - NEVER passed to analysis agents
            if user_question and system_answer:
                state["conversation_summary"] = update_conversation_summary(
                    state=state,
                    user_question=user_question,
                    system_answer=system_answer,
                    llm=self.graph_llm
                )
                print(f"    ✓ Conversation summary updated ({len(state['conversation_summary'])} chars)")

            # Clear remaining analyses
            state["required_analyses"] = []

            return state

        # ----------------------------
        # BUILD GRAPH
        # ----------------------------
        graph = StateGraph(TradingAdvisorState)

        graph.add_node("planner", planner_node)
        graph.add_node("validator", validate_and_route)
        graph.add_node("fetch", fetch_node)
        graph.add_node("router", router_node)

        graph.add_node("indicator_node", run_indicator)
        graph.add_node("pattern_node", run_pattern)
        graph.add_node("trend_node", run_trend)
        graph.add_node("decision_node", run_decision)

        graph.add_edge(START, "planner")
        graph.add_edge("planner", "validator")
        graph.add_edge("validator", "fetch")
        graph.add_edge("fetch", "router")

        graph.add_conditional_edges(
            "router",
            route_decider,
            {
                "indicator_node": "indicator_node",
                "pattern_node": "pattern_node",
                "trend_node": "trend_node",
                "decision_node": "decision_node",
                "end": END,
            },
        )

        graph.add_edge("indicator_node", "router")
        graph.add_edge("pattern_node", "router")
        graph.add_edge("trend_node", "router")
        graph.add_edge("decision_node", "router")

        return graph.compile()


    # ============================================================
    # LEGACY GRAPH (IndicatorAgentState)
    # ============================================================
    def set_graph_legacy(self):
        """
        Legacy linear pipeline (kept untouched).
        """

        agent_nodes = {
            "indicator": create_indicator_agent(self.graph_llm, self.toolkit),
            "pattern": create_pattern_agent(
                self.agent_llm, self.graph_llm, self.toolkit
            ),
            "trend": create_trend_agent(
                self.agent_llm, self.graph_llm, self.toolkit
            ),
        }

        decision_agent_node = create_final_trade_decider(self.graph_llm)

        graph = StateGraph(IndicatorAgentState)

        def should_run_analysis(state):
            return "run_analysis" if state.get("should_analyze", False) else "context_only"

        graph.add_node("router", should_run_analysis)

        for agent_type, node in agent_nodes.items():
            graph.add_node(f"{agent_type.capitalize()} Agent", node)

        graph.add_node("Decision Maker", decision_agent_node)

        graph.add_edge(START, "router")

        graph.add_conditional_edges(
            "router",
            should_run_analysis,
            {
                "run_analysis": "Indicator Agent",
                "context_only": END,
            },
        )

        graph.add_edge("Indicator Agent", "Pattern Agent")
        graph.add_edge("Pattern Agent", "Trend Agent")
        graph.add_edge("Trend Agent", "Decision Maker")
        graph.add_edge("Decision Maker", END)

        return graph.compile()
