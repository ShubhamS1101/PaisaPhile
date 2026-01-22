"""
Dialogue Agent: User-facing conversational agent for explanations and clarifications.

STRICT RULES:
- NEVER changes decisions
- NEVER runs analysis
- NEVER triggers data fetch
- Reads: analysis_store, data_contexts_required, conversation_summary, user_query
- Produces: Natural language explanation only
"""

import json
from typing import Any, Dict, List
from analysis_store_util import get_filtered_analysis_store


# ============================================================================
# UNIFIED DIALOGUE AGENT PROMPT
# ============================================================================

UNIFIED_DIALOGUE_PROMPT = """You are a friendly financial trading advisor having a CONVERSATION with a client.

⚠️ CRITICAL RULES:
1. You are conversational and user-facing
2. You EXPLAIN decisions and analysis - you DON'T change them
3. You NEVER run new analysis or fetch data
4. You use ONLY the information provided below
5. Adapt your response based on what information is available
6. Be specific, cite numbers, acknowledge uncertainty

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONVERSATION HISTORY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{conversation_summary}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AVAILABLE ANALYSIS RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{analysis_context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AVAILABLE PRICE DATA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{price_data_context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USER QUERY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{user_query}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE GUIDELINES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Respond naturally based on what's available:

**If you have analysis results:**
- Explain the trading decision (BUY/SELL/HOLD) and reasoning
- Cite specific indicators, patterns, and trend data
- Mention confidence levels and risk notes
- Answer specific questions about the analysis

**If you have price data only:**
- Present the price information clearly
- Show OHLCV data in readable format
- Calculate period changes if multiple data points
- Keep it concise and data-focused

**If you have neither:**
- Answer as general trading knowledge (explain concepts, indicators, strategies)
- OR ask for clarification about what they want to analyze
- Be helpful and educational

**For mixed queries (e.g., "What's the price and should I buy?"):**
- Address all parts of the question
- Show price data first, then analysis/recommendation

TONE:
- Conversational and friendly
- Factual and data-driven
- Honest about limitations
- Patient with follow-ups

Do NOT speculate beyond the provided information.
Do NOT make up analysis or data.
If information isn't available, acknowledge it and offer alternatives.
"""


# ============================================================================
# HELPER: Format all available context for dialogue
# ============================================================================

