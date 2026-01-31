"""
Pattern Agent with per-agent freshness tracking and chart management.

This agent:
1. Reads analyses_required dict from state
2. Checks freshness of cached pattern analysis before running
3. Generates pattern charts only if cache is stale or missing
4. Stores results with metadata and chart path
5. Tracks upstream_agents_reran for decision invalidation
"""

import copy
import json
import os
from typing import Dict, Any
from datetime import datetime

from langchain_core.messages import ToolMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from analysis_store_util import (
    calculate_pattern_freshness,
    is_agent_output_fresh,
    make_analysis_store_key,
    store_agent_output,
)
from freshness_config import get_current_time_iso, parse_iso_datetime
from chart_manager import make_chart_path, ensure_chart_dirs


def create_pattern_agent(tool_llm, graph_llm, toolkit):
    """
    Create pattern analysis agent with freshness tracking and chart management.
    """

    def pattern_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process all pattern analysis requests from analyses_required.
        """
        analyses_required = state.get("analyses_required", {})
        analysis_store = state.get("analysis_store", {})
        kline_data = state.get("kline_data", {})
        ensure_chart_dirs()
        
        # Process each data context
        for context_key, spec in analyses_required.items():
            # Check if pattern is required for this context
            if "pattern" not in spec.get("run", []):
                continue

            horizon = spec.get("horizon")
            if not horizon:
                spec["run"].remove("pattern")
                continue

            parts = context_key.split("|")
            if len(parts) != 3:
                spec["run"].remove("pattern")
                continue
            symbol = parts[0]
            timeframe = parts[1]
            datetime_range = parts[2]
            
            # Parse datetime range with timezone-aware regex
            import re
            match = re.match(r'^(.+?[+-]\d{2}:\d{2}):(.+)$', datetime_range)
            if not match:
                match = re.match(r'^(.+?Z):(.+)$', datetime_range)
            if not match:
                spec["run"].remove("pattern")
                continue
            start_datetime = match.group(1)
            end_datetime = match.group(2)

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
            if is_agent_output_fresh(analysis_store, store_key, "pattern", current_time):
                print(f"✅ Pattern analysis CACHED and FRESH for {symbol}|{timeframe}|{horizon}")
                # Remove from run list
                spec["run"].remove("pattern")
                continue
            
            # CACHE MISS or STALE - Run pattern analysis
            print(f"🔄 Running pattern analysis for {symbol}|{timeframe}|{horizon}")
            
            # Get kline data for this context
            context_kline_data = kline_data.get(context_key, {})
            if not context_kline_data:
                print(f"⚠️ No kline data available for {context_key}")
                spec["run"].remove("pattern")
                continue
            
            # Run pattern recognition
            pattern_result = _run_pattern_analysis(
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
            
            # Calculate freshness
            fresh_until = calculate_pattern_freshness(current_time, timeframe, horizon)
            
            # Prepare metadata
            metadata = {
                "agent": "pattern",
                "created_at": current_time,
                "ran_at": current_time,
                "fresh_until": fresh_until,
                "timeframe": timeframe,
                "horizon": horizon,
                "symbol": symbol,
                "chart_path": pattern_result.get("chart_path")
            }
            
            # Store in analysis_store
            store_agent_output(
                analysis_store=analysis_store,
                store_key=store_key,
                agent_name="pattern",
                data=pattern_result,
                metadata=metadata
            )
            
            print(f"💾 Stored pattern analysis (fresh until {fresh_until})")
            
            # Remove from run list
            spec["run"].remove("pattern")

        return {"analysis_store": analysis_store}
    
    return pattern_agent_node


def _run_pattern_analysis(
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
    Execute pattern recognition using LLM and tools.
    
    Returns:
        Dict with pattern findings, image path, and interpretation
    """
    # Generate pattern chart
    chart_path = _generate_pattern_chart(
        toolkit=toolkit,
        kline_data=kline_data,
        symbol=symbol,
        timeframe=timeframe,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        horizon=horizon
    )
    
    # Pattern descriptions
    pattern_descriptions = _get_pattern_descriptions()
    
    # Build prompt for pattern recognition
    system_msg = (
        f"You are a candlestick pattern recognition expert for {horizon} trading. "
        f"Analyze the {timeframe} chart for classical patterns. "
        "Refer to the following pattern types:\n\n"
        f"{pattern_descriptions}\n\n"
        "Identify any patterns present and their implications."
    )
    
    messages = [
        SystemMessage(content=system_msg),
        HumanMessage(content=f"Analyze this {symbol} chart for {horizon} patterns.")
    ]
    
    # If we have the chart image, use vision model
    pattern_image_b64 = None
    if chart_path and os.path.exists(chart_path):
        # Read chart as base64
        import base64
        with open(chart_path, "rb") as f:
            pattern_image_b64 = base64.b64encode(f.read()).decode('utf-8')
    
    # Use vision-enabled LLM if we have image
    if pattern_image_b64 and graph_llm:
        # Build vision message
        vision_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze this candlestick chart for patterns:"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{pattern_image_b64}"}
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
            interpretation = "Pattern chart generated but vision analysis unavailable."
    else:
        # Fallback to text-only analysis
        interpretation = "Pattern chart generated. Manual analysis required."
    
    return {
        "chart_path": chart_path,
        "patterns_found": _extract_patterns_from_text(interpretation),
        "interpretation": interpretation,
        "has_vision_analysis": pattern_image_b64 is not None
    }


