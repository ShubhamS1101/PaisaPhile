"""
Planner Agent: Query Interpretation and Routing
Runs ONCE per user query to determine intent and required actions.
"""

import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict
import pytz

from langchain_core.messages import HumanMessage, SystemMessage



# ============================================================================
# PLANNER SYSTEM PROMPT
# ============================================================================

PLANNER_SYSTEM_PROMPT = """You are a financial query planning agent. Your ONLY job is to analyze user queries and output execution instructions in STRICT JSON format.

⚠️ CRITICAL RULES - WHAT YOU MUST DO:
1. Output ONLY valid JSON - no explanations, no markdown, no extra text
2. Analyze user intent and extract parameters ONLY
3. Populate required fields: intent, data_requirement, symbols, timeframe, horizon, start_date, end_date, required_analyses
4. If ANY critical information is missing, set need_clarification=true and ask explicitly

⚠️ CRITICAL RULES - WHAT YOU MUST NOT DO:
1. NEVER fetch data or call APIs
2. NEVER perform analysis or reasoning about market conditions
3. NEVER guess missing information (symbols, timeframe, dates)
4. NEVER reference cached analysis or previous results
5. NEVER answer user questions directly - only classify and route
6. NEVER make trading recommendations or predictions

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT (STRICT JSON)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "intent": "<intent_type>",
  "data_requirement": "<required|optional|not_required>",
  "horizon": "<horizon_type>",
  "symbols": ["<symbol1>", "<symbol2>", ...],
  "mode": "<mode_type>",
  "timeframe": "<timeframe>",
  "start_date": "<date_or_null>",
  "end_date": "<date_or_null>",
  "required_analyses": ["<analysis1>", "<analysis2>", ...],
  "need_clarification": <true_or_false>,
  "clarification_question": "<question_or_null>"
}

FIELD DEFINITIONS:

intent (required):
  - "trade" = user wants buy/sell recommendation (NEW analysis needed)
  - "trend" = user wants to know direction/trend (NEW analysis needed)
  - "compare" = user wants to compare multiple assets (NEW analysis needed)
  - "explain" = user asks follow-up questions about EXISTING analysis (NO new analysis)
  - "historical" = user wants past performance data
  - "price_check" = user wants current/recent price info
  - "clarify" = query is too vague, need more info
  
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONVERSATION AWARENESS (CRITICAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If previous conversation exists (previous_symbols, previous_intent provided):

Use intent = "explain" for follow-up questions like:
- "why?" / "why did you say that?" / "explain"
- "what about the indicators?" / "what indicators show this?"
- "is RSI overbought?" / "what's the MACD saying?"
- "what patterns did you see?"
- "but I think it will go up" / "I disagree"
- "what if..." / "should I still..."
- ANY question that discusses/argues about EXISTING analysis

Use intent = "trade/trend/compare" ONLY for:
- Fresh analysis requests on NEW symbols
- Explicit re-analysis requests ("analyze again", "check now")
- Different symbol than previous_symbols

Example:
- Query 1: "should I buy BEL.NS?" → intent: "trade" (NEW analysis)
- Query 2: "why?" → intent: "explain" (discuss existing analysis)
- Query 3: "what about RSI?" → intent: "explain" (discuss existing indicators)
- Query 4: "but I think it will go up" → intent: "explain" (argue with decision)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATA REQUIREMENT RULES (MANDATORY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Set data_requirement as follows:
- trade, trend, compare, historical, price_check → "required"
- explain → "optional" (uses cached analysis, no new data fetch)
- clarify, chat → "not_required"

⚠️ MANDATORY VALIDATION:
If data_requirement = "required", then ALL of these MUST be non-null:
- symbols (non-empty array)
- horizon (non-null string)
- timeframe (non-null string)
- start_date (YYYY-MM-DD format)
- end_date (YYYY-MM-DD format)

If ANY of the above are missing or cannot be determined:
- need_clarification MUST be true
- clarification_question MUST ask SPECIFICALLY for the missing information
- Do NOT guess, infer, or assume - ask explicitly

Example clarification questions:
- Missing symbol: "Which stock or cryptocurrency would you like to analyze? Please provide the ticker symbol (e.g., AAPL, BTC-USD)."
- Missing timeframe: "What timeframe are you interested in? Please specify (e.g., 5m, 1h, 1d, 1w)."
- Missing horizon: "What's your trading horizon? Intraday (minutes to hours), swing (days to weeks), or long-term (months)?"
- Ambiguous query: "I need more details to help you. Please specify: which asset, what timeframe, and what you'd like to know."



intent (required):
  - "trade" = user wants buy/sell recommendation
  - "trend" = user wants to know direction/trend
  - "compare" = user wants to compare multiple assets
  - "explain" = user asks about cached analysis results
  - "historical" = user wants past performance data
  - "price_check" = user wants current/recent price info
  - "clarify" = query is too vague, need more info
  


horizon (required if intent != clarify):
  - "intraday" = minutes to hours (5m, 15m, 1h)
  - "swing" = days to weeks (1d, 1w)
  - "long_term" = months to years (1mo, 3mo)
  - null = if unclear or not applicable

symbols (required):
  - Extract ticker symbols from query
  - Common mappings: Bitcoin→BTC-USD, Apple→AAPL, S&P 500→^GSPC, Tesla→TSLA
  - If unclear, leave empty [] and set need_clarification=true

mode (required):
  - "single" = one symbol analysis
  - "comparison" = multiple symbols compared
  - "split" = same symbol, different timeframes

timeframe (recommended):
  - Valid: "5m", "15m", "1h", "4h", "1d", "1w", "1mo"
  - Infer from horizon or explicit mention
  - null if not determinable
  
start_date / end_date (CRITICAL - required if data_requirement = "required"):
  - Format: "YYYY-MM-DD" (MANDATORY for Yahoo Finance API)
  - MUST be set when data_requirement = "required"
  - Use CURRENT_DATE as reference (provided in system message)
  
  Rules for setting dates:
  1. If user asks about "now", "current", "today":
     - For intraday (5m, 15m, 1h, 4h): start_date = CURRENT_DATE, end_date = CURRENT_DATE
     - For daily (1d): start_date = 30 days before CURRENT_DATE, end_date = CURRENT_DATE
     - For weekly (1w): start_date = 90 days before CURRENT_DATE, end_date = CURRENT_DATE
  
  2. If user specifies exact date (e.g., "on Dec 30"):
     - Extract and use that specific date for both start_date and end_date
  
  3. If user specifies date range (e.g., "from Jan 1 to Jan 10"):
     - Use provided start and end dates
  
  4. If data_requirement = "not_required":
     - Both must be null
  
  ⚠️ NEVER leave start_date or end_date as null when data_requirement = "required"
  ⚠️ If you cannot determine the dates, set need_clarification=true and ask

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REQUIRED_ANALYSES FIELD (STRICT ROUTING)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   
required_analyses determines which internal agents must run to answer the user query.

Allowed values (choose only from these):
["indicator", "pattern", "trend", "decision"]

Meanings:
- indicator → technical indicators such as RSI, MACD, momentum
- pattern → candlestick patterns and chart formations
- trend → market structure, support/resistance, directional bias
- decision → final synthesis or explanation using existing information ONLY

⚠️ CRITICAL: Do NOT guess which analyses are needed based on market knowledge
⚠️ CRITICAL: Do NOT perform analysis - only specify what needs to be done

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANALYSIS SELECTION RULES (STRICT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If intent = "trade":
- If the user asks for a quick / fast / short / immediate opinion:
  → ["trend", "decision"]
- Otherwise (default and safer mode):
  → ["indicator", "pattern", "trend", "decision"]

If intent = "trend":
- If user wants a quick directional view:
  → ["trend", "decision"]
- Otherwise:
  → ["trend", "indicator", "decision"]

If intent = "compare":
- If user wants a quick comparison:
  → ["trend", "decision"]
- Otherwise:
  → ["indicator", "trend", "decision"]

If intent = "price_check":
→ ["decision"]

If intent = "explain":
→ ["decision"]

If intent = "clarify":
→ []

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMPORTANT SAFETY RULES (FINAL CHECKS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. NEVER perform analysis yourself - only route to appropriate agents
2. NEVER reference cached data or previous analysis - you don't have access to it
3. NEVER make assumptions about missing information - ask for clarification
4. NEVER include reasoning about market conditions or indicators in your output
5. If you're unsure about ANY parameter, set need_clarification=true
6. Your output is authoritative ONLY for the current turn - don't assume persistence
7. If required_analyses is empty for trade/trend intent, something is wrong - set need_clarification=true

⚠️ REMEMBER: 
- OUTPUT ONLY JSON
- NO OTHER TEXT
- NO MARKDOWN
- NO EXPLANATIONS
- NO ANALYSIS
- JUST ROUTING INSTRUCTIONS


need_clarification (required):
  - true = query is ambiguous, missing critical info (symbol, timeframe, etc.)
  - false = query is clear enough to proceed

clarification_question (conditional):
  - If need_clarification=true, ask specific question
  - Examples: "Which stock would you like to analyze?", "What timeframe are you interested in?"
  - null if need_clarification=false



⚠️ REMEMBER: OUTPUT ONLY JSON. NO OTHER TEXT. NO MARKDOWN. NO EXPLANATIONS.
"""
# EXAMPLE QUERIES AND OUTPUTS:

# Query: "Should I buy Bitcoin right now?"
# Current date: 2026-01-01
# Output:
# {
#   "intent": "trade",
#   "data_requirement": "required",
#   "horizon": "intraday",
#   "symbols": ["BTC-USD"],
#   "mode": "single",
#   "timeframe": "4h",
#   "start_date": "2026-01-01",
#   "end_date": "2026-01-01",
#   "required_analyses": ["indicator", "pattern", "trend", "decision"],
#   "need_clarification": false,
#   "clarification_question": null
# }

# Query: "What's the trend for Apple?"
# Current date: 2026-01-01
# Output:
# {
#   "intent": "trend",
#   "data_requirement": "required",
#   "horizon": "swing",
#   "symbols": ["AAPL"],
#   "mode": "single",
#   "timeframe": "1d",
#   "start_date": "2025-12-02",
#   "end_date": "2026-01-01",
#   "required_analyses": ["trend", "indicator", "decision"],
#   "need_clarification": false,
#   "clarification_question": null
# }

# Query: "Compare Bitcoin and Ethereum"
# Current date: 2026-01-01
# Output:
# {
#   "intent": "compare",
#   "data_requirement": "required",
#   "horizon": "swing",
#   "symbols": ["BTC-USD", "ETH-USD"],
#   "mode": "comparison",
#   "timeframe": "1d",
#   "start_date": "2025-12-02",
#   "end_date": "2026-01-01",
#   "required_analyses": ["indicator", "trend", "decision"],
#   "need_clarification": false,
#   "clarification_question": null
# }

