"""
Summary-based conversational memory for financial advisor.

This module provides a safe, compact mechanism for updating the rolling conversation summary.
Raw chat history is NOT stored or replayed. Only a concise summary is kept.

SAFETY RULES:
- Raw chat history (List[BaseMessage]) is forbidden for privacy and compactness.
- Only a rolling summary is kept, updated after each user interaction.
- Summary is injected ONLY into decision/explanation logic, NEVER into analysis agents.
- Summary is advisory context only, never a fact source.
- If summary conflicts with current query, current query wins.
- Guardrails prevent summary from growing indefinitely or overriding market data.
"""

from typing import Dict, Any

def update_conversation_summary(state: Dict[str, Any], user_question: str, system_answer: str, llm) -> str:
    """
    Update the rolling conversation summary AFTER decision agent execution.
    
    SUMMARY RULES (STRICT):
    - Keep summary concise (5-10 lines max)
    - Capture ONLY: active symbols, horizons, decisions, user intent
    - DO NOT include: prices, indicators, timestamps, or raw text
    - Summary is advisory context only
    - Passed to planner and decision agent ONLY
    - NEVER passed to analysis agents
    
    Inputs:
        state: Current TradingAdvisorState (contains previous summary, user_preferences)
        user_question: Latest user query
        system_answer: Latest system answer (decision or explanation)
        llm: Language model for summary rewriting
    
    Returns:
        New concise summary string (5-10 lines max)
    """
    previous_summary = state.get("conversation_summary", "")
    user_prefs = state.get("user_preferences", {})
    
    # Extract key context for summary
    intent = state.get("intent", "")
    symbols = state.get("symbols", [])
    horizon = state.get("horizon", "")
    decision = state.get("decision", "")

    # Compose prompt for LLM with STRICT rules
    prompt = f"""
You are maintaining a CONCISE conversation summary (5-10 lines maximum).
This is advisory context only, capturing high-level conversation state.

Previous summary:
{previous_summary or "[New conversation]"}

Latest interaction:
- User intent: {intent}
- Symbols discussed: {', '.join(symbols) if symbols else 'None'}
- Horizon: {horizon or 'Not specified'}
- Decision: {decision or 'No decision yet'}
- User question: {user_question[:100]}...
- System response: {system_answer[:100]}...

User preferences:
{user_prefs}

STRICT RULES:
✓ Capture ONLY: active symbols, horizons, decisions, user intent
✗ DO NOT include: prices, indicator values (RSI/MACD/etc.), timestamps, dates, raw quotes
✗ DO NOT append - REWRITE the summary compactly
✗ DO NOT exceed 10 lines
✓ If context changes, reset or overwrite summary
✓ Use bullet points for clarity

Example good summary:
- Analyzing BEL.NS for short-term trading
- User seeks buy signals with moderate risk
- Recent decision: BUY (bullish confluence)
- Follow-up: User asking about RSI interpretation
- Preference: Conservative entries

Output ONLY the updated summary (5-10 lines). No explanations.
"""

    # Call LLM to rewrite summary
    response = llm.invoke(prompt)
    new_summary = response.content.strip()

    # Guardrail: Truncate if LLM output is too long
    lines = new_summary.splitlines()
    if len(lines) > 10:
        new_summary = "\n".join(lines[:10])

    return new_summary
