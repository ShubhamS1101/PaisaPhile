"""
Indicator Agent with per-agent freshness tracking and horizon-aware caching.

This agent:
1. Reads analyses_required dict from state
2. Checks freshness of cached indicator analysis before running
3. Computes indicators only if cache is stale or missing
4. Stores results with metadata (created_at, fresh_until)
5. Tracks upstream_agents_reran for decision invalidation
"""

import copy
import json
import pandas as pd
from typing import Dict, Any

from langchain_core.messages import ToolMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from analysis_store_util import (
    calculate_indicator_freshness,
    force_dependents_to_run,
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
            
            # Cascade: indicator recomputed → force trend + decision to rerun
            force_dependents_to_run(state, window_key, "indicator")
            
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
    Execute indicator computation using LLM and tools.
    
    Returns:
        Dict with indicator values (RSI, MACD, etc.) and interpretation
    """
    # Tool definitions
    tools = [
        toolkit.compute_macd,
        toolkit.compute_rsi,
        toolkit.compute_roc,
        toolkit.compute_stoch,
        toolkit.compute_willr,
    ]
    
    # System prompt tailored to horizon
    horizon_context = {
        "intraday": "short-term intraday trading with quick entry/exit",
        "swing": "swing trading over several days",
        "long_term": "long-term trend following over weeks/months"
    }
    
    system_msg = (
        f"You are a technical indicator analyst for {horizon_context.get(horizon, 'trading')}. "
        f"Analyze indicators for {timeframe} timeframe data. "
        "You have access to: compute_rsi, compute_macd, compute_roc, compute_stoch, compute_willr. "
        "Compute relevant indicators and provide interpretation focused on the trading horizon. "
        f"Focus on {horizon} signals."
    )
    
    # Build prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        MessagesPlaceholder(variable_name="messages"),
    ])
    
    chain = prompt | llm.bind_tools(tools)
    
    # Get data overview for context
    df = pd.DataFrame(kline_data)
    candle_count = len(df)
    latest_close = df['Close'].iloc[-1] if not df.empty else 0
    
    # Initial message with explicit instruction to use tools
    messages = [HumanMessage(content=(
        f"You have {candle_count} candles of {timeframe} OHLCV data (latest close: {latest_close:.2f}). "
        f"Analyze technical indicators for {horizon} trading.\n\n"
        f"REQUIRED: You MUST call the following indicator tools:\n"
        f"1. compute_rsi - RSI momentum indicator\n"
        f"2. compute_macd - MACD trend indicator\n"
        f"3. compute_roc - Rate of Change indicator\n"
        f"4. compute_stoch - Stochastic oscillator\n"
        f"5. compute_willr - Williams %R indicator\n\n"
        f"Call ALL these tools to compute indicators, then provide your interpretation."
    ))]
    
    # Step 1: Request tool calls
    ai_response = chain.invoke({"messages": messages})
    messages.append(ai_response)
    
    print(f"\n🤖 LLM Response for {horizon} {timeframe}:")
    print(f"   Has tool_calls attr: {hasattr(ai_response, 'tool_calls')}")
    if hasattr(ai_response, "tool_calls"):
        print(f"   Tool calls: {len(ai_response.tool_calls) if ai_response.tool_calls else 0}")
        if ai_response.tool_calls:
            for tc in ai_response.tool_calls:
                print(f"      - {tc.get('name', 'unknown')}")
    print(f"   Content preview: {ai_response.content[:200] if ai_response.content else 'None'}...")
    
    # Step 2: Execute tool calls
    tool_results = {}
    if hasattr(ai_response, "tool_calls") and ai_response.tool_calls:
        for call in ai_response.tool_calls:
            tool_name = call["name"]
            tool_args = call["args"]
            tool_args["kline_data"] = copy.deepcopy(kline_data)
            
            # Execute tool
            tool_fn = next(t for t in tools if t.name == tool_name)
            tool_result = tool_fn.invoke(tool_args)
            tool_results[tool_name] = tool_result
            
            # Add to messages
            messages.append(
                ToolMessage(
                    tool_call_id=call["id"],
                    content=json.dumps(tool_result)
                )
            )
    
    # Step 3: Get final interpretation
    max_iterations = 5
    for iteration in range(max_iterations):
        final_response = chain.invoke({"messages": messages})
        messages.append(final_response)
        
        # Check if done
        if not hasattr(final_response, "tool_calls") or not final_response.tool_calls:
            break
        
        # Execute any additional tool calls
        for call in final_response.tool_calls:
            tool_name = call["name"]
            tool_args = call["args"]
            tool_args["kline_data"] = copy.deepcopy(kline_data)
            tool_fn = next(t for t in tools if t.name == tool_name)
            tool_result = tool_fn.invoke(tool_args)
            tool_results[tool_name] = tool_result
            messages.append(
                ToolMessage(
                    tool_call_id=call["id"],
                    content=json.dumps(tool_result)
                )
            )
    
    # Extract interpretation
    if final_response:
        # Handle both string and list-based content formats
        if isinstance(final_response.content, list):
            # New format: [{'type': 'text', 'text': '...'}]
            interpretation = "".join(
                block.get('text', '') for block in final_response.content 
                if isinstance(block, dict) and block.get('type') == 'text'
            )
        else:
            # Old format: simple string
            interpretation = final_response.content
    else:
        interpretation = "Analysis completed"
    
    # Fallback if no tools were called - compute indicators directly
    if not tool_results:
        print(f"⚠️ Indicator agent: LLM did not call any tools for {horizon} {timeframe}")
        print(f"   🔧 Computing indicators directly as fallback...")
        
        # Compute all indicators directly
        for tool in tools:
            try:
                result = tool.invoke({"kline_data": copy.deepcopy(kline_data)})
                tool_results[tool.name] = result
                print(f"      ✓ {tool.name}: {result}")
            except Exception as e:
                print(f"      ✗ {tool.name} failed: {e}")
        
        # Generate interpretation based on computed values
        if tool_results:
            interpretation = f"Computed {len(tool_results)} indicators for {horizon} {timeframe}. "
            
            # Basic interpretation - extract latest values from arrays
            rsi_data = tool_results.get("compute_rsi", {})
            rsi_array = rsi_data.get("rsi", [])
            rsi_val = rsi_array[-1] if rsi_array else None
            
            macd_data = tool_results.get("compute_macd", {})
            macd_array = macd_data.get("macd", [])
            macd_signal_array = macd_data.get("macd_signal", [])
            macd_val = macd_array[-1] if macd_array else None
            macd_signal_val = macd_signal_array[-1] if macd_signal_array else None
            
            roc_data = tool_results.get("compute_roc", {})
            roc_array = roc_data.get("roc", [])
            roc_val = roc_array[-1] if roc_array else None
            
            stoch_data = tool_results.get("compute_stoch", {})
            stoch_k_array = stoch_data.get("stoch_k", [])
            stoch_k_val = stoch_k_array[-1] if stoch_k_array else None
            
            willr_data = tool_results.get("compute_willr", {})
            willr_array = willr_data.get("willr", [])
            willr_val = willr_array[-1] if willr_array else None
            
            # Add detailed interpretation
            if rsi_val is not None:
                if rsi_val > 70:
                    interpretation += f"RSI={rsi_val:.1f} (overbought). "
                elif rsi_val < 30:
                    interpretation += f"RSI={rsi_val:.1f} (oversold). "
                else:
                    interpretation += f"RSI={rsi_val:.1f} (neutral). "
            
            if macd_val is not None and macd_signal_val is not None:
                if macd_val > macd_signal_val:
                    interpretation += f"MACD={macd_val:.2f} above signal={macd_signal_val:.2f} (bullish). "
                else:
                    interpretation += f"MACD={macd_val:.2f} below signal={macd_signal_val:.2f} (bearish). "
            
            if roc_val is not None:
                interpretation += f"ROC={roc_val:.2f}%. "
            
            if stoch_k_val is not None:
                if stoch_k_val > 80:
                    interpretation += f"Stochastic=%K={stoch_k_val:.1f} (overbought). "
                elif stoch_k_val < 20:
                    interpretation += f"Stochastic=%K={stoch_k_val:.1f} (oversold). "
                else:
                    interpretation += f"Stochastic=%K={stoch_k_val:.1f}. "
            
            if willr_val is not None:
                interpretation += f"Williams %R={willr_val:.1f}. "
        else:
            interpretation = "Unable to compute indicators - all tool executions failed."
    
    # Return structured result
    return {
        "tool_results": tool_results,
        "interpretation": interpretation,
        "indicators_computed": list(tool_results.keys())
    }