# Query: "What do you think about the market?"
# Output:
# {
#   "intent": "clarify",
#   "data_requirement": "not_required",
#   "horizon": null,
#   "symbols": [],
#   "mode": "single",
#   "timeframe": null,
#   "start_date": null,
#   "end_date": null,
#   "required_analyses": [],
#   "need_clarification": true,
#   "clarification_question": "Which specific market or stock would you like me to analyze? For example: Bitcoin, S&P 500, Apple, etc."
# }

# Query: "Why did you recommend buying earlier?"
# Output:
# {
#   "intent": "explain",
#   "data_requirement": "optional",
#   "horizon": null,
#   "symbols": [],
#   "mode": "single",
#   "timeframe": null,
#   "start_date": null,
#   "end_date": null,
#   "required_analyses": [],
#   "need_clarification": false,
#   "clarification_question": null
# }

# ============================================================================
# PLANNER AGENT IMPLEMENTATION
# ============================================================================

import json
import re
from typing import Any, Dict
from langchain_core.messages import SystemMessage, HumanMessage




def create_planner_agent(llm):
    """
    Planner Agent
    Interprets user_query and produces an execution plan.
    """

    def planner_node(state: Dict[str, Any]) -> Dict[str, Any]:

        user_query = state.get("user_query")

        # --------------------------------------------------
        # 1. No user query → clarification
        # --------------------------------------------------
        if not user_query:
            return {
                **state,
                "intent": "clarify",
                "data_requirement": "not_required",
                "required_analyses": [],
                "need_clarification": True,
                "explanation": "How can I help you with market analysis today?",
            }

        # --------------------------------------------------
        # 2. Gather conversation context for the planner
        # --------------------------------------------------
        conversation_summary = state.get("conversation_summary", "")
        previous_symbols = state.get("symbols", [])
        previous_intent = state.get("intent", "")
        
        # Build context string for the planner
        context_info = ""
        if conversation_summary:
            context_info += f"\nPrevious conversation: {conversation_summary}"
        if previous_symbols:
            context_info += f"\nPrevious symbols discussed: {', '.join(previous_symbols)}"
        if previous_intent:
            context_info += f"\nPrevious intent: {previous_intent}"
        
        # --------------------------------------------------
        # 3. Call LLM planner with IST timezone and context
        # --------------------------------------------------
        ist = pytz.timezone('Asia/Kolkata')
        now_ist = datetime.now(ist)
        current_date = now_ist.strftime("%Y-%m-%d")
        current_time = now_ist.strftime("%H:%M:%S")
        
        planner_messages = [
            SystemMessage(content=f"""CURRENT_DATE: {current_date}
CURRENT_TIME: {current_time} IST
{context_info}

{PLANNER_SYSTEM_PROMPT}

⚠️ CONTEXT AWARENESS:
- If user refers to "it", "this stock", "that symbol" without naming it, use previous_symbols from context
- If user asks follow-up questions about price/analysis, reuse the symbols from previous conversation
- Example: If previous query was about "BEL.NS" and user now asks "what is its current price", use "BEL.NS"
"""),
            HumanMessage(content=f"User query: {user_query}\nOutput JSON only.")
        ]

        response = llm.invoke(planner_messages)
        response_text = response.content.strip()

        # --------------------------------------------------
        # 3. Extract JSON safely
        # --------------------------------------------------
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if not json_match:
            return {
                **state,
                "intent": "clarify",
                "data_requirement": "not_required",
                "required_analyses": [],
                "need_clarification": True,
                "explanation": "I couldn’t understand your request. Could you rephrase it?",
            }

        try:
            planner_output = json.loads(json_match.group(0))
        except Exception:
            return {
                **state,
                "intent": "clarify",
                "data_requirement": "not_required",
                "required_analyses": [],
                "need_clarification": True,
                "explanation": "I couldn’t parse your request properly. Could you rephrase it?",
            }

        # --------------------------------------------------
        # 4. Planner output → state update WITH context preservation
        # --------------------------------------------------
        updated_state = {**state}

        updated_state["intent"] = planner_output.get("intent", "clarify")
        updated_state["data_requirement"] = planner_output.get(
            "data_requirement", "not_required"
        )

        # 🔥 PRESERVE previous symbols if planner returns empty
        new_symbols = planner_output.get("symbols", [])
        if new_symbols:
            updated_state["symbols"] = new_symbols
        elif previous_symbols and updated_state["intent"] != "clarify":
            # Keep previous symbols for follow-up questions
            updated_state["symbols"] = previous_symbols
            print(f"ℹ️  Reusing previous symbols: {previous_symbols}")
        else:
            updated_state["symbols"] = []
        
        updated_state["horizon"] = planner_output.get("horizon")
        updated_state["timeframe"] = planner_output.get("timeframe")
        updated_state["mode"] = planner_output.get("mode", "single")
        updated_state["start_date"] = planner_output.get("start_date")
        updated_state["end_date"] = planner_output.get("end_date")
        updated_state["required_analyses"] = planner_output.get(
            "required_analyses", []
        )

        need_clarification = planner_output.get("need_clarification", False)
        updated_state["need_clarification"] = need_clarification

        if need_clarification:
            updated_state["explanation"] = planner_output.get(
                "clarification_question",
                "Could you provide more details?"
            )
            # Ensure no execution happens
            updated_state["required_analyses"] = []
            updated_state["data_requirement"] = "not_required"

        # --------------------------------------------------
        # 5. Populate execution keys for cache-aware routing
        # --------------------------------------------------
        from analysis_store_util import populate_execution_keys
        
        # Only populate if we have data requirements
        if (updated_state["data_requirement"] == "required" and 
            updated_state["symbols"] and 
            updated_state["timeframe"] and
            updated_state["start_date"] and
            updated_state["end_date"] and
            updated_state["required_analyses"]):
            
            populate_execution_keys(
                state=updated_state,
                symbols=updated_state["symbols"],
                timeframe=updated_state["timeframe"],
                start_date=updated_state["start_date"],
                end_date=updated_state["end_date"],
                required_analyses=updated_state["required_analyses"]
            )
            print(f"✓ Execution keys populated: {len(updated_state.get('data_required_keys', []))} data keys, {len(updated_state.get('required_analysis_keys', {}))} analysis keys")

        # --------------------------------------------------
        # 6. Debug (KEEP THIS while developing)
        # --------------------------------------------------
        print("\n" + "=" * 60)
        print("PLANNER OUTPUT")
        print("=" * 60)
        print(f"Query            : {user_query}")
        print(f"Intent           : {updated_state['intent']}")
        print(f"Data Requirement : {updated_state['data_requirement']}")
        print(f"Symbols          : {updated_state['symbols']}")
        print(f"Horizon          : {updated_state['horizon']}")
        print(f"Timeframe        : {updated_state['timeframe']}")
        print(f"Mode             : {updated_state['mode']}")
        print(f"Analyses         : {updated_state['required_analyses']}")
        print(f"Clarification    : {updated_state['need_clarification']}")
        if updated_state.get("explanation"):
            print(f"Message          : {updated_state['explanation']}")
        print("=" * 60 + "\n")

        return updated_state

    return planner_node



# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def validate_planner_output(planner_output: Dict[str, Any]) -> bool:
    """
    Validate planner output schema.
    
    Args:
        planner_output: Parsed JSON from planner
        
    Returns:
        True if valid, False otherwise
    """
    required_fields = ["intent", "mode", "required_analyses", "need_clarification"]
    
    for field in required_fields:
        if field not in planner_output:
            print(f"❌ Missing required field: {field}")
            return False
    
    valid_intents = ["trade", "trend", "compare", "explain", "historical", "price_check", "clarify"]
    if planner_output["intent"] not in valid_intents:
        print(f"❌ Invalid intent: {planner_output['intent']}")
        return False
    
    valid_modes = ["single", "comparison", "split"]
    if planner_output["mode"] not in valid_modes:
        print(f"❌ Invalid mode: {planner_output['mode']}")
        return False
    
    return True


# ============================================================================
# SYSTEM VALIDATOR (Pure Python - No LLM)
# This prevents unsafe financial advice and ensures data consistency
# ============================================================================

class ValidationResult:
    """Result of system validation."""
    
    def __init__(self, approved: bool, reason: str = None, clarification: str = None):
        self.approved = approved
        self.reason = reason
        self.clarification = clarification
    
    def __repr__(self):
        if self.approved:
            return f"ValidationResult(approved=True)"
        else:
            return f"ValidationResult(approved=False, reason='{self.reason}')"


