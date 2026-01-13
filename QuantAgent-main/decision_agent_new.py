"""
Decision Agent: Non-conversational, structured decision generator.

STRICT RULES:
- NEVER reads conversation_summary
- NEVER produces conversational text
- NEVER talks to user
- NEVER recomputes analysis
- Reads ONLY: analysis_store, data_contexts_required, intent
- Produces ONLY structured JSON decision
- Decision is immutable for the current turn
"""

import json
import re
from typing import Any, Dict, List

from analysis_store_util import (
    decision_is_stale,
    get_filtered_analysis_store,
    make_analysis_store_key,
    store_agent_output,
)
from freshness_config import get_current_time_iso


# ============================================================================
# DECISION AGENT PROMPT (NON-CONVERSATIONAL)
# ============================================================================

DECISION_AGENT_PROMPT = """You are a quantitative trading decision synthesizer. You produce STRUCTURED DECISIONS ONLY.

⚠️ CRITICAL CONSTRAINTS:
1. You are NOT conversational
2. You do NOT talk to users
3. You ONLY synthesize existing analysis into structured decisions
4. You NEVER recompute or re-analyze data
5. You output ONLY valid JSON

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUT DATA (READ-ONLY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ANALYSIS RESULTS (already computed):

{analysis_summary}

DATA CONTEXTS USED:
{contexts_used}

QUERY INTENT: {intent}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DECISION SYNTHESIS RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Your task is to synthesize the analysis above into ONE decision.

DECISION CRITERIA:
✓ BUY: All three analyses (indicator, pattern, trend) show strong bullish confluence
  - Momentum indicators confirm uptrend
  - Patterns show clear breakout
  - Trend support is strong
  - Confidence ≥ 70%

✓ SELL: All three analyses show strong bearish confluence
  - Momentum indicators confirm downtrend
  - Patterns show clear breakdown
  - Trend resistance is strong
  - Confidence ≥ 70%

✓ HOLD: Default when:
  - Signals conflict or are mixed
  - Indicators are neutral
  - Patterns incomplete or ambiguous
  - Confidence < 70%
  - Insufficient data

SAFETY RULES:
- Prefer HOLD when uncertain
- Never guarantee outcomes
- Acknowledge conflicts explicitly
- Weight recent signals higher

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT (STRICT JSON ONLY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{{
  "decision": "BUY | SELL | HOLD",
  "confidence": <float 0-100>,
  "decision_type": "strong_buy | weak_buy | neutral | weak_sell | strong_sell",
  "contexts_used": [
    "{{symbol}}|{{timeframe}}|{{start}}:{{end}}"
  ],
  "reasoning": {{
    "indicator": "<1-2 sentence summary of indicator signals>",
    "pattern": "<1-2 sentence summary of pattern signals>",
    "trend": "<1-2 sentence summary of trend signals>"
  }},
  "risk_notes": "<specific risks for this decision>"
}}

REMEMBER: Output ONLY the JSON. No explanations. No conversation. No markdown.
"""


# ============================================================================
# HELPER: Format analysis for decision synthesis
# ============================================================================

