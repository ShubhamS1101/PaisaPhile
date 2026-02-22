"""
Trend Agent — deterministic execution via resolve_run_lists().

This agent:
1. Reads analyses_required dict from state
2. Executes ONLY if "trend" is in the resolved run list
3. Generates trendline charts and stores results with freshness metadata
4. Triggers downstream cascade (decision) via force_dependents_to_run
"""

import copy
import json
import os
from typing import Dict, Any
from datetime import datetime

from langchain_core.messages import ToolMessage, HumanMessage, SystemMessage

from analysis_store_util import (
    calculate_trend_freshness,
    force_dependents_to_run,
    parse_window_key,
    store_agent_output,
)
from freshness_config import get_current_time_iso, parse_iso_datetime
from chart_manager import make_chart_path, ensure_chart_dirs


def create_trend_agent(tool_llm, graph_llm, toolkit):
    """
    Create trend analysis agent with freshness tracking and chart management.
    """

    def trend_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process all trend analysis requests from analyses_required.
        
        The run list is DETERMINISTICALLY resolved by resolve_run_lists()
        before this agent executes.  If "trend" is in run → execute.
        """
        analyses_required = state.get("analyses_required", {})
        analysis_store = state.get("analysis_store", {})
        kline_data = state.get("kline_data", {})
        ensure_chart_dirs()
        
        # Process each window
        for window_key, spec in analyses_required.items():
            # Authoritative gate: run list was set by resolve_run_lists
            if "trend" not in spec.get("run", []):
                continue

            # Parse window key to get symbol/timeframe/horizon
            try:
                parsed = parse_window_key(window_key)
            except ValueError:
                spec["run"].remove("trend")
                continue

            symbol = parsed["symbol"]
            timeframe = parsed["timeframe"]
            horizon = parsed["horizon"]

            # store_key IS window_key in the new model
            store_key = window_key
            
            # Get current time
            current_time = get_current_time_iso()
            
            # Run trend analysis
            print(f"🔄 Running trend analysis for {symbol}|{timeframe}|{horizon}")
            
            # Get kline data for this window
            context_kline_data = kline_data.get(window_key, {})
            if not context_kline_data:
                print(f"⚠️ No kline data available for {window_key}")
                spec["run"].remove("trend")
                continue
            
            # Extract actual start/end from fetched kline data
            datetimes = context_kline_data.get("Datetime", [])
            start_datetime = datetimes[0] if datetimes else ""
            end_datetime = datetimes[-1] if datetimes else ""
            
            # Run trend analysis
            trend_result = _run_trend_analysis(
                tool_llm=tool_llm,
                graph_llm=graph_llm,
                toolkit=toolkit,
                kline_data=context_kline_data,
                timeframe=timeframe,
                horizon=horizon,
                symbol=symbol,
                start_datetime=start_datetime,
                end_datetime=end_datetime
            )
            
            # Calculate freshness (based on window duration)
            fresh_until = calculate_trend_freshness(
                current_time, 
                start_datetime, 
                end_datetime, 
                horizon
            )
            
            # Prepare metadata
            metadata = {
                "agent": "trend",
                "created_at": current_time,
                "ran_at": current_time,
                "fresh_until": fresh_until,
                "timeframe": timeframe,
                "horizon": horizon,
                "symbol": symbol,
                "chart_path": trend_result.get("chart_path")
            }
            
            # Store in analysis_store
            store_agent_output(
                analysis_store=analysis_store,
                store_key=store_key,
                agent_name="trend",
                data=trend_result,
                metadata=metadata
            )
            
            print(f"💾 Stored trend analysis (fresh until {fresh_until})")
            
            # Cascade: trend recomputed → force decision to rerun
            force_dependents_to_run(state, window_key, "trend")
            
            # Remove from run list
            spec["run"].remove("trend")

        return {"analysis_store": analysis_store}
    
    return trend_agent_node


def _run_trend_analysis(
    tool_llm,
    graph_llm,
    toolkit,
    kline_data: Dict[str, Any],
    timeframe: str,
    horizon: str,
    symbol: str,
    start_datetime: str,
    end_datetime: str
) -> Dict[str, Any]:
    """
    Execute trend analysis using LLM and tools.
    
    Returns:
        Dict with trend direction, support/resistance, chart path, and interpretation
    """
    # Generate trend chart
    chart_path = _generate_trend_chart(
        toolkit=toolkit,
        kline_data=kline_data,
        symbol=symbol,
        timeframe=timeframe,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        horizon=horizon
    )
    
    # Build prompt for trend analysis
    horizon_context = {
        "intraday": "short-term intraday movements (hours)",
        "swing": "swing trends over days to weeks",
        "long_term": "major trends over weeks to months"
    }
    
    system_msg = (
        f"You are a trend analysis expert for {horizon_context.get(horizon, 'trading')}. "
        f"Analyze the {timeframe} chart for trendlines, support/resistance levels, and trend direction. "
        f"Focus on {horizon} timeframe implications. "
        "Identify: 1) Current trend direction (up/down/sideways), "
        "2) Key support and resistance levels, "
        "3) Trendline strength and potential breakouts."
    )
    
    messages = [
        SystemMessage(content=system_msg),
        HumanMessage(content=f"Analyze trend for {symbol} on {timeframe} chart focusing on {horizon} trading.")
    ]
    
    # If we have the chart image, use vision model
    trend_image_b64 = None
    if chart_path and os.path.exists(chart_path):
        # Read chart as base64
        import base64
        with open(chart_path, "rb") as f:
            trend_image_b64 = base64.b64encode(f.read()).decode('utf-8')
    
    # Use vision-enabled LLM if we have image
    if trend_image_b64 and graph_llm:
        # Build vision message
        vision_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze this trend chart with trendlines and support/resistance:"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{trend_image_b64}"}
                }
            ]
        }
        
        try:
            response = graph_llm.invoke([
                {"role": "system", "content": system_msg},
                vision_message
            ])
            # Handle both string and list-based content formats
            if hasattr(response, 'content'):
                if isinstance(response.content, list):
                    # New format: [{'type': 'text', 'text': '...'}]
                    interpretation = "".join(
                        block.get('text', '') for block in response.content 
                        if isinstance(block, dict) and block.get('type') == 'text'
                    )
                else:
                    # Old format: simple string
                    interpretation = response.content
            else:
                interpretation = str(response)
        except Exception as e:
            print(f"⚠️ Vision analysis failed: {e}")
            interpretation = "Trend chart generated but vision analysis unavailable."
    else:
        # Fallback to text-only analysis
        interpretation = "Trend chart generated. Manual analysis required."
    
    # Extract structured data from interpretation
    trend_direction = _extract_trend_direction(interpretation)
    
    return {
        "chart_path": chart_path,
        "trend_direction": trend_direction,
        "interpretation": interpretation,
        "has_vision_analysis": trend_image_b64 is not None,
        "horizon": horizon
    }


def _generate_trend_chart(
    toolkit,
    kline_data: Dict[str, Any],
    symbol: str,
    timeframe: str,
    start_datetime: str,
    end_datetime: str,
    horizon: str
) -> str:
    """
    Generate trend chart with trendlines and save with standardized naming.
    
    Returns:
        Path to saved chart file
    """
    # Generate chart using toolkit
    try:
        result = toolkit.generate_trend_image.invoke({"kline_data": copy.deepcopy(kline_data)})
        image_b64 = result.get("trend_image")
        
        if not image_b64:
            print("⚠️ Trend chart generation failed")
            return None
        
        chart_path = make_chart_path(
            symbol=symbol,
            timeframe=timeframe,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            horizon=horizon,
            agent="trend",
        )
        
        # Save chart
        import base64
        with open(chart_path, "wb") as f:
            f.write(base64.b64decode(image_b64))
        
        print(f"📊 Saved trend chart: {chart_path}")
        return chart_path
        
    except Exception as e:
        print(f"⚠️ Chart generation error: {e}")
        return None


def _ensure_chart_directory():
    """Backward-compatible alias."""
    ensure_chart_dirs()


def _extract_trend_direction(text: str) -> str:
    """
    Extract trend direction from analysis text.
    
    Returns:
        "upward", "downward", or "sideways"
    """
    text_lower = text.lower()
    
    # Check for directional keywords
    upward_keywords = ["upward", "bullish", "uptrend", "rising", "climbing"]
    downward_keywords = ["downward", "bearish", "downtrend", "falling", "declining"]
    sideways_keywords = ["sideways", "ranging", "consolidat", "neutral", "flat"]
    
    upward_count = sum(1 for kw in upward_keywords if kw in text_lower)
    downward_count = sum(1 for kw in downward_keywords if kw in text_lower)
    sideways_count = sum(1 for kw in sideways_keywords if kw in text_lower)
    
    # Determine dominant direction
    max_count = max(upward_count, downward_count, sideways_count)
    
    if max_count == 0:
        return "unknown"
    elif upward_count == max_count:
        return "upward"
    elif downward_count == max_count:
        return "downward"
    else:
        return "sideways"
