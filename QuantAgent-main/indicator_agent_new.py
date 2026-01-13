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
from typing import Dict, Any

from langchain_core.messages import ToolMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from analysis_store_util import (
    calculate_indicator_freshness,
    is_agent_output_fresh,
    make_analysis_store_key,
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
        
        # Process each data context
        for context_key, spec in analyses_required.items():
            # Check if indicator is required for this context
            if "indicator" not in spec.get("run", []):
                continue

            horizon = spec.get("horizon")
            if not horizon:
                spec["run"].remove("indicator")
                continue

            # context_key: "{symbol}|{timeframe}|{start}:{end}"
            parts = context_key.split("|")
            if len(parts) != 3:
                spec["run"].remove("indicator")
                continue
            symbol = parts[0]
            timeframe = parts[1]
            start_datetime, end_datetime = parts[2].split(":")

            store_key = make_analysis_store_key(
                symbol=symbol,
                timeframe=timeframe,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                horizon=horizon,
            )
            
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
            
            # Get kline data for this context
            context_kline_data = kline_data.get(context_key, {})
            if not context_kline_data:
                print(f"⚠️ No kline data available for {context_key}")
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
    
    # Initial message
    messages = [HumanMessage(content=f"Analyze indicators for this {timeframe} data focusing on {horizon} trading.")]
    
    # Step 1: Request tool calls
    ai_response = chain.invoke({"messages": messages})
    messages.append(ai_response)
    
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
    interpretation = final_response.content if final_response else "Analysis completed"
    
    # Return structured result
    return {
        "tool_results": tool_results,
        "interpretation": interpretation,
        "indicators_computed": list(tool_results.keys())
    }
