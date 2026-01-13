"""
Dialogue Agent: User-facing conversational agent for explanations and clarifications.

STRICT RULES:
- NEVER changes decisions
- NEVER runs analysis
- NEVER triggers data fetch
- Reads: decision output, analysis_store (read-only), conversation_summary, user_query
- Produces: Natural language explanation only
- Updates: conversation_summary after responding
"""

import json
from typing import Any, Dict
from analysis_store_util import get_filtered_analysis_store


# ============================================================================
# DIALOGUE AGENT PROMPT (CONVERSATIONAL)
# ============================================================================

DIALOGUE_AGENT_PROMPT = """You are a friendly financial advisor having a CONVERSATION with a client.

⚠️ CRITICAL RULES:
1. You are conversational and user-facing
2. You EXPLAIN decisions and analysis - you DON'T change them
3. You NEVER run new analysis or fetch data
4. You use ONLY the information provided below
5. If asked "why?", explain reasoning from the analysis
6. If user disagrees, defend using analysis data (but respectfully)
7. Be specific, cite numbers, acknowledge uncertainty

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AVAILABLE INFORMATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CURRENT DECISION:
{decision_summary}

ANALYSIS DETAILS:
{analysis_details}

CONVERSATION HISTORY:
{conversation_summary}

USER QUERY:
{user_query}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR TASK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Respond to the user's query by:
1. Explaining the decision and its reasoning
2. Answering specific questions using analysis data
3. Clarifying any confusion
4. Engaging with user's concerns or disagreements
5. Being conversational but factual

EXAMPLES:

User: "Why did you recommend BUY?"
You: "I recommended BUY because all three analyses aligned bullishly. The RSI at 45 shows healthy momentum without being overbought, the MACD just crossed bullish, and we identified a cup-and-handle pattern that recently broke out. The trend shows strong support at $95."

User: "What about RSI?"
You: "The RSI is currently at 45, which is in neutral territory. This suggests the stock isn't overbought yet and has room to move higher before hitting resistance levels."

User: "I think it will go down"
You: "I understand your concern. However, the technical analysis shows three bullish signals: (1) MACD bullish crossover, (2) breakout from cup-and-handle pattern, (3) price above rising support line. While markets are unpredictable, these signals historically suggest upward momentum."

User: "Should I still buy?"
You: "Based on the technical analysis, the BUY signal remains valid. However, always consider your risk tolerance and portfolio allocation. The analysis shows 75% confidence, meaning there's still 25% uncertainty. Never invest more than you can afford to lose."

TONE:
- Conversational and friendly
- Factual and data-driven
- Honest about limitations
- Patient with follow-ups

Do NOT speculate beyond the provided analysis.
Do NOT make up new analysis or data.
If information isn't available, say "I don't have that information in my current analysis."
"""


# ============================================================================
# SPECIAL CASE: Price Check / Historical Query
# ============================================================================

PRICE_CHECK_PROMPT = """You are a financial data assistant providing price information.

USER QUERY:
{user_query}

AVAILABLE DATA:
{price_data}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR TASK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Present the price data in a clear, readable format.

For current price checks:
- Show the latest price prominently
- Include recent data points (last 2-3)
- Show change from previous close

For historical queries:
- Show all requested data points
- Calculate period change
- Present in chronological order

Format example:
💰 **Current Price of AAPL: $175.43**

**Recent Price Data:**

**2024-01-08**
• Open: $174.50
• High: $176.20
• Low: $174.10
• Close: $175.43
• Volume: 52,847,300

**Period Change:** +$2.43 (+1.40%)

Be concise and data-focused. No analysis unless explicitly asked.
"""


# ============================================================================
# HELPER: Format decision and analysis for dialogue
# ============================================================================