def format_context_for_dialogue(state: Dict[str, Any]) -> Dict[str, str]:
    """
    Format all available context (analysis + price data) for dialogue agent.
    
    Args:
        state: TradingAdvisorState with analysis_store and data_contexts_required
        
    Returns:
        Dict with formatted strings for unified prompt
    """
    # Get filtered analysis_store
    filtered_store = get_filtered_analysis_store(state)
    
    # Format analysis context
    analysis_parts = []
    
    if filtered_store:
        for key, entry in filtered_store.items():
            # Extract metadata from first available agent output
            metadata = None
            for agent_name in ["indicator", "pattern", "trend", "decision"]:
                if agent_name in entry and entry[agent_name]:
                    metadata = entry[agent_name].get("metadata", {})
                    break
            
            # Fallback to unknown if no metadata found
            if not metadata:
                metadata = {}
            
            symbol = metadata.get("symbol", "Unknown")
            timeframe = metadata.get("timeframe", "Unknown")
            horizon = metadata.get("horizon", "Unknown")
            
            analysis_parts.append(f"\n{'─'*50}")
            analysis_parts.append(f"📊 {symbol} | {timeframe} | {horizon}")
            analysis_parts.append(f"{'─'*50}\n")
            
            # Decision (if exists)
            if "decision" in entry and entry["decision"]:
                decision_output = entry["decision"]
                decision_data = decision_output.get("result", {})
                
                analysis_parts.append("🎯 **TRADING DECISION:**")
                analysis_parts.append(f"• Action: {decision_data.get('decision_type', 'HOLD').upper()}")
                analysis_parts.append(f"• Confidence: {decision_data.get('confidence', 'N/A')}%")
                
                reasoning = decision_data.get("reasoning", {})
                if reasoning:
                    analysis_parts.append("\n**Reasoning:**")
                    if "indicator" in reasoning:
                        analysis_parts.append(f"• Indicators: {reasoning['indicator']}")
                    if "pattern" in reasoning:
                        analysis_parts.append(f"• Patterns: {reasoning['pattern']}")
                    if "trend" in reasoning:
                        analysis_parts.append(f"• Trend: {reasoning['trend']}")
                
                risk_notes = decision_data.get("risk_notes", "")
                if risk_notes:
                    analysis_parts.append(f"\n**Risk Notes:** {risk_notes}")
                
                analysis_parts.append("")
            
            # Indicator
            if "indicator" in entry and entry["indicator"]:
                indicator_output = entry["indicator"]
                indicator_data = indicator_output.get("result", {})
                interpretation = indicator_data.get("interpretation", "")
                if interpretation:
                    analysis_parts.append("📈 **Indicator Analysis:**")
                    analysis_parts.append(interpretation)
                    analysis_parts.append("")
            
            # Pattern
            if "pattern" in entry and entry["pattern"]:
                pattern_output = entry["pattern"]
                pattern_data = pattern_output.get("result", {})
                interpretation = pattern_data.get("interpretation", "")
                if interpretation:
                    analysis_parts.append("🔍 **Pattern Analysis:**")
                    analysis_parts.append(interpretation)
                    analysis_parts.append("")
            
            # Trend
            if "trend" in entry and entry["trend"]:
                trend_output = entry["trend"]
                trend_data = trend_output.get("result", {})
                interpretation = trend_data.get("interpretation", "")
                if interpretation:
                    analysis_parts.append("📉 **Trend Analysis:**")
                    analysis_parts.append(interpretation)
                    analysis_parts.append("")
    
    analysis_context = "\n".join(analysis_parts) if analysis_parts else "No analysis results available"
    
    # Format price data context
    price_data_parts = []
    data_contexts_required = state.get("data_contexts_required", [])
    kline_data = state.get("kline_data", {})
    
    # Track failed fetches
    failed_symbols = []
    
    if data_contexts_required and kline_data:
        for ctx in data_contexts_required:
            ctx_key = ctx.get("key", "")
            if not ctx_key:
                continue
            
            symbol = ctx.get("symbol", "Unknown")
            timeframe = ctx.get("timeframe", "Unknown")
            
            # Check if fetch failed (None value) or key doesn't exist
            if ctx_key not in kline_data:
                continue
            
            if kline_data[ctx_key] is None:
                # Fetch failed for this symbol
                failed_symbols.append(f"{symbol} ({timeframe})")
                continue
            
            data = kline_data[ctx_key]
            
            dates = data.get("Datetime", [])
            opens = data.get("Open", [])
            highs = data.get("High", [])
            lows = data.get("Low", [])
            closes = data.get("Close", [])
            volumes = data.get("Volume", [])
            
            if not dates or not closes:
                continue
            
            price_data_parts.append(f"\n{'─'*50}")
            price_data_parts.append(f"💰 {symbol} | {timeframe}")
            price_data_parts.append(f"{'─'*50}\n")
            
            # Show recent data points (last 5 or all if fewer)
            num_points = min(5, len(dates))
            for i in range(-num_points, 0):
                price_data_parts.append(f"**{dates[i]}**")
                price_data_parts.append(f"• Open: ${opens[i]:.2f}")
                price_data_parts.append(f"• High: ${highs[i]:.2f}")
                price_data_parts.append(f"• Low: ${lows[i]:.2f}")
                price_data_parts.append(f"• Close: ${closes[i]:.2f}")
                price_data_parts.append(f"• Volume: {volumes[i]:,.0f}\n")
            
            # Add period change
            if len(closes) > 1:
                change = closes[-1] - closes[0]
                change_pct = (change / closes[0]) * 100
                price_data_parts.append(f"**Period Change:** ${change:+.2f} ({change_pct:+.2f}%)\n")
    
    # Build error message for failed fetches
    if failed_symbols:
        error_msg = f"\n{'─'*50}\n❌ **Data Fetch Failed**\n{'─'*50}\n"
        error_msg += f"Unable to fetch data for: {', '.join(failed_symbols)}\n\n"
        error_msg += "**Possible reasons:**\n"
        error_msg += "• Symbol may be delisted or invalid\n"
        error_msg += "• Market may be closed (weekend/holiday)\n"
        error_msg += "• Data may not be available for the requested timeframe\n"
        error_msg += "• For Indian stocks, ensure .NS (NSE) or .BO (BSE) suffix\n"
        price_data_parts.insert(0, error_msg)
    
    price_data_context = "\n".join(price_data_parts) if price_data_parts else "No price data available"
    
    return {
        "analysis_context": analysis_context,
        "price_data_context": price_data_context
    }