def system_validator(state: Dict[str, Any]) -> ValidationResult:
    """
    System validator - validates planner output before data fetch.
    Pure Python function with NO LLM calls.
    
    ENFORCES STRICT RULES:
    1. If data_requirement = "required", ALL fields (symbols, horizon, timeframe, start_date, end_date) must be non-null
    2. No guessing - if information is missing, request clarification
    3. Validate required_analyses is appropriate for intent
    
    This prevents unsafe financial advice by enforcing:
    - Complete information before data fetch
    - Consistent timeframes across comparisons
    - Appropriate analysis for query types
    
    Args:
        state: TradingAdvisorState after planner execution
        
    Returns:
        ValidationResult: approved=True/False with optional clarification question
    """
    
    intent = state.get("intent", "")
    data_requirement = state.get("data_requirement", "not_required")
    horizon = state.get("horizon")
    symbols = state.get("symbols", [])
    mode = state.get("mode", "single")
    timeframe = state.get("timeframe")
    start_date = state.get("start_date")
    end_date = state.get("end_date")
    required_analyses = state.get("required_analyses", [])
    
    # ========================================================================
    # RULE 0: Check if planner already requested clarification
    # ========================================================================
    
    if intent == "clarify" or state.get("need_clarification"):
        clarification = state.get("clarification_question") or state.get("explanation", "Could you provide more details?")
        return ValidationResult(
            approved=False,
            reason="Planner requested clarification",
            clarification=clarification
        )
    
    # ========================================================================
    # RULE 1: MANDATORY - If data_requirement = "required", validate ALL fields
    # This is the strictest rule - no data fetch without complete information
    # ========================================================================
    
    if data_requirement == "required":
        missing_fields = []
        
        if not symbols or len(symbols) == 0:
            missing_fields.append("symbols")
        if not horizon:
            missing_fields.append("horizon")
        if not timeframe:
            missing_fields.append("timeframe")
        if not start_date:
            missing_fields.append("start_date")
        if not end_date:
            missing_fields.append("end_date")
        
        if missing_fields:
            # Build specific clarification question based on what's missing
            if "symbols" in missing_fields:
                clarification = "Which stock or cryptocurrency would you like to analyze? Please provide the ticker symbol (e.g., AAPL for Apple, BTC-USD for Bitcoin)."
            elif "timeframe" in missing_fields or "horizon" in missing_fields:
                clarification = "What timeframe and trading horizon are you interested in? For example: intraday (5m, 15m, 1h), swing (1d, 1w), or long-term (1mo)."
            elif "start_date" in missing_fields or "end_date" in missing_fields:
                clarification = "What date range would you like to analyze? For example: 'current prices', 'last 30 days', or a specific date range."
            else:
                clarification = f"I need more information to proceed. Missing: {', '.join(missing_fields)}. Please provide these details."
            
            return ValidationResult(
                approved=False,
                reason=f"data_requirement=required but missing: {', '.join(missing_fields)}",
                clarification=clarification
            )
    
    # ========================================================================
    # RULE 2: If horizon is missing for analysis intents, ask for clarification
    # This prevents unsafe financial advice by ensuring appropriate timeframe selection
    # ========================================================================
    
    if intent in ["trade", "trend", "compare"] and not horizon:
        return ValidationResult(
            approved=False,
            reason="Missing horizon for analysis",
            clarification="What timeframe are you interested in? For example: intraday (minutes to hours), swing trading (days to weeks), or long-term (months)?"
        )
    
    # ========================================================================
    # RULE 3: If symbols are missing for analysis, ask for clarification
    # This prevents unsafe financial advice by ensuring we analyze the correct assets
    # ========================================================================
    
    if intent in ["trade", "trend", "compare"] and not symbols:
        return ValidationResult(
            approved=False,
            reason="Missing ticker symbols",
            clarification="Which stock or cryptocurrency would you like me to analyze? For example: Bitcoin, Apple (AAPL), Tesla (TSLA), or S&P 500."
        )
    
    # ========================================================================
    # RULE 4: If timeframe is missing, try to infer from horizon
    # This prevents unsafe financial advice by using appropriate timeframes
    # ========================================================================
    
    if not timeframe and horizon:
        # Auto-infer timeframe based on horizon
        timeframe_map = {
            "intraday": "1h",      # Default to 1-hour for intraday
            "swing": "1d",         # Default to daily for swing
            "long_term": "1w"      # Default to weekly for long-term
        }
        inferred_timeframe = timeframe_map.get(horizon)
        
        if not inferred_timeframe:
            return ValidationResult(
                approved=False,
                reason="Cannot infer timeframe from horizon",
                clarification="What specific timeframe would you like? For example: 1h (hourly), 4h (4-hour), 1d (daily), or 1w (weekly)?"
            )
        
        # Update state with inferred timeframe
        state["timeframe"] = inferred_timeframe
        print(f"ℹ️  Inferred timeframe: {inferred_timeframe} from horizon: {horizon}")
    
    # ========================================================================
    # RULE 5: Comparison mode must have consistent timeframes
    # This prevents unsafe financial advice by ensuring apples-to-apples comparisons
    # ========================================================================
    
    if mode == "comparison" and len(symbols) > 1:
        # All symbols in comparison must use same timeframe
        # This is enforced by using single timeframe value
        if not timeframe:
            return ValidationResult(
                approved=False,
                reason="Comparison requires explicit timeframe",
                clarification=f"To compare {', '.join(symbols)}, what timeframe should I use? For example: 1d (daily), 1w (weekly)?"
            )
        
        # Check for mixed horizons (advanced safety check)
        # If user asks "compare Bitcoin daily and Apple weekly" this would be detected
        # For now, we assume single horizon/timeframe per comparison
        print(f"✓ Comparison validated: {len(symbols)} symbols on {timeframe} timeframe")
    
    # ========================================================================
    # RULE 6: Multiple tickers with split mode requires clarification
    # This prevents unsafe financial advice by avoiding ambiguous multi-symbol multi-timeframe scenarios
    # ========================================================================
    
    if mode == "split" and len(symbols) > 1:
        return ValidationResult(
            approved=False,
            reason="Split mode does not support multiple tickers",
            clarification="Split mode analyzes one symbol across different timeframes. Did you mean to compare multiple symbols instead?"
        )
    
    # ========================================================================
    # RULE 7: Factual intents (price_check, historical) need decision agent only
    # The decision agent will extract and format the price data
    # ========================================================================
    
    if intent in ["price_check", "historical"]:
        # Override: factual queries only need decision agent to format output
        if required_analyses != ["decision"]:
            state["required_analyses"] = ["decision"]
            print(f"ℹ️  Factual query detected - using decision agent only")
        
        # These intents are approved with decision agent
        return ValidationResult(approved=True, reason="Factual query - decision agent will format data")
    
    # ========================================================================
    # RULE 8: Explain intent should use cached data
    # This prevents unsafe financial advice by avoiding re-analysis for clarification questions
    # ========================================================================
    
    if intent == "explain":
        # Check if we have cached analysis
        has_cache = (
            state.get("indicators", {}) or 
            state.get("trend", {}) or 
            state.get("pattern", {})
        )
        
        if not has_cache:
            return ValidationResult(
                approved=False,
                reason="No cached analysis to explain",
                clarification="I don't have any previous analysis to explain. Would you like me to analyze a specific stock first?"
            )
        
        # Approved - use cached data
        return ValidationResult(approved=True, reason="Using cached analysis")
    
    # ========================================================================
    # RULE 9: Trade intent must have full analysis pipeline
    # This prevents unsafe financial advice by ensuring comprehensive analysis before recommendations
    # ========================================================================
    
    if intent == "trade":
        required_full_analysis = ["indicator", "pattern", "trend", "decision"]
        missing_analyses = set(required_full_analysis) - set(required_analyses)
        
        if missing_analyses:
            print(f"⚠️  Trade intent missing analyses: {missing_analyses}")
            # Auto-add missing analyses for safety
            state["required_analyses"] = required_full_analysis
            print(f"✓ Auto-corrected to full analysis pipeline for trade recommendation")
    
    # ========================================================================
    # RULE 10: Final validation - ensure critical fields are present
    # This prevents unsafe financial advice by catching any edge cases
    # ========================================================================
    
    if intent in ["trade", "trend", "compare"]:
        if not symbols or not timeframe or not horizon:
            return ValidationResult(
                approved=False,
                reason="Missing critical information",
                clarification="I need more information. Please specify: which stock/crypto, what timeframe (1h, 1d, 1w), and what's your trading style (intraday, swing, long-term)?"
            )
    
    # ========================================================================
    # All validations passed
    # ========================================================================
    
    print(f"✓ System validation passed")
    print(f"  Intent: {intent}")
    print(f"  Symbols: {symbols}")
    print(f"  Timeframe: {timeframe}")
    print(f"  Horizon: {horizon}")
    print(f"  Required Analyses: {required_analyses}")
    
    return ValidationResult(approved=True, reason="All validations passed")


def validate_and_route(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Combined planner validation and routing decision.
    
    This function runs after planner agent and before data fetcher.
    It validates the plan and either approves it or requests clarification.
    
    Args:
        state: TradingAdvisorState after planner execution
        
    Returns:
        Updated state with validation results
    """
    
    validation = system_validator(state)
    
    if not validation.approved:
        # Validation failed - need clarification
        print(f"\n⚠️  Validation blocked: {validation.reason}")
        print(f"   Clarification: {validation.clarification}\n")
        
        # Set state to clarify mode
        state["intent"] = "clarify"
        state["explanation"] = validation.clarification
        state["required_analyses"] = []
        state["context_ready"] = False
        
        return state
    
    # Validation passed - proceed to data fetch
    print(f"\n✓ Validation approved: {validation.reason}\n")
    return state
