from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import json
import pandas as pd
import yfinance as yf
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from agent_state import DataContext, TradingAdvisorState
from agents.conversation_memory import update_conversation_summary
from agents.decision_agent_new import create_decision_agent
from agents.dialogue_agent import create_dialogue_agent
from graph_util import TechnicalTools
from agents.indicator_agent_new import create_indicator_agent
from agents.pattern_agent_new import create_pattern_agent
from agents.planner_agent import create_planner_agent, validate_and_route
from agents.trend_agent_new import create_trend_agent


def _ensure_state_defaults(state: Dict[str, Any]) -> Dict[str, Any]:
    state.setdefault("analysis_store", {})
    state.setdefault("conversation_summary", "")
    state.setdefault("user_preferences", {})
    state.setdefault("kline_data", {})
    state.setdefault("data_contexts_required", [])
    state.setdefault("analyses_required", {})
    state.setdefault("need_clarification", False)
    state.setdefault("intent", state.get("intent") or "trade")
    state.setdefault("explanation", None)
    return state


def _normalize_timeframe(value: str) -> str:
    """Best-effort normalization for legacy UI strings."""
    if not isinstance(value, str):
        return ""

    v = value.strip().lower()
    # web_interface expands: 4h->4hour, 15m->15min, 1d->1day
    if v.endswith("hour"):
        return v[:-4] + "h"
    if v.endswith("min"):
        return v[:-3] + "m"
    if v.endswith("day"):
        return v[:-3] + "d"
    if v == "1 week":
        return "1w"
    if v == "1 month":
        return "1mo"
    return value


def _infer_horizon_from_timeframe(timeframe: str) -> str:
    tf = timeframe.strip().lower()
    if tf.endswith("m") or tf.endswith("h"):
        return "intraday"
    if tf.endswith("d"):
        return "swing"
    return "long_term"


def _iso_from_any(dt: Any) -> str:
    parsed = pd.to_datetime(dt, errors="coerce")
    if pd.isna(parsed):
        # fallback to now UTC
        return datetime.now(timezone.utc).isoformat()
    if getattr(parsed, "tzinfo", None) is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _maybe_build_context_from_legacy_state(state: Dict[str, Any]) -> Optional[DataContext]:
    """Adapt legacy web_interface initial_state into a DataContext + analyses_required.

    Legacy state often looks like:
      {
        "kline_data": {"Datetime": [...], "Open": [...], ...},
        "stock_name": "BTC-USD",
        "time_frame": "4hour" (or similar)
      }

    We derive start/end from the provided Datetime column (not inferred).
    """

    kline_data = state.get("kline_data")
    if not isinstance(kline_data, dict):
        return None

    # If it's already keyed by DataContext.key, leave it alone
    if kline_data and all(isinstance(v, dict) and "Datetime" in v for v in kline_data.values()):
        # already in new shape
        return None

    required_cols = {"Datetime", "Open", "High", "Low", "Close"}
    if not required_cols.issubset(set(kline_data.keys())):
        return None

    symbol = state.get("stock_name") or state.get("symbol")
    timeframe_raw = state.get("time_frame") or state.get("timeframe")
    if not symbol or not timeframe_raw:
        return None

    timeframe = _normalize_timeframe(str(timeframe_raw))

    dt_list = kline_data.get("Datetime")
    if not isinstance(dt_list, list) or not dt_list:
        return None

    start_iso = _iso_from_any(dt_list[0])
    end_iso = _iso_from_any(dt_list[-1])

    ctx_key = f"{symbol}|{timeframe}|{start_iso}:{end_iso}"

    ctx: DataContext = {
        "key": ctx_key,
        "symbol": str(symbol),
        "timeframe": timeframe,
        "start_datetime": start_iso,
        "end_datetime": end_iso,
    }

    # Wrap legacy kline_data into new shape
    state["kline_data"] = {ctx_key: kline_data}

    # Provide a default plan if the legacy caller didn't provide one
    if not state.get("analyses_required"):
        horizon = _infer_horizon_from_timeframe(timeframe)
        state["analyses_required"] = {
            ctx_key: {
                "horizon": horizon,
                "run": ["indicator", "pattern", "trend", "decision"],
            }
        }
    if not state.get("data_contexts_required"):
        state["data_contexts_required"] = [ctx]

    return ctx