def format_for_dialogue(state: Dict[str, Any]) -> Dict[str, str]:
    """
    Format decision and analysis for dialogue agent.
    
    Args:
        state: TradingAdvisorState with decision and analysis_store
        
    Returns:
        Dict with formatted strings for prompt
    """
    # Get decision
    decision = state.get("decision", "No decision made yet")
    
    # Get filtered analysis_store
    filtered_store = get_filtered_analysis_store(state)
    
    # Format decision summary
    decision_summary = f"Decision: {decision}\n\n"
    
    # Try to get decision details from analysis_store
    decision_details = {}
    for key, entry in filtered_store.items():
        if "decision" in entry and entry["decision"]:
            decision_data = entry["decision"]
            decision_details = decision_data
            
            decision_summary += f"**Confidence:** {decision_data.get('confidence', 'N/A')}%\n"
            decision_summary += f"**Type:** {decision_data.get('decision_type', 'neutral')}\n\n"
            
            reasoning = decision_data.get("reasoning", {})
            if reasoning:
                decision_summary += "**Reasoning:**\n"
                if "indicator" in reasoning:
                    decision_summary += f"• Indicators: {reasoning['indicator']}\n"
                if "pattern" in reasoning:
                    decision_summary += f"• Patterns: {reasoning['pattern']}\n"
                if "trend" in reasoning:
                    decision_summary += f"• Trend: {reasoning['trend']}\n"
                decision_summary += "\n"
            
            risk_notes = decision_data.get("risk_notes", "")
            if risk_notes:
                decision_summary += f"**Risk Notes:** {risk_notes}\n"
            
            break
    
    # Format analysis details
    analysis_parts = []
    for key, entry in filtered_store.items():
        symbol = entry.get("symbol", "Unknown")
        timeframe = entry.get("timeframe", "Unknown")
        
        analysis_parts.append(f"\n{'─'*50}")
        analysis_parts.append(f"Asset: {symbol} | Timeframe: {timeframe}")
        analysis_parts.append(f"{'─'*50}\n")
        
        # Indicator
        if "indicator" in entry and entry["indicator"]:
            indicator_report = entry["indicator"].get("report", "")
            if indicator_report:
                analysis_parts.append("📊 **Indicator Analysis:**")
                analysis_parts.append(indicator_report)
                analysis_parts.append("")
        
        # Pattern
        if "pattern" in entry and entry["pattern"]:
            pattern_report = entry["pattern"].get("report", "")
            if pattern_report:
                analysis_parts.append("📈 **Pattern Analysis:**")
                analysis_parts.append(pattern_report)
                analysis_parts.append("")
        
        # Trend
        if "trend" in entry and entry["trend"]:
            trend_report = entry["trend"].get("report", "")
            if trend_report:
                analysis_parts.append("📉 **Trend Analysis:**")
                analysis_parts.append(trend_report)
                analysis_parts.append("")
    
    analysis_details = "\n".join(analysis_parts) if analysis_parts else "No detailed analysis available"
    
    return {
        "decision_summary": decision_summary,
        "analysis_details": analysis_details
    }


# ============================================================================
# HELPER: Format price data for display
# ============================================================================

def format_price_data(state: Dict[str, Any]) -> str:
    """
    Format kline_data for price check display.
    
    Args:
        state: TradingAdvisorState with kline_data_map
        
    Returns:
        Formatted price data string
    """
    kline_data_map = state.get("kline_data_map", {})
    symbols = state.get("symbols", [])
    
    if not symbols or not kline_data_map:
        return "No price data available"
    
    symbol = symbols[0]
    if symbol not in kline_data_map:
        return f"No price data available for {symbol}"
    
    data = kline_data_map[symbol]
    dates = data.get("Datetime", [])
    closes = data.get("Close", [])
    opens = data.get("Open", [])
    highs = data.get("High", [])
    lows = data.get("Low", [])
    volumes = data.get("Volume", [])
    
    if not dates or not closes:
        return f"Incomplete price data for {symbol}"
    
    # Build price information
    price_info = f"**Price Data for {symbol}**\n\n"
    
    # Show data points
    for i in range(len(dates)):
        date_str = dates[i]
        price_info += f"**{date_str}**\n"
        price_info += f"• Open: ${opens[i]:.2f}\n"
        price_info += f"• High: ${highs[i]:.2f}\n"
        price_info += f"• Low: ${lows[i]:.2f}\n"
        price_info += f"• Close: ${closes[i]:.2f}\n"
        price_info += f"• Volume: {volumes[i]:,.0f}\n\n"
    
    # Add change calculation if multiple data points
    if len(closes) > 1:
        change = closes[-1] - closes[0]
        change_pct = (change / closes[0]) * 100
        price_info += f"**Period Change:** ${change:+.2f} ({change_pct:+.2f}%)\n"
    
    return price_info


# ============================================================================
# MAIN DIALOGUE AGENT (CONVERSATIONAL)
# ============================================================================

