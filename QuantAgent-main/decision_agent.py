"""
Decision Agent: Final answer generation for conversational trading advisor.

DUAL MODE OPERATION:
1. DECISION MODE - Trade recommendations (BUY/SELL/HOLD)
   - Inputs: user_query, intent, mode, conversation_summary, user_preferences, 
     FILTERED analysis_store entries relevant to current query
   - Outputs: decision (BUY/SELL/HOLD), explanation
   - Triggered when: intent in ["advice", "trade", "compare", "trend_decision"]

2. EXPLANATION MODE - Conversational queries using cached analysis
   - Inputs: Same as decision mode, but NO new analysis triggered
   - Uses: cached decisions and analysis from analysis_store
   - Triggered when: intent in ["explain", "chat", "why", "price_check"]

CRITICAL: This agent NEVER re-analyzes or recomputes indicators.
It ONLY synthesizes existing results from analysis_store or explains past decisions.
"""

import json
import re
from typing import Any, Dict, List
from analysis_store_util import get_filtered_analysis_store


# ============================================================================
# Helper: Format analysis for LLM
# ============================================================================

def format_analysis_for_llm(filtered_store: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    """
    Format filtered analysis_store entries into readable text for LLM.
    
    Args:
        filtered_store: Dict of {key: analysis_entry}
        
    Returns:
        Dict with formatted strings: {
            "indicator_text": combined indicator reports,
            "pattern_text": combined pattern reports,
            "trend_text": combined trend reports,
            "symbols_analyzed": list of symbols
        }
    """
    indicator_parts = []
    pattern_parts = []
    trend_parts = []
    symbols = set()
    
    for key, entry in filtered_store.items():
        symbol = entry.get("symbol", "Unknown")
        timeframe = entry.get("timeframe", "Unknown")
        symbols.add(symbol)
        
        # Format indicator
        if "indicator" in entry and entry["indicator"]:
            indicator_data = entry["indicator"]
            report = indicator_data.get("report", "")
            if report:
                indicator_parts.append(f"**{symbol} ({timeframe}):**\n{report}\n")
        
        # Format pattern
        if "pattern" in entry and entry["pattern"]:
            pattern_data = entry["pattern"]
            report = pattern_data.get("report", "")
            if report:
                pattern_parts.append(f"**{symbol} ({timeframe}):**\n{report}\n")
        
        # Format trend
        if "trend" in entry and entry["trend"]:
            trend_data = entry["trend"]
            report = trend_data.get("report", "")
            if report:
                trend_parts.append(f"**{symbol} ({timeframe}):**\n{report}\n")
    
    return {
        "indicator_text": "\n".join(indicator_parts) if indicator_parts else "No indicator analysis available",
        "pattern_text": "\n".join(pattern_parts) if pattern_parts else "No pattern analysis available",
        "trend_text": "\n".join(trend_parts) if trend_parts else "No trend analysis available",
        "symbols_analyzed": list(symbols)
    }


# ============================================================================
# DECISION MODE: Trade Recommendations
# ============================================================================

def generate_trade_decision(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    DECISION MODE: Generate BUY/SELL/HOLD recommendation.
    
    Inputs:
    - user_query: Current user question
    - intent: Query intent (advice, trade, compare, etc.)
    - mode: Execution mode
    - conversation_summary: Historical conversation context
    - user_preferences: User's trading preferences
    - analysis_store: FILTERED entries relevant to current query
    
    This mode synthesizes cached analysis from analysis_store into a trading decision.
    
    SAFETY RULES:
    - Prefer HOLD when signals conflict
    - Never guarantee profits
    - Always acknowledge uncertainty
    - Provide risk warnings
    
    Args:
        state: Trading advisor state with filtered analysis_store
        llm: Language model for decision synthesis
        
    Returns:
        Updated state with decision and explanation
    """
    
    # Extract inputs for decision mode
    user_query = state.get("user_query", "")
    intent = state.get("intent", "")
    mode = state.get("mode", "")
    conversation_summary = state.get("conversation_summary", "")
    user_preferences = state.get("user_preferences", {})
    
    # Get filtered analysis_store (only relevant to current query)
    filtered_store = get_filtered_analysis_store(state)
    
    # Format analysis for LLM
    formatted = format_analysis_for_llm(filtered_store)
    indicator_report = formatted["indicator_text"]
    pattern_report = formatted["pattern_text"]
    trend_report = formatted["trend_text"]
    symbols_analyzed = formatted["symbols_analyzed"]
    
    # Extract context
    time_frame = state.get("timeframe", "unknown")
    symbols = state.get("symbols", symbols_analyzed)
    stock_name = symbols[0] if symbols else "unknown"
    
    # Build decision prompt
    prompt = f"""You are a conservative financial advisor providing trading analysis.

⚠️ CRITICAL SAFETY RULES:
1. Prefer NO TRADE when signals are mixed or weak
2. NEVER use phrases like "guaranteed", "sure shot", "100% confidence"
3. ALWAYS acknowledge market uncertainty
4. ALWAYS include risk warnings
5. Be honest about conflicting signals

CONTEXT:
- Asset: {stock_name}
- Timeframe: {time_frame}
- Analysis Date: Current market conditions

AVAILABLE ANALYSIS (already computed):

📊 TECHNICAL INDICATORS:
{indicator_report}

📈 PATTERN ANALYSIS:
{pattern_report}

📉 TREND ANALYSIS:
{trend_report}

USER CONTEXT:
- User Query: {user_query}
- Intent: {intent}
- Conversation History: {conversation_summary[:200] if conversation_summary else 'New conversation'}
- User Preferences: {user_preferences}

YOUR TASK:
Synthesize the above analysis into ONE of these decisions:
- BUY (if strong bullish confluence)
- SELL (if strong bearish confluence)
- HOLD (if signals conflict, are weak, or insufficient)

DECISION CRITERIA:
✓ All three analyses should align in the same direction
✓ Momentum indicators should confirm the trend
✓ Patterns should show clear breakout/breakdown
✓ Prefer HOLD if:
  - RSI shows overbought but trend is up (conflict)
  - Pattern is incomplete or ambiguous
  - Indicators are neutral or mixed
  - Confidence is below 60%

OUTPUT FORMAT (valid JSON only):
{{
  "decision": "BUY | SELL | HOLD",
  "confidence": "XX% (realistic estimate)",
  "reasoning": [
    "Bullet point 1 - specific signal",
    "Bullet point 2 - confirmation"
  ],
  "risk_warning": "Specific risks for this trade (mandatory)",
  "timeframe_note": "Expected holding period based on {time_frame} timeframe"
}}

⚠️ Remember: HOLD is a valid and often the safest decision. Don't force trades.
"""

    # Invoke LLM
    response = llm.invoke(prompt)
    response_text = response.content.strip()
    
    # Extract JSON from response
    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if json_match:
        try:
            decision_data = json.loads(json_match.group(0))
            explanation_parts = [
                f"**Decision: {decision_data.get('decision', 'HOLD')}**",
                f"**Confidence: {decision_data.get('confidence', 'N/A')}**",
                "",
                "**Reasoning:**"
            ]
            for reason in decision_data.get('reasoning', []):
                explanation_parts.append(f"• {reason}")
            explanation_parts.extend([
                "",
                f"⚠️ **Risk Warning:** {decision_data.get('risk_warning', 'Markets are unpredictable')}",
                f"⏰ **Timeframe:** {decision_data.get('timeframe_note', time_frame)}"
            ])
            explanation = "\n".join(explanation_parts)
            
            # Store decision back to analysis_store for caching
            from analysis_store_util import update_analysis_field
            analysis_store = state.get("analysis_store", {})
            for key in filtered_store.keys():
                decision_entry = {
                    "decision": decision_data.get('decision', 'HOLD'),
                    "confidence": decision_data.get('confidence', 'N/A'),
                    "reasoning": decision_data.get('reasoning', []),
                    "risk_warning": decision_data.get('risk_warning', ''),
                    "timeframe_note": decision_data.get('timeframe_note', '')
                }
                update_analysis_field(analysis_store, key, "decision", decision_entry)
            
            return {
                **state,
                "decision": decision_data.get('decision', 'HOLD'),
                "explanation": explanation,
                "final_trade_decision": response_text,
            }
            
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            return {
                **state,
                "decision": "HOLD",
                "explanation": f"Analysis synthesis:\n\n{response_text}\n\n⚠️ Unable to generate structured decision. Please review the analysis above.",
                "final_trade_decision": response_text,
            }
    
    # Fallback
    return {
        **state,
        "decision": "HOLD",
        "explanation": response_text,
        "final_trade_decision": response_text,
    }


# ============================================================================
# EXPLANATION/QA MODE: Answer questions using cached data
# ============================================================================

def generate_explanation(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    EXPLANATION MODE: Answer user questions using ONLY cached analysis.
    
    Inputs:
    - user_query: Current user question
    - intent: Query intent (explain, chat, why, etc.)
    - mode: Execution mode
    - conversation_summary: Historical conversation context
    - user_preferences: User's trading preferences
    - analysis_store: Uses cached decisions and analysis (NO new analysis)
    
    This mode is triggered when intent in ["explain", "chat", "why", "price_check"].
    It NEVER re-analyzes or recomputes anything.
    
    FORBIDDEN ACTIONS:
    - Fetching new market data
    - Calling indicator/pattern/trend agents
    - Recomputing analysis
    - Modifying market context
    
    ALLOWED ACTIONS:
    - Explain existing decision from analysis_store
    - Clarify reasoning from cached reports
    - Answer "why" questions
    - Provide conversational responses
    
    Args:
        state: Contains cached analysis_store and user query
        llm: Language model for explanation generation
        
    Returns:
        Updated state with explanation
    """
    
    # Extract inputs for explanation mode
    user_query = state.get("user_query", "")
    intent = state.get("intent", "")
    conversation_summary = state.get("conversation_summary", "")
    user_preferences = state.get("user_preferences", {})
    
    # Get filtered analysis_store (may include previous decisions)
    filtered_store = get_filtered_analysis_store(state)
    
    # If no filtered store, check entire store for explanation mode
    if not filtered_store:
        filtered_store = state.get("analysis_store", {})
    
    # Format analysis for LLM
    formatted = format_analysis_for_llm(filtered_store)
    indicator_report = formatted["indicator_text"]
    pattern_report = formatted["pattern_text"]
    trend_report = formatted["trend_text"]
    symbols_analyzed = formatted["symbols_analyzed"]
    
    # Extract cached decision if available
    decision = "No decision made yet"
    decision_details = {}
    for key, entry in filtered_store.items():
        if "decision" in entry and entry["decision"]:
            decision_data = entry["decision"]
            decision = decision_data.get("decision", "No decision")
            decision_details = decision_data
            break
    
    kline_data_map = state.get("kline_data_map", {})
    symbols = state.get("symbols", symbols_analyzed)
    
    # ====================================================================
    # SPECIAL CASE: historical/price_check with no data
    # ====================================================================
    if intent in ["historical", "price_check"] and not kline_data_map:
        # Get requested date info from state
        start_date = state.get("start_date", "")
        end_date = state.get("end_date", "")
        symbol = symbols[0] if symbols else "the requested symbol"
        
        error_msg = f"❌ Unable to fetch data for **{symbol}**"
        
        if start_date:
            error_msg += f" on {start_date}"
        
        error_msg += "\n\n**Possible reasons:**\n"
        error_msg += f"• The date might be a non-trading day (weekend/holiday)\n"
        error_msg += f"• The symbol might be incorrect or not available on Yahoo Finance\n"
        error_msg += f"• Data might not be available for that specific date\n\n"
        error_msg += f"**Suggestions:**\n"
        error_msg += f"• Try a different date or date range\n"
        error_msg += f"• Verify the symbol is correct (e.g., {symbol})\n"
        error_msg += f"• For Indian stocks, ensure you're using the correct suffix (e.g., RELIANCE.NS for NSE, RELIANCE.BO for BSE)"
        
        return {
            **state,
            "explanation": error_msg,
        }
    
    # ====================================================================
    # SPECIAL CASE: historical/price_check with data - extract price info
    # ====================================================================
    if intent in ["historical", "price_check"] and kline_data_map:
        print(f"🔍 Price check detected - symbols: {symbols}, kline_data_map keys: {list(kline_data_map.keys())}")
        symbol = symbols[0] if symbols else "Unknown"
        
        if symbol in kline_data_map:
            data = kline_data_map[symbol]
            dates = data.get("Datetime", [])
            closes = data.get("Close", [])
            opens = data.get("Open", [])
            highs = data.get("High", [])
            lows = data.get("Low", [])
            volumes = data.get("Volume", [])
            
            print(f"✓ Found data for {symbol}: {len(dates)} data points")
            
            if dates and closes:
                # Build price information response
                price_info = f"📊 **Price Data for {symbol}**\n\n"
                
                # Show latest data point (most recent price)
                if intent == "price_check":
                    # For current price, show only the last few rows
                    recent_count = min(3, len(dates))
                    start_idx = len(dates) - recent_count
                    price_info += f"**Recent Price Data (Latest {recent_count} data points):**\n\n"
                    
                    for i in range(start_idx, len(dates)):
                        date_str = dates[i]
                        price_info += f"**{date_str}**\n"
                        price_info += f"• Open: ₹{opens[i]:.2f}\n"
                        price_info += f"• High: ₹{highs[i]:.2f}\n"
                        price_info += f"• Low: ₹{lows[i]:.2f}\n"
                        price_info += f"• Close: ₹{closes[i]:.2f}\n"
                        price_info += f"• Volume: {volumes[i]:,.0f}\n\n"
                    
                    # Show current price prominently
                    current_price = closes[-1]
                    price_info = f"💰 **Current Price of {symbol}: ₹{current_price:.2f}**\n\n" + price_info
                else:
                    # For historical, show all data points
                    for i in range(len(dates)):
                        date_str = dates[i]
                        price_info += f"**{date_str}**\n"
                        price_info += f"• Open: ₹{opens[i]:.2f}\n"
                        price_info += f"• High: ₹{highs[i]:.2f}\n"
                        price_info += f"• Low: ₹{lows[i]:.2f}\n"
                        price_info += f"• Close: ₹{closes[i]:.2f}\n"
                        price_info += f"• Volume: {volumes[i]:,.0f}\n\n"
                
                # Add change calculation if multiple data points
                if len(closes) > 1:
                    change = closes[-1] - closes[0]
                    change_pct = (change / closes[0]) * 100
                    price_info += f"**Period Change:** ₹{change:+.2f} ({change_pct:+.2f}%)\n"
                
                print(f"✓ Returning price info ({len(price_info)} chars)")
                return {
                    **state,
                    "explanation": price_info,
                }
        else:
            print(f"⚠️ Symbol {symbol} not found in kline_data_map")
    
    # Check if we have any cached analysis in filtered_store
    has_analysis = bool(filtered_store) and any(
        "indicator" in entry or "pattern" in entry or "trend" in entry or "decision" in entry
        for entry in filtered_store.values()
    )
    
    if not has_analysis and intent == "explain":
        return {
            **state,
            "explanation": "I don't have any previous analysis to explain. Would you like me to analyze a specific stock first?",
        }
    
    # Build explanation prompt for conversational follow-ups
    prompt = f"""You are a financial advisor having a CONVERSATION with a client about a stock analysis.

⚠️ CRITICAL RULES:
1. Use ONLY the information from the previous analysis below
2. DO NOT make up new analysis or fetch new data
3. DO NOT recompute indicators
4. Be conversational and engage with the user's question
5. If user disagrees or challenges your view, defend it using the analysis data
6. If user asks "why?", explain the reasoning behind the decision

PREVIOUS ANALYSIS (Your Reference):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Decision Made:** {decision}

**Decision Details:**
{json.dumps(decision_details, indent=2) if decision_details else 'No detailed decision available'}

**Technical Indicators:**
{indicator_report}

**Pattern Analysis:**
{pattern_report}

**Trend Analysis:**
{trend_report}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONVERSATION CONTEXT:
{conversation_summary[:300] if conversation_summary else 'New conversation'}

USER PREFERENCES:
{user_preferences}

USER'S FOLLOW-UP QUESTION:
{user_query}

YOUR TASK:
Answer the user's question by discussing the analysis above. Be conversational.

Examples:
- "Why?" → Explain the key reasons from the reports
- "What about RSI?" → Quote the RSI value and explain what it means
- "I think it will go up" → Acknowledge their view, then explain what the analysis shows
- "What patterns did you see?" → List the patterns from pattern_report
- "Should I still buy?" → Refer back to the decision and supporting evidence

Be friendly, specific, and back everything with data from the analysis above.
If the answer isn't in the provided data, say "I don't have that information in my analysis."

Be conversational but factual. Don't speculate beyond what's in the reports.
"""

    # Invoke LLM
    response = llm.invoke(prompt)
    explanation = response.content.strip()
    
    return {
        **state,
        "explanation": explanation,
    }


# ============================================================================
# MAIN DECISION AGENT - Dual Mode Router
# ============================================================================

def create_final_trade_decider(llm):
    """
    Create a decision agent node with dual-mode operation.
    
    MODE SELECTION based on state["intent"]:
    - DECISION MODE: intent in ["advice", "trade", "compare", "trend_decision"]
    - EXPLANATION MODE: intent in ["explain", "chat", "why", "price_check", "historical"]
    
    This agent is the FINAL step in the pipeline.
    It NEVER triggers re-analysis or loops.
    It is idempotent for follow-up questions.
    
    Args:
        llm: Language model for decision/explanation generation
        
    Returns:
        A function that processes state and returns final answer
    """
    
    def decision_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decision agent router - delegates to appropriate mode based on intent.
        """
        
        intent = state.get("intent", "")
        
        print(f"\n{'='*60}")
        print(f"DECISION AGENT")
        print(f"{'='*60}")
        print(f"Intent: {intent}")
        
        # ====================================================================
        # MODE 1: DECISION MODE
        # Generate trade recommendation (BUY/SELL/HOLD)
        # ====================================================================
        
        if intent in ["advice", "trade", "compare", "trend_decision"]:
            print(f"Mode: DECISION (generating trade recommendation)")
            print(f"Using cached analysis to synthesize decision...")
            
            result = generate_trade_decision(state, llm)
            
            print(f"Decision: {result.get('decision', 'N/A')}")
            print(f"{'='*60}\n")
            
            return result
        
        # ====================================================================
        # MODE 2: EXPLANATION/QA MODE
        # Answer questions using cached data (NO re-analysis)
        # ====================================================================
        
        elif intent in ["explain", "chat", "why", "price_check", "historical"]:
            print(f"Mode: EXPLANATION/QA (using cached analysis)")
            print(f"Answering user question without re-analysis...")
            
            result = generate_explanation(state, llm)
            
            print(f"Explanation generated: {len(result.get('explanation', ''))} chars")
            print(f"{'='*60}\n")
            
            return result
        
        # ====================================================================
        # MODE 3: CLARIFICATION (no analysis needed)
        # Return clarification question directly
        # ====================================================================
        
        elif intent == "clarify":
            print(f"Mode: CLARIFICATION (returning question)")
            print(f"{'='*60}\n")
            
            # Explanation should already be set by planner/validator
            return state
        
        # ====================================================================
        # DEFAULT: Unknown intent
        # ====================================================================
        
        else:
            print(f"Mode: UNKNOWN INTENT ('{intent}')")
            print(f"{'='*60}\n")
            
            return {
                **state,
                "explanation": "I'm not sure how to help with that. Could you rephrase your question?",
            }
    
    return decision_agent_node


# ============================================================================
# LEGACY FUNCTION (for backward compatibility)
# ============================================================================

def create_final_trade_decider_legacy(llm):
    """
    Legacy decision agent - kept for backward compatibility.
    Always generates LONG/SHORT decisions (no NO TRADE option).
    Used by the old linear pipeline.
    """

    def trade_decision_node(state) -> dict:
        indicator_report = state["indicator_report"]
        pattern_report = state["pattern_report"]
        trend_report = state["trend_report"]
        time_frame = state["time_frame"]
        stock_name = state["stock_name"]

        # --- System prompt for LLM ---
        prompt = f"""You are a high-frequency quantitative trading (HFT) analyst operating on the current {time_frame} K-line chart for {stock_name}. Your task is to issue an **immediate execution order**: **LONG** or **SHORT**. ⚠️ HOLD is prohibited due to HFT constraints.

            Your decision should forecast the market move over the **next N candlesticks**, where:
            - For example: TIME_FRAME = 15min, N = 1 → Predict the next 15 minutes.
            - TIME_FRAME = 4hour, N = 1 → Predict the next 4 hours.

            Base your decision on the combined strength, alignment, and timing of the following three reports:

            ---

            ### 1. Technical Indicator Report:
            - Evaluate momentum (e.g., MACD, ROC) and oscillators (e.g., RSI, Stochastic, Williams %R).
            - Give **higher weight to strong directional signals** such as MACD crossovers, RSI divergence, extreme overbought/oversold levels.
            - **Ignore or down-weight neutral or mixed signals** unless they align across multiple indicators.

            ---

            ### 2. Pattern Report:
            - Only act on bullish or bearish patterns if:
            - The pattern is **clearly recognizable and mostly complete**, and
            - A **breakout or breakdown is already underway** or highly probable based on price and momentum (e.g., strong wick, volume spike, engulfing candle).
            - **Do NOT act** on early-stage or speculative patterns. Do not treat consolidating setups as tradable unless there is **breakout confirmation** from other reports.

            ---

            ### 3. Trend Report:
            - Analyze how price interacts with support and resistance:
            - An **upward sloping support line** suggests buying interest.
            - A **downward sloping resistance line** suggests selling pressure.
            - If price is compressing between trendlines:
            - Predict breakout **only when confluence exists with strong candles or indicator confirmation**.
            - **Do NOT assume breakout direction** from geometry alone.

            ---

            ### ✅ Decision Strategy

            1. Only act on **confirmed** signals — avoid emerging, speculative, or conflicting signals.
            2. Prioritize decisions where **all three reports** (Indicator, Pattern, and Trend) **align in the same direction**.
            3. Give more weight to:
            - Recent strong momentum (e.g., MACD crossover, RSI breakout)
            - Decisive price action (e.g., breakout candle, rejection wicks, support bounce)
            4. If reports disagree:
            - Choose the direction with **stronger and more recent confirmation**
            - Prefer **momentum-backed signals** over weak oscillator hints.
            5. ⚖️ If the market is in consolidation or reports are mixed:
            - Default to the **dominant trendline slope** (e.g., SHORT in descending channel).
            - Do not guess direction — choose the **more defensible** side.
            6. Suggest a reasonable **risk-reward ratio** between **1.2 and 1.8**, based on current volatility and trend strength.

            ---
            ### 🧠 Output Format in json(for system parsing):

            ```
            {{
            "forecast_horizon": "Predicting next 3 candlestick (15 minutes, 1 hour, etc.)",
            "decision": "<LONG or SHORT>",
            "justification": "<Concise, confirmed reasoning based on reports>",
            "risk_reward_ratio": "<float between 1.2 and 1.8>",
            }}

            --------
            **Technical Indicator Report**  
            {indicator_report}

            **Pattern Report**  
            {pattern_report}

            **Trend Report**  
            {trend_report}

        """

        # --- LLM call for decision ---
        response = llm.invoke(prompt)

        return {
            "final_trade_decision": response.content,
            "messages": [response],
            "decision_prompt": prompt,
        }

    return trade_decision_node


# ============================================================================
# LEGACY FUNCTION (for backward compatibility)
# ============================================================================

def create_final_trade_decider_legacy(llm):
    """
    Legacy decision agent - kept for backward compatibility.
    Always generates LONG/SHORT decisions (no NO TRADE option).
    Used by the old linear pipeline.
    """
    
    def trade_decision_node(state) -> dict:
        indicator_report = state.get("indicator_report", "")
        pattern_report = state.get("pattern_report", "")
        trend_report = state.get("trend_report", "")
        time_frame = state.get("time_frame", "unknown")
        stock_name = state.get("stock_name", "unknown")

        # --- System prompt for LLM ---
        prompt = f"""You are a high-frequency quantitative trading (HFT) analyst operating on the current {time_frame} K-line chart for {stock_name}. Your task is to issue an **immediate execution order**: **LONG** or **SHORT**. ⚠️ HOLD is prohibited due to HFT constraints.

Your decision should forecast the market move over the **next N candlesticks**, where:
- For example: TIME_FRAME = 15min, N = 1 - Predict the next 15 minutes.
- TIME_FRAME = 4hour, N = 1 - Predict the next 4 hours.

Base your decision on the combined strength, alignment, and timing of the following three reports:

---

### 1. Technical Indicator Report:
- Evaluate momentum (e.g., MACD, ROC) and oscillators (e.g., RSI, Stochastic, Williams %R).
- Give **higher weight to strong directional signals** such as MACD crossovers, RSI divergence, extreme overbought/oversold levels.
- **Ignore or down-weight neutral or mixed signals** unless they align across multiple indicators.

---

### 2. Pattern Report:
- Only act on bullish or bearish patterns if:
- The pattern is **clearly recognizable and mostly complete**, and
- A **breakout or breakdown is already underway** or highly probable based on price and momentum (e.g., strong wick, volume spike, engulfing candle).
- **Do NOT act** on early-stage or speculative patterns. Do not treat consolidating setups as tradable unless there is **breakout confirmation** from other reports.

---

### 3. Trend Report:
- Analyze how price interacts with support and resistance:
- An **upward sloping support line** suggests buying interest.
- A **downward sloping resistance line** suggests selling pressure.
- If price is compressing between trendlines:
- Predict breakout **only when confluence exists with strong candles or indicator confirmation**.
- **Do NOT assume breakout direction** from geometry alone.

---

### ✅ Decision Strategy

1. Only act on **confirmed** signals — avoid emerging, speculative, or conflicting signals.
2. Prioritize decisions where **all three reports** (Indicator, Pattern, and Trend) **align in the same direction**.
3. Give more weight to:
- Recent strong momentum (e.g., MACD crossover, RSI breakout)
- Decisive price action (e.g., breakout candle, rejection wicks, support bounce)
4. If reports disagree:
- Choose the direction with **stronger and more recent confirmation**
- Prefer **momentum-backed signals** over weak oscillator hints.
5. ⚖️ If the market is in consolidation or reports are mixed:
- Default to the **dominant trendline slope** (e.g., SHORT in descending channel).
- Do not guess direction — choose the **more defensible** side.
6. Suggest a reasonable **risk-reward ratio** between **1.2 and 1.8**, based on current volatility and trend strength.

---
### 🧠 Output Format in json(for system parsing):

{{
"forecast_horizon": "Predicting next 3 candlestick (15 minutes, 1 hour, etc.)",
"decision": "<LONG or SHORT>",
"justification": "<Concise, confirmed reasoning based on reports>",
"risk_reward_ratio": "<float between 1.2 and 1.8>",
}}

--------
**Technical Indicator Report**  
{indicator_report}

**Pattern Report**  
{pattern_report}

**Trend Report**  
{trend_report}

"""

        # --- LLM call for decision ---
        response = llm.invoke(prompt)

        return {
            "final_trade_decision": response.content,
            "messages": [response],
            "decision_prompt": prompt,
        }

    return trade_decision_node