class SetGraph:
    def __init__(
        self,
        agent_llm: ChatOpenAI,
        graph_llm: ChatOpenAI,
        toolkit: TechnicalTools,
    ):
        self.agent_llm = agent_llm
        self.graph_llm = graph_llm
        self.toolkit = toolkit

    def _normalize_node(self):
        def node(state: TradingAdvisorState) -> Dict[str, Any]:
            state = _ensure_state_defaults(state)
            _maybe_build_context_from_legacy_state(state)
            return state

        return node

    def _fetch_data_node(self):
        def node(state: TradingAdvisorState) -> Dict[str, Any]:
            state = _ensure_state_defaults(state)

            contexts: List[Dict[str, Any]] = state.get("data_contexts_required") or []
            if not contexts:
                return state

            kline_data: Dict[str, Dict[str, Any]] = state.get("kline_data") or {}

            for ctx in contexts:
                ctx_key = ctx.get("key")
                if not ctx_key:
                    continue
                if ctx_key in kline_data and kline_data[ctx_key]:
                    continue

                symbol = ctx.get("symbol")
                timeframe = ctx.get("timeframe")
                start_dt = pd.to_datetime(ctx.get("start_datetime"), errors="coerce")
                end_dt = pd.to_datetime(ctx.get("end_datetime"), errors="coerce")

                if pd.isna(start_dt) or pd.isna(end_dt) or not symbol or not timeframe:
                    continue

                # yfinance end is exclusive; pad slightly to include last candle
                fetch_end = end_dt
                if end_dt == start_dt:
                    fetch_end = end_dt + timedelta(days=1)

                df = yf.download(
                    tickers=symbol,
                    start=start_dt,
                    end=fetch_end,
                    interval=timeframe,
                    auto_adjust=True,
                    progress=False,
                )

                if df is None or df.empty:
                    continue

                df = df.reset_index()
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                time_col = "Datetime" if "Datetime" in df.columns else ("Date" if "Date" in df.columns else None)
                if not time_col:
                    continue

                if time_col != "Datetime":
                    df = df.rename(columns={time_col: "Datetime"})

                required_cols = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
                for col in required_cols:
                    if col not in df.columns:
                        # tolerate missing Volume
                        if col == "Volume":
                            df["Volume"] = 0
                        else:
                            return state

                df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce")
                df = df.dropna(subset=["Datetime"])

                kline_data[ctx_key] = {
                    "Datetime": df["Datetime"].dt.strftime("%Y-%m-%d %H:%M:%S").tolist(),
                    "Open": df["Open"].astype(float).tolist(),
                    "High": df["High"].astype(float).tolist(),
                    "Low": df["Low"].astype(float).tolist(),
                    "Close": df["Close"].astype(float).tolist(),
                    "Volume": df["Volume"].astype(float).tolist(),
                }

            return {"kline_data": kline_data}

        return node

    def _adapt_outputs_node(self):
        """Populate legacy UI fields from analysis_store for web_interface compatibility."""

        def node(state: TradingAdvisorState) -> Dict[str, Any]:
            analyses_required = state.get("analyses_required") or {}
            analysis_store = state.get("analysis_store") or {}

            if not analyses_required:
                return {}

            # Take first context in plan for legacy display fields
            ctx_key = next(iter(analyses_required.keys()))
            spec = analyses_required.get(ctx_key) or {}
            horizon = spec.get("horizon")
            if not horizon:
                return {}

            parts = ctx_key.split("|")
            if len(parts) != 3:
                return {}

            symbol = parts[0]
            timeframe = parts[1]
            start_datetime, end_datetime = parts[2].split(":")

            store_key = f"{symbol}|{timeframe}|{start_datetime}:{end_datetime}|{horizon}"
            entry = analysis_store.get(store_key) or {}

            indicator_report = (
                (entry.get("indicator") or {}).get("result") or {}
            ).get("interpretation", "")
            pattern_report = (
                (entry.get("pattern") or {}).get("result") or {}
            ).get("interpretation", "")
            trend_report = (
                (entry.get("trend") or {}).get("result") or {}
            ).get("interpretation", "")

            decision_obj = (entry.get("decision") or {}).get("result")
            final_trade_decision = ""
            if isinstance(decision_obj, dict):
                final_trade_decision = json.dumps(decision_obj)

            out: Dict[str, Any] = {
                "indicator_report": indicator_report,
                "pattern_report": pattern_report,
                "trend_report": trend_report,
                "final_trade_decision": final_trade_decision,
            }

            if isinstance(decision_obj, dict):
                out["decision"] = decision_obj

            return out

        return node

    def _dialogue_node(self):
        dialogue = create_dialogue_agent(self.agent_llm)

        def node(state: TradingAdvisorState) -> Dict[str, Any]:
            return dialogue(state)

        return node

    def _memory_node(self):
        def node(state: TradingAdvisorState) -> Dict[str, Any]:
            summary = update_conversation_summary(
                state.get("conversation_summary", ""),
                state.get("user_query") or "",
                state.get("explanation") or "",
            )
            return {"conversation_summary": summary}

        return node

    def _cleanup_node(self):
        def node(state: TradingAdvisorState) -> Dict[str, Any]:
            # Clear per-turn temporary market data
            return {"kline_data": {}}

        return node

    def set_graph(self):
        indicator_agent = create_indicator_agent(self.graph_llm, self.toolkit)
        pattern_agent = create_pattern_agent(self.agent_llm, self.graph_llm, self.toolkit)
        trend_agent = create_trend_agent(self.agent_llm, self.graph_llm, self.toolkit)
        decision_agent = create_decision_agent(self.agent_llm)

        planner_node = create_planner_agent(self.graph_llm)

        graph: StateGraph = StateGraph(TradingAdvisorState)

        graph.add_node("normalize", self._normalize_node())
        graph.add_node("planner", planner_node)
        graph.add_node("validator", validate_and_route)
        graph.add_node("fetch", self._fetch_data_node())
        graph.add_node("indicator", indicator_agent)
        graph.add_node("pattern", pattern_agent)
        graph.add_node("trend", trend_agent)
        graph.add_node("decision", decision_agent)
        graph.add_node("adapt", self._adapt_outputs_node())
        graph.add_node("dialogue", self._dialogue_node())
        graph.add_node("memory", self._memory_node())
        graph.add_node("cleanup", self._cleanup_node())

        def route_after_normalize(state: Dict[str, Any]) -> str:
            # If user_query exists, run planner
            if state.get("user_query"):
                return "planner"
            # If a plan already exists (legacy adapter or external caller), proceed
            if state.get("analyses_required"):
                return "fetch"
            return "end"

        def route_after_validate(state: Dict[str, Any]) -> str:
            if state.get("intent") == "clarify" and state.get("explanation"):
                return "dialogue"
            return "fetch"

        graph.add_edge(START, "normalize")
        graph.add_conditional_edges(
            "normalize",
            route_after_normalize,
            {"planner": "planner", "fetch": "fetch", "end": END},
        )

        graph.add_edge("planner", "validator")
        graph.add_conditional_edges("validator", route_after_validate, {"fetch": "fetch", "dialogue": "dialogue"})

        graph.add_edge("fetch", "indicator")
        graph.add_edge("indicator", "pattern")
        graph.add_edge("pattern", "trend")
        graph.add_edge("trend", "decision")
        graph.add_edge("decision", "adapt")
        graph.add_edge("adapt", "dialogue")
        graph.add_edge("dialogue", "memory")
        graph.add_edge("memory", "cleanup")
        graph.add_edge("cleanup", END)

        return graph.compile()
