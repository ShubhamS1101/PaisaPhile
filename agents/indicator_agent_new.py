"""
Indicator Agent — deterministic computation + LLM interpretation.

This agent:
1. Reads analyses_required dict from state
2. Checks freshness of cached indicator analysis before running
3. Computes ALL indicators deterministically (no LLM tool-calling)
4. Builds a time-aligned indicator table (Datetime × indicators)
5. Passes the table to the LLM for interpretation only
6. Stores results with metadata (created_at, fresh_until)
"""

import copy
import json
import pandas as pd
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate

from analysis_store_util import (
    calculate_indicator_freshness,
    is_agent_output_fresh,
    parse_window_key,
    store_agent_output,
)
from freshness_config import get_current_time_iso


def create_indicator_agent(llm, toolkit):
    """
    Create indicator analysis agent with freshness tracking.
    """

    def indicator_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process all indicator analysis requests from analyses_required.
        """
        analyses_required = state.get("analyses_required", {})
        analysis_store = state.get("analysis_store", {})
        kline_data = state.get("kline_data", {})
        
        # Process each window
        for window_key, spec in analyses_required.items():
            # Check if indicator is required for this window
            if "indicator" not in spec.get("run", []):
                continue

            # Parse window key to get symbol/timeframe/horizon
            try:
                parsed = parse_window_key(window_key)
            except ValueError:
                spec["run"].remove("indicator")
                continue

            symbol = parsed["symbol"]
            timeframe = parsed["timeframe"]
            horizon = parsed["horizon"]

            # store_key IS window_key in the new model
            store_key = window_key
            
            # Get current time
            current_time = get_current_time_iso()
            
            # CHECK FRESHNESS
            if is_agent_output_fresh(analysis_store, store_key, "indicator", current_time):
                print(f"✅ Indicator analysis CACHED and FRESH for {symbol}|{timeframe}|{horizon}")
                # Remove from run list
                spec["run"].remove("indicator")
                continue
            
            # CACHE MISS or STALE - Run indicator analysis
            print(f"🔄 Running indicator analysis for {symbol}|{timeframe}|{horizon}")
            print(f"   Window key: {window_key}")
            
            # Get kline data for this window
            context_kline_data = kline_data.get(window_key, {})
            if not context_kline_data:
                print(f"⚠️ No kline data available for {window_key}")
                print(f"   Available kline_data keys: {list(kline_data.keys())}")
                spec["run"].remove("indicator")
                continue
            
            # Run indicator computation
            indicator_result = _run_indicator_analysis(
                llm=llm,
                toolkit=toolkit,
                kline_data=context_kline_data,
                timeframe=timeframe,
                horizon=horizon
            )
            
            # Calculate freshness
            fresh_until = calculate_indicator_freshness(current_time, timeframe)
            
            # Prepare metadata
            metadata = {
                "agent": "indicator",
                "created_at": current_time,
                "ran_at": current_time,
                "fresh_until": fresh_until,
                "timeframe": timeframe,
                "horizon": horizon,
                "symbol": symbol
            }
            
            # Store in analysis_store
            store_agent_output(
                analysis_store=analysis_store,
                store_key=store_key,
                agent_name="indicator",
                data=indicator_result,
                metadata=metadata
            )
            
            print(f"💾 Stored indicator analysis (fresh until {fresh_until})")
            
            # Remove from run list
            spec["run"].remove("indicator")

        return {"analysis_store": analysis_store}
    
    return indicator_agent_node


def _run_indicator_analysis(
    llm,
    toolkit,
    kline_data: Dict[str, Any],
    timeframe: str,
    horizon: str
) -> Dict[str, Any]:
    """
    Deterministically compute all indicators, build a time-aligned table,
    then pass the table to the LLM for interpretation only.

    Returns:
        Dict with indicator_table (list of row dicts), tool_results,
        interpretation, and indicators_computed.
    """
    # ------------------------------------------------------------------
    # 1. Compute every indicator deterministically — NO LLM tool calls
    # ------------------------------------------------------------------
    kline_copy = copy.deepcopy(kline_data)
    tool_results: Dict[str, Any] = {}
    tool_fns = {
        "compute_macd":  toolkit.compute_macd,
        "compute_rsi":   toolkit.compute_rsi,
        "compute_roc":   toolkit.compute_roc,
        "compute_stoch": toolkit.compute_stoch,
        "compute_willr": toolkit.compute_willr,
    }
    for name, fn in tool_fns.items():
        try:
            result = fn.invoke({"kline_data": copy.deepcopy(kline_copy)})
            tool_results[name] = result
            print(f"   ✓ {name}")
        except Exception as e:
            print(f"   ✗ {name} failed: {e}")

    # ------------------------------------------------------------------
    # 2. Build a time-aligned indicator table
    #    Columns: Datetime | Close | MACD | Signal | Hist | RSI | ROC
    #             | Stoch_K | Stoch_D | WillR
    # ------------------------------------------------------------------
    datetimes = kline_data.get("Datetime", [])
    closes    = kline_data.get("Close", [])
    n = len(closes)                       # total candle count

    # Helper: right-align a shorter array to length n with None padding
    def _align(arr: list, total: int = n) -> list:
        if len(arr) >= total:
            return arr[-total:]
        return [None] * (total - len(arr)) + arr

    # Extract arrays from tool_results
    macd_raw  = tool_results.get("compute_macd", {})
    rsi_raw   = tool_results.get("compute_rsi", {})
    roc_raw   = tool_results.get("compute_roc", {})
    stoch_raw = tool_results.get("compute_stoch", {})
    willr_raw = tool_results.get("compute_willr", {})

    macd_arr    = _align(macd_raw.get("macd", []))
    signal_arr  = _align(macd_raw.get("macd_signal", []))
    hist_arr    = _align(macd_raw.get("macd_hist", []))
    rsi_arr     = _align(rsi_raw.get("rsi", []))
    roc_arr     = _align(roc_raw.get("roc", []))
    stoch_k_arr = _align(stoch_raw.get("stoch_k", []))
    stoch_d_arr = _align(stoch_raw.get("stoch_d", []))
    willr_arr   = _align(willr_raw.get("willr", []))

    # Build DataFrame
    table_df = pd.DataFrame({
        "Datetime":    datetimes[-n:] if len(datetimes) >= n else datetimes,
        "Close":       closes,
        "MACD":        macd_arr,
        "MACD_Signal": signal_arr,
        "MACD_Hist":   hist_arr,
        "RSI":         rsi_arr,
        "ROC":         roc_arr,
        "Stoch_K":     stoch_k_arr,
        "Stoch_D":     stoch_d_arr,
        "WillR":       willr_arr,
    })

    # Keep only the last 28 rows so the prompt stays concise
    table_df = table_df.tail(28).reset_index(drop=True)

    # Convert to a clean text table for the LLM
    table_text = table_df.to_string(index=False, na_rep="-")

    # Also keep a serialisable version for storage
    indicator_table: List[Dict[str, Any]] = (
        table_df.where(table_df.notna(), None).to_dict(orient="records")
    )

    print(f"\n📊 Indicator table ({len(table_df)} rows):")
    print(table_text[:600])  # preview

    # ------------------------------------------------------------------
    # 3. Ask the LLM to interpret the table (no tools, just text)
    # ------------------------------------------------------------------
    horizon_context = {
        "intraday": "short-term intraday trading with quick entry/exit",
        "swing":    "swing trading over several days",
        "long_term": "long-term trend following over weeks/months",
    }

    system_msg = (
        f"You are a technical indicator analyst for {horizon_context.get(horizon, 'trading')}.\n"
        f"Timeframe: {timeframe}.  Horizon: {horizon}.\n\n"
        "Below is a table of OHLCV-derived indicators computed over the most recent candles.\n"
        "Columns: Datetime, Close, MACD, MACD_Signal, MACD_Hist, RSI, ROC, "
        "Stoch_K, Stoch_D, WillR.\n\n"
        "Your job:\n"
        "1. Summarise the current state of each indicator (latest values + recent direction).\n"
        "2. Note any overbought / oversold / crossover / divergence signals.\n"
        "3. Give an overall indicator-based bias (bullish / bearish / neutral) "
        f"appropriate for a {horizon} horizon.\n"
        "Be concise but specific — cite the numbers."
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("human", "{table}"),
    ])

    chain = prompt | llm
    ai_response = chain.invoke({"table": table_text})

    # Extract interpretation text
    if isinstance(ai_response.content, list):
        interpretation = "".join(
            block.get("text", "")
            for block in ai_response.content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    else:
        interpretation = ai_response.content or "Analysis completed."

    print(f"\n🤖 LLM Interpretation ({len(interpretation)} chars)")

    # ------------------------------------------------------------------
    # 4. Return structured result
    # ------------------------------------------------------------------
    return {
        "indicator_table": indicator_table,
        "tool_results": tool_results,
        "interpretation": interpretation,
        "indicators_computed": list(tool_results.keys()),
    }
