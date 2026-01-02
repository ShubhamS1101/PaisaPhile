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

        # --------------------------------------------------
        # 1. Fetch only if planner says data is required
        # --------------------------------------------------
        if state.get("data_requirement") != "required":
            return state

        symbols = state.get("symbols", [])
        timeframe = state.get("timeframe")
        start_date = state.get("start_date")
        end_date = state.get("end_date")

        # --------------------------------------------------
        # 2. Hard safety checks (planner contract)
        # --------------------------------------------------
        if not symbols or not timeframe or not start_date or not end_date:
            print("⚠️ Fetch skipped: missing required fetch parameters")
            return state
        
        # --------------------------------------------------
        # 3. Check if ALL requested symbols are already cached
        # --------------------------------------------------
        all_cached = all(symbol in state["kline_data_map"] for symbol in symbols)
        if all_cached:
            print(f"✓ All symbols already cached: {symbols}")
            state["context_ready"] = True
            return state

        fetched_any = False

        # --------------------------------------------------
        # 4. Fetch data symbol-by-symbol (skip cached ones)
        # --------------------------------------------------
        for symbol in symbols:

            if symbol in state["kline_data_map"]:
                print(f"✓ Using cached data for {symbol}")
                continue

            # --------------------------------------------------
            # 🔥 FIX: Adjust end_date for yfinance (exclusive end)
            # --------------------------------------------------
            # yfinance's end parameter is EXCLUSIVE, so we need to add 1 day
            # to include the requested date in the results
            from datetime import datetime, timedelta
            
            fetch_start = start_date
            fetch_end = end_date
            
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                
                # If querying a single date, extend end by 1 day
                if start_dt == end_dt:
                    fetch_end = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                    print(f"ℹ️  Single date query detected - extending end_date to {fetch_end}")
                # If date range is very narrow (< 2 days), extend by 1 day for safety
                elif (end_dt - start_dt).days < 2:
                    fetch_end = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                    print(f"ℹ️  Narrow date range - extending end_date to {fetch_end}")
            except ValueError:
                # If date parsing fails, use original dates
                pass

            print(
                f"📥 Fetching {symbol} | "
                f"TF={timeframe} | "
                f"{fetch_start} → {fetch_end}"
            )

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
                
                # Try fetching a wider range (7 days before the target date)
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
            # 🔥 NORMALIZE COLUMNS (CRITICAL FIX)
            # --------------------------------------------------
            # Handle MultiIndex columns from yfinance
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # Ensure columns are strings
            df.columns = df.columns.astype(str)
            
            # --------------------------------------------------
            # 🔥 NORMALIZE TIME COLUMN
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
            
            # --------------------------------------------------
            # 💾 SAVE TO CSV (for visibility and debugging)
            # --------------------------------------------------
            # Rename time column to Datetime for consistency
            if time_col != "Datetime":
                df = df.rename(columns={time_col: "Datetime"})
            
            # Save to record.csv (overwrites previous data)
            csv_cols = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
            df[csv_cols].to_csv("record.csv", index=False)
            print(f"💾 Saved {len(df)} rows to record.csv")

            state["kline_data_map"][symbol] = {
                "Datetime": df["Datetime"].astype(str).tolist(),
                "Open": df["Open"].tolist(),
                "High": df["High"].tolist(),
                "Low": df["Low"].tolist(),
                "Close": df["Close"].tolist(),
                "Volume": df["Volume"].tolist(),
            }

            fetched_any = True

        # --------------------------------------------------
        # 5. Mark context ready ONLY if something was fetched
        # --------------------------------------------------
        if fetched_any:
            state["context_ready"] = True

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
        # AGENT WRAPPERS
        # ----------------------------
        def run_indicator(state: TradingAdvisorState):
            print("  ▸ Indicator Agent")
            # Extract kline_data for the first symbol
            symbols = state.get("symbols", [])
            if symbols and symbols[0] in state["kline_data_map"]:
                state["kline_data"] = state["kline_data_map"][symbols[0]]
            result = indicator_agent(state)
            # Merge result into state
            state.update(result)
            state["required_analyses"] = [
                a for a in state.get("required_analyses", []) if a != "indicator"
            ]
            return state

        def run_pattern(state: TradingAdvisorState):
            print("  ▸ Pattern Agent")
            # Extract kline_data for the first symbol
            symbols = state.get("symbols", [])
            if symbols and symbols[0] in state["kline_data_map"]:
                state["kline_data"] = state["kline_data_map"][symbols[0]]
            result = pattern_agent(state)
            # Merge result into state
            state.update(result)
            state["required_analyses"] = [
                a for a in state.get("required_analyses", []) if a != "pattern"
            ]
            return state

        def run_trend(state: TradingAdvisorState):
            print("  ▸ Trend Agent")
            # Extract kline_data for the first symbol
            symbols = state.get("symbols", [])
            if symbols and symbols[0] in state["kline_data_map"]:
                state["kline_data"] = state["kline_data_map"][symbols[0]]
            result = trend_agent(state)
            # Merge result into state
            state.update(result)
            state["required_analyses"] = [
                a for a in state.get("required_analyses", []) if a != "trend"
            ]
            return state

        def run_decision(state: TradingAdvisorState):
            print("  ▸ Decision Agent")

            # Run decision agent
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

            # Update rolling conversation summary
            if user_question and system_answer:
                state["conversation_summary"] = update_conversation_summary(
                    state=state,
                    user_question=user_question,
                    system_answer=system_answer,
                    llm=self.graph_llm
                )

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