def generate_explanation(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Generate conversational explanation for user.
    
    FORBIDDEN:
    - Changing decisions
    - Running analysis
    - Fetching data
    - Modifying analysis_store
    
    ALLOWED:
    - Reading decision output
    - Reading analysis_store (read-only)
    - Reading conversation_summary
    - Reading user_query
    - Producing natural language explanation
    
    Args:
        state: TradingAdvisorState with decision and analysis
        llm: Language model for explanation generation
        
    Returns:
        Updated state with explanation
    """
    
    user_query = state.get("user_query", "")
    intent = state.get("intent", "")
    conversation_summary = state.get("conversation_summary", "")
    
    # ====================================================================
    # SPECIAL CASE: Price check query
    # ====================================================================
    if intent in ["price_check"]:
        kline_data_map = state.get("kline_data_map", {})
        
        if not kline_data_map:
            # No data available
            symbols = state.get("symbols", [])
            symbol = symbols[0] if symbols else "the requested symbol"
            start_date = state.get("start_date", "")
            
            error_msg = f"❌ Unable to fetch data for **{symbol}**"
            if start_date:
                error_msg += f" on {start_date}"
            
            error_msg += "\n\n**Possible reasons:**\n"
            error_msg += "• The date might be a non-trading day (weekend/holiday)\n"
            error_msg += "• The symbol might be incorrect or not available\n"
            error_msg += "• Data might not be available for that specific date\n\n"
            error_msg += "**Suggestions:**\n"
            error_msg += "• Try a different date or date range\n"
            error_msg += "• Verify the symbol is correct\n"
            error_msg += "• For Indian stocks, use .NS (NSE) or .BO (BSE) suffix"
            
            return {
                **state,
                "explanation": error_msg
            }
        
        # Format price data
        price_data = format_price_data(state)
        
        # Use price check prompt
        prompt = PRICE_CHECK_PROMPT.format(
            user_query=user_query,
            price_data=price_data
        )
        
        response = llm.invoke(prompt)
        explanation = response.content.strip()
        
        return {
            **state,
            "explanation": explanation
        }
    
    # ====================================================================
    # STANDARD CASE: Explain decision and analysis
    # ====================================================================
    
    # Check if we have analysis to explain
    filtered_store = get_filtered_analysis_store(state)
    
    if not filtered_store:
        # No analysis available
        if intent == "explain":
            explanation = "I don't have any previous analysis to explain. Would you like me to analyze a specific stock first?"
        else:
            explanation = "I don't have enough information to provide a recommendation yet. Could you specify which asset you're interested in?"
        
        return {
            **state,
            "explanation": explanation
        }
    
    # Format decision and analysis for dialogue
    formatted = format_for_dialogue(state)
    decision_summary = formatted["decision_summary"]
    analysis_details = formatted["analysis_details"]
    
    # Build dialogue prompt
    prompt = DIALOGUE_AGENT_PROMPT.format(
        decision_summary=decision_summary,
        analysis_details=analysis_details,
        conversation_summary=conversation_summary[:500] if conversation_summary else "New conversation",
        user_query=user_query
    )
    
    # Invoke LLM
    response = llm.invoke(prompt)
    explanation = response.content.strip()
    
    return {
        **state,
        "explanation": explanation
    }


# ============================================================================
# NODE FACTORY
# ============================================================================

def create_dialogue_agent(llm):
    """
    Create dialogue/explanation agent node (conversational).
    
    This agent:
    - Runs for ALL queries (after decision agent if applicable)
    - Reads decision output, analysis_store, conversation_summary, user_query
    - NEVER changes decisions or runs analysis
    - Produces natural language explanation
    - User-facing and conversational
    
    Args:
        llm: Language model for dialogue generation
        
    Returns:
        Dialogue agent node function
    """
    
    def dialogue_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dialogue agent node - generates user-facing explanation.
        """
        
        intent = state.get("intent", "")
        
        print(f"\n{'='*60}")
        print(f"DIALOGUE AGENT (Conversational)")
        print(f"{'='*60}")
        print(f"Intent: {intent}")
        
        result = generate_explanation(state, llm)
        
        explanation_length = len(result.get("explanation", ""))
        print(f"Explanation generated: {explanation_length} chars")
        print(f"{'='*60}\n")
        
        return result
    
    return dialogue_agent_node