# ============================================================================
# MAIN DIALOGUE AGENT (UNIFIED)
# ============================================================================

def generate_explanation(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Generate conversational explanation for user using unified prompt.
    
    Reads all available context and lets LLM decide how to respond:
    - Has analysis? Explain decision
    - Has price data? Present prices
    - Has neither? Answer as general knowledge or clarify
    
    Args:
        state: TradingAdvisorState with all context
        llm: Language model for explanation generation
        
    Returns:
        Updated state with explanation (always returns valid state)
    """
    
    # Check if explanation already exists (from clarification/validation)
    if state.get("explanation") and state.get("intent") == "clarify":
        print("✓ Using existing clarification message")
        return state
    
    user_query = state.get("user_query", "")
    conversation_summary = state.get("conversation_summary", "")
    
    # Format all available context
    formatted = format_context_for_dialogue(state)
    analysis_context = formatted["analysis_context"]
    price_data_context = formatted["price_data_context"]
    
    # Check if we have any data to work with
    has_analysis = "No analysis results available" not in analysis_context
    has_price_data = "No price data available" not in price_data_context
    has_failed_fetches = "Data Fetch Failed" in price_data_context
    
    # If all fetches failed and no analysis, provide helpful error message
    if not has_analysis and (has_failed_fetches or not has_price_data):
        explanation = """I apologize, but I wasn't able to fetch the market data needed for analysis.

**Possible reasons:**
• The symbol may be invalid or delisted
• The market may be closed (weekend/holiday)
• The requested timeframe may not have available data
• For Indian stocks, ensure you're using the correct exchange suffix (.NS for NSE or .BO for BSE)

**What you can try:**
• Verify the symbol is correct
• Try a different timeframe (e.g., daily instead of intraday)
• Check if the market is open
• Try a major symbol like AAPL, MSFT, or ^GSPC (S&P 500) to test

Would you like to try analyzing a different asset?"""
        
        return {
            **state,
            "explanation": explanation
        }
    
    # Build unified prompt with available context
    prompt = UNIFIED_DIALOGUE_PROMPT.format(
        conversation_summary=conversation_summary[:500] if conversation_summary else "New conversation - no previous context",
        analysis_context=analysis_context,
        price_data_context=price_data_context,
        user_query=user_query
    )
    
    # Invoke LLM
    try:
        response = llm.invoke(prompt)
        explanation = response.content.strip()
        
        # Ensure we have a valid response
        if not explanation:
            explanation = "I processed your request but couldn't generate a proper response. Please try rephrasing your question."
            
    except Exception as e:
        print(f"⚠️  Error generating explanation: {e}")
        explanation = f"I encountered an error while processing your request. Please try again or rephrase your question.\n\nError details: {str(e)}"
    
    # CRITICAL: Always return the full state with explanation
    return {
        **state,
        "explanation": explanation
    }


# ============================================================================
# NODE FACTORY
# ============================================================================

def create_dialogue_agent(llm):
    """
    Create dialogue agent node with unified conversational approach.
    
    This agent:
    - Runs for ALL queries (after analysis agents if applicable)
    - Reads all available context (analysis_store, data_contexts_required, conversation_summary)
    - NEVER changes decisions or runs analysis
    - Produces natural language explanation adapted to what's available
    - User-facing and conversational
    - ALWAYS returns updated state with explanation field
    
    Args:
        llm: Language model for dialogue generation
        
    Returns:
        Dialogue agent node function
    """
    
    def dialogue_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dialogue agent node - generates user-facing explanation using unified prompt.
        CRITICAL: Always returns full state with explanation.
        """
        
        print(f"\n{'='*60}")
        print(f"DIALOGUE AGENT")
        print(f"{'='*60}")
        
        # Generate explanation (always returns valid state)
        result = generate_explanation(state, llm)
        
        # Verify explanation was generated
        explanation = result.get("explanation", "")
        if explanation:
            explanation_length = len(explanation)
            print(f"✓ Explanation generated: {explanation_length} chars")
        else:
            print(f"⚠️  Warning: Empty explanation generated")
            # Provide fallback
            result["explanation"] = "I processed your request but couldn't generate a response. Please try again."
        
        print(f"{'='*60}\n")
        
        return result
    
    return dialogue_agent_node
