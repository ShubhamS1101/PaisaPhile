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
    Update the rolling conversation summary using an LLM.
    
    Inputs:
        state: Current TradingAdvisorState (contains previous summary, user_preferences)
        user_question: Latest user query
        system_answer: Latest system answer (decision or explanation)
        llm: Language model for summary rewriting
    
    Returns:
        New concise summary string (5-10 lines max)
    
    Guardrails:
    - Summary must be concise (max 10 lines)
    - Must capture: active symbols, horizon, risk, constraints, recent decisions
    - Must NOT include raw user wording, indicator values, timestamps, or prices
    - If summary grows too long, LLM is instructed to rewrite compactly
    - If context changes drastically, summary may be reset or overwritten
    """
    previous_summary = state.get("conversation_summary", "")
    user_prefs = state.get("user_preferences", {})

    # Compose prompt for LLM
    prompt = f"""
You are a professional financial advisor maintaining a compact summary of the ongoing conversation.
Your job is to rewrite the summary after each user interaction, keeping it concise (max 10 lines).

Previous summary:
{previous_summary}

User question:
{user_question}

System answer:
{system_answer}

User preferences:
{user_prefs}

Instructions:
- DO NOT include raw user wording, indicator values, timestamps, or prices.
- DO NOT append blindly; rewrite the summary compactly.
- Capture: active symbols, horizon, risk style, constraints, recent decisions.
- If context changes, reset or overwrite summary as needed.
- If summary is too long, compress to 5-10 lines.

Output ONLY the updated summary text. No explanations, no markdown.
"""

    # Call LLM to rewrite summary
    response = llm.invoke(prompt)
    new_summary = response.content.strip()

    # Guardrail: Truncate if LLM output is too long
    lines = new_summary.splitlines()
    if len(lines) > 10:
        new_summary = "\n".join(lines[:10])

    return new_summary