def _generate_pattern_chart(
    toolkit,
    kline_data: Dict[str, Any],
    symbol: str,
    timeframe: str,
    start_datetime: str,
    end_datetime: str,
    horizon: str
) -> str:
    """
    Generate pattern chart and save with standardized naming.
    
    Returns:
        Path to saved chart file
    """
    # Generate chart using toolkit
    try:
        result = toolkit.generate_kline_image.invoke({"kline_data": copy.deepcopy(kline_data)})
        image_b64 = result.get("pattern_image")
        
        if not image_b64:
            print("⚠️ Pattern chart generation failed")
            return None
        
        chart_path = make_chart_path(
            symbol=symbol,
            timeframe=timeframe,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            horizon=horizon,
            agent="pattern",
        )
        
        # Save chart
        import base64
        with open(chart_path, "wb") as f:
            f.write(base64.b64decode(image_b64))
        
        print(f"📊 Saved pattern chart: {chart_path}")
        return chart_path
        
    except Exception as e:
        print(f"⚠️ Chart generation error: {e}")
        return None


def _ensure_chart_directory():
    """Backward-compatible alias."""
    ensure_chart_dirs()


def _get_pattern_descriptions() -> str:
    """Get classical candlestick pattern descriptions."""
    return """
1. Inverse Head and Shoulders: Three lows with the middle being lowest, symmetrical, indicates upward trend
2. Double Bottom: Two similar lows with rebound, 'W' shape
3. Rounded Bottom: Gradual decline then rise, 'U' shape
4. Hidden Base: Horizontal consolidation then upward breakout
5. Falling Wedge: Narrowing downward, usually breaks up
6. Rising Wedge: Rising but converging, often breaks down
7. Ascending Triangle: Rising support, flat resistance, breaks up
8. Descending Triangle: Falling resistance, flat support, breaks down
9. Bullish Flag: Sharp rise, brief consolidation, continues up
10. Bearish Flag: Sharp drop, brief consolidation, continues down
11. Rectangle: Horizontal support and resistance
12. Island Reversal: Two gaps forming isolated price island
13. V-shaped Reversal: Sharp decline/rise then reverse
14. Rounded Top/Bottom: Gradual peak/bottom, arc shape
15. Expanding Triangle: Widening swings, high volatility
16. Symmetrical Triangle: Converging highs/lows, breakout expected
    """


def _extract_patterns_from_text(text: str) -> list:
    """
    Extract pattern names mentioned in analysis text.
    
    Returns:
        List of pattern names found
    """
    pattern_keywords = [
        "head and shoulders", "double bottom", "double top",
        "rounded bottom", "rounded top", "wedge", "triangle",
        "flag", "rectangle", "island", "v-shaped"
    ]
    
    found = []
    text_lower = text.lower()
    
    for pattern in pattern_keywords:
        if pattern in text_lower:
            found.append(pattern.title())
    
    return found