def format_analysis_for_decision(filtered_store: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Format analysis_store entries into structured summary for decision agent.
    
    Args:
        filtered_store: Dict of {key: analysis_entry}
        
    Returns:
        Dict with formatted analysis summary and metadata
    """
    analysis_parts = []
    contexts = []
    
    for key, entry in filtered_store.items():
        symbol = entry.get("symbol", "Unknown")
        timeframe = entry.get("timeframe", "Unknown")
        contexts.append(key)
        
        analysis_parts.append(f"\n{'='*60}")
        analysis_parts.append(f"CONTEXT: {key}")
        analysis_parts.append(f"Symbol: {symbol} | Timeframe: {timeframe}")
        analysis_parts.append(f"{'='*60}\n")
        
        # Indicator analysis
        if "indicator" in entry and entry["indicator"]:
            indicator_data = entry["indicator"]
            report = indicator_data.get("report", "Not available")
            analysis_parts.append("📊 INDICATOR ANALYSIS:")
            analysis_parts.append(report)
            analysis_parts.append("")
        
        # Pattern analysis
        if "pattern" in entry and entry["pattern"]:
            pattern_data = entry["pattern"]
            report = pattern_data.get("report", "Not available")
            analysis_parts.append("📈 PATTERN ANALYSIS:")
            analysis_parts.append(report)
            analysis_parts.append("")
        
        # Trend analysis
        if "trend" in entry and entry["trend"]:
            trend_data = entry["trend"]
            report = trend_data.get("report", "Not available")
            analysis_parts.append("📉 TREND ANALYSIS:")
            analysis_parts.append(report)
            analysis_parts.append("")
    
    return {
        "analysis_summary": "\n".join(analysis_parts) if analysis_parts else "No analysis available",
        "contexts_used": contexts
    }


# ============================================================================
# MAIN DECISION AGENT (NON-CONVERSATIONAL)
# ============================================================================

def generate_decision(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Generate structured trading decision from cached analysis.
    
    AUTO-TRIGGER LOGIC:
    - Automatically re-runs if any upstream agent (indicator, pattern, trend) changed
    - Checks decision validity based on upstream versions
    - Tracks upstream_agents_reran to detect changes
    
    FORBIDDEN:
    - Reading conversation_summary
    - Producing conversational text
    - Talking to user
    - Recomputing analysis
    - Fetching new data
    
    ALLOWED:
    - Reading analysis_store (filtered)
    - Reading analyses_required
    - Reading intent
    - Producing structured JSON decision
    
    Args:
        state: TradingAdvisorState with analysis_store
        llm: Language model for decision synthesis
        
    Returns:
        Updated state with decision output
    """
    
    intent = state.get("intent", "")
    analyses_required = state.get("analyses_required", {})
    analysis_store = state.get("analysis_store", {})

    last_decision_result = None

    # Process each DataContext.key (no horizon), convert to store_key with horizon
    for ctx_key, spec in analyses_required.items():
        horizon = spec.get("horizon")
        if not horizon:
            continue

        # ctx_key: "{symbol}|{timeframe}|{start}:{end}"
        parts = ctx_key.split("|")
        if len(parts) != 3:
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

        planner_requested = "decision" in spec.get("run", [])
        stale = decision_is_stale(store_key, analysis_store)
        if not planner_requested and not stale:
            continue

        # Guard: need upstream analyses present
        entry = analysis_store.get(store_key) or {}
        
        # Check if upstream analyses exist
        missing_upstream = [a for a in ["indicator", "pattern", "trend"] if not isinstance(entry.get(a), dict)]
        if missing_upstream:
            # Don't force decision before inputs exist
            if planner_requested and "decision" in spec.get("run", []):
                spec["run"].remove("decision")
            continue
        
        print(f"🔄 Running decision for {store_key} (stale={stale}, planner_requested={planner_requested})")

        formatted = _format_single_context_analysis(entry)
        
        # Build decision prompt
        prompt = DECISION_AGENT_PROMPT.format(
            analysis_summary=formatted["analysis_summary"],
            contexts_used=ctx_key,
            intent=intent
        )
        
        # Invoke LLM
        response = llm.invoke(prompt)
        response_text = response.content.strip()
        
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            try:
                decision_data = json.loads(json_match.group(0))
                
                # Validate decision format
                decision = decision_data.get("decision", "HOLD")
                if decision not in ["BUY", "SELL", "HOLD"]:
                    print(f"⚠️ Invalid decision '{decision}', defaulting to HOLD")
                    decision = "HOLD"
                
                # Get current time
                current_time = get_current_time_iso()
                
                # Prepare decision data
                decision_result = {
                    "decision": decision,
                    "confidence": decision_data.get("confidence", 0),
                    "decision_type": decision_data.get("decision_type", "neutral"),
                    "contexts_used": [ctx_key],
                    "reasoning": decision_data.get("reasoning", {}),
                    "risk_notes": decision_data.get("risk_notes", "")
                }
                
                metadata = {
                    "agent": "decision",
                    "created_at": current_time,
                    "ran_at": current_time,
                    "fresh_until": None,
                    "timeframe": timeframe,
                    "horizon": horizon,
                }
                
                # Store decision
                store_agent_output(
                    analysis_store=analysis_store,
                    store_key=store_key,
                    agent_name="decision",
                    data=decision_result,
                    metadata=metadata
                )

                last_decision_result = decision_result
                
                print(f"✓ Decision: {decision} (confidence: {decision_data.get('confidence', 0)}%)")
                # Remove from run list
                if "decision" in spec.get("run", []):
                    spec["run"].remove("decision")
                
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON parsing failed: {e}")
                if "decision" in spec.get("run", []):
                    spec["run"].remove("decision")
        else:
            print("⚠️ No valid JSON found in decision response")
            if "decision" in spec.get("run", []):
                spec["run"].remove("decision")
    
    result: Dict[str, Any] = {"analysis_store": analysis_store}
    if last_decision_result is not None:
        # Convenience fields for UI and dialogue_agent
        result["decision"] = last_decision_result
    return result


def _format_single_context_analysis(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a single analysis store entry for decision synthesis.
    
    Args:
        entry: Analysis store entry with indicator, pattern, trend
        
    Returns:
        Dict with formatted analysis summary
    """
    analysis_parts = []
    
    # Indicator analysis
    if "indicator" in entry and entry["indicator"]:
        indicator_output = entry["indicator"]
        if "data" in indicator_output:
            indicator_data = indicator_output["data"]
            interpretation = indicator_data.get("interpretation", "Not available")
            analysis_parts.append("📊 INDICATOR ANALYSIS:")
            analysis_parts.append(interpretation)
            analysis_parts.append("")
    
    # Pattern analysis
    if "pattern" in entry and entry["pattern"]:
        pattern_output = entry["pattern"]
        if "data" in pattern_output:
            pattern_data = pattern_output["data"]
            interpretation = pattern_data.get("interpretation", "Not available")
            analysis_parts.append("📈 PATTERN ANALYSIS:")
            analysis_parts.append(interpretation)
            analysis_parts.append("")
    
    # Trend analysis
    if "trend" in entry and entry["trend"]:
        trend_output = entry["trend"]
        if "data" in trend_output:
            trend_data = trend_output["data"]
            interpretation = trend_data.get("interpretation", "Not available")
            analysis_parts.append("📉 TREND ANALYSIS:")
            analysis_parts.append(interpretation)
            analysis_parts.append("")
    
    return {
        "analysis_summary": "\n".join(analysis_parts) if analysis_parts else "No analysis available"
    }


# ============================================================================
# NODE FACTORY
# ============================================================================

def create_decision_agent(llm):
    """
    Create decision agent node (non-conversational).
    
    This agent:
    - Runs ONLY when intent in ["trade", "trend", "compare"]
    - Reads ONLY analysis_store (filtered) and intent
    - NEVER reads conversation_summary
    - Produces ONLY structured JSON decision
    - Writes decision to analysis_store
    
    Args:
        llm: Language model for decision synthesis
        
    Returns:
        Decision agent node function
    """
    
    def decision_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decision agent node - generates structured decision.
        """
        
        intent = state.get("intent", "")
        
        print(f"\n{'='*60}")
        print(f"DECISION AGENT (Non-Conversational)")
        print(f"{'='*60}")
        print(f"Intent: {intent}")
        
        result = generate_decision(state, llm)

        # result['decision'] is structured dict when available
        decision = result.get("decision")
        if isinstance(decision, dict):
            print(f"Decision: {decision.get('decision', 'N/A')}")
        else:
            print(f"Decision: {decision or 'N/A'}")
        print(f"{'='*60}\n")
        
        return result
    
    return decision_agent_node
