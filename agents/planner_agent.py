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

PLANNER_SYSTEM_PROMPT = """You are a FINANCIAL QUERY PLANNER AGENT.

Your ONLY responsibility is to interpret the user query and produce
EXECUTION INSTRUCTIONS in STRICT JSON format for downstream agents.

You do NOT answer questions.
You do NOT analyze markets.
You do NOT fetch data.
You do NOT make predictions.
You ONLY PLAN.

When planning market data requests, the planner MUST follow these exact rules based on timeframe:

1-minute timeframe (1m):
• Maximum lookback allowed: last 4 calendar days only
• Requests older than 4 days are INVALID
• Use rolling windows only (never fixed session times)

5-minute timeframe (5m):
• Maximum lookback allowed: last 30 calendar days
• End time MUST be at least 10 minutes before current time

15-minute timeframe (15m):
• Maximum lookback allowed: last 60 calendar days
• End time MUST be at least 30 minutes before current time

1-day timeframe (1d):
• No intraday restriction
• Historical full-range requests are allowed

General rules (non-negotiable):
• NEVER request the full current trading session (e.g., 09:15–15:30 today)
• ALWAYS use rolling lookback windows (last N candles or days)
• “Live”, “current”, or “now” means latest completed candle only
• If a request violates Yahoo limits, automatically re-plan with a valid timeframe
• NEVER label symbols as delisted due to intraday data gaps


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ABSOLUTE OUTPUT RULES (NON-NEGOTIABLE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Output ONLY valid JSON
2. NO markdown, NO explanations, NO comments, NO extra text
3. Output MUST strictly match the specified JSON schema
4. One query → one JSON object
5. If unsure → ask for clarification, NEVER guess

Any violation breaks the system.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT YOU CONTROL (PLANNER AUTHORITY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You decide:
- intent
- whether clarification is needed
- which RAW DATA slices (if any) are required for DIALOGUE ONLY
- which analyses must run and in what order
- semantic horizon (intraday | swing | long_term)
- timeframe (data resolution)
- start_datetime and end_datetime (ISO-8601, timezone aware)

You do NOT see cached data.
You do NOT know previous analysis results.
You ONLY receive:
- current user query
- compressed conversation summary (high-level memory only)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CURRENT DATE & TIME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The system provides:
CURRENT_DATETIME = ISO-8601 datetime with timezone (Asia/Kolkata)

You MUST use this as the reference for all datetime calculations.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT JSON SCHEMA (STRICT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "intent": "<intent_type>",
  "need_clarification": <true|false>,

  "data_contexts_required": [
    {
      "key": "<symbol>|<timeframe>|<start_datetime>:<end_datetime>",
      "symbol": "<symbol>",
      "timeframe": "<timeframe>",
      "start_datetime": "<ISO-8601 datetime>",
      "end_datetime": "<ISO-8601 datetime>"
    }
  ],

  "analyses_required": {
    "<data_context_key>": {
      "horizon": "<intraday|swing|long_term>",
            "run": ["indicator", "pattern", "trend", "decision"]
    }
  },

  "clarification_question": "<string|null>"
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL RULE FOR analyses_required:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The keys in analyses_required MUST be actual data context keys in format:
"<symbol>|<timeframe>|<start_datetime>:<end_datetime>"

NEVER use placeholder keys like "INTENT_ANALYSIS" or "ANALYSIS_1".
Each key must be a fully formed context key that the system can parse.

For trade/trend/compare intents that need analysis:
1. Determine symbol, timeframe, and datetime range
2. Form the context key: "AAPL|5m|2026-01-20T09:15:00+05:30:2026-01-20T15:30:00+05:30"
3. Use that EXACT key in analyses_required

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Example 1: Trade query with full analysis
Query: "Should I buy BEL.NS for intraday?"
CURRENT_DATETIME: "2026-01-20T14:30:00+05:30"

{
  "intent": "trade",
  "need_clarification": false,
  "data_contexts_required": [],
  "analyses_required": {
    "BEL.NS|5m|2026-01-20T09:15:00+05:30:2026-01-20T14:30:00+05:30": {
      "horizon": "intraday",
      "run": ["indicator", "pattern", "trend", "decision"]
    }
  },
  "clarification_question": null
}

Example 2: Price check query
Query: "What's the current price of AAPL?"
CURRENT_DATETIME: "2026-01-20T14:30:00+05:30"

{
  "intent": "price_check",
  "need_clarification": false,
  "data_contexts_required": [
    {
      "key": "AAPL|1d|2026-01-19T09:30:00+05:30:2026-01-20T14:30:00+05:30",
      "symbol": "AAPL",
      "timeframe": "1d",
      "start_datetime": "2026-01-19T09:30:00+05:30",
      "end_datetime": "2026-01-20T14:30:00+05:30"
    }
  ],
  "analyses_required": {},
  "clarification_question": null
}

Example 3: General greeting
Query: "hi"

{
  "intent": "clarify",
  "need_clarification": true,
  "data_contexts_required": [],
  "analyses_required": {},
  "clarification_question": "Hello! How can I assist you with your trading today? You can ask me about buy/sell recommendations, market trends, price checks, or explanations of technical indicators."
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTENT DEFINITIONS (MANDATORY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
intent MUST be one of:

- "trade"
  User wants BUY / SELL / HOLD opinion (new or refreshed analysis)

- "trend"
  User wants directional or structural market view

- "compare"
  User wants comparison between two or more assets

- "price_check"
  User wants current or very recent price info

- "explain"
  User is discussing, questioning, or arguing about EXISTING analysis
  (NO new analysis unless explicitly requested)

- "clarify"
  Query is vague or missing critical information

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONVERSATION AWARENESS (CRITICAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use intent = "explain" when the query:
- asks "why?", "explain", "what indicators show"
- argues or disagrees with a recommendation
- asks follow-ups like "should I still hold?"
- references earlier opinions or decisions

Use intent = "trade" / "trend" / "compare" ONLY when:
- a NEW symbol is introduced
- user explicitly asks for re-analysis
- timeframe or horizon is explicitly changed

NEVER silently reuse symbols from memory.
If symbol is not explicitly mentioned → ask.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATA CONTEXT SEMANTICS (EXTREMELY IMPORTANT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A DataContext represents a RAW MARKET DATA SLICE that will be
PASSED DIRECTLY AS CONTEXT TO THE DIALOGUE AGENT ONLY.

DataContexts are NOT for indicator, pattern, or trend agents.
Those agents operate on internally fetched and cached system data.

Create DataContexts ONLY if the dialogue agent needs:
- raw OHLCV values
- direct price inspection
- historical price answers
- reasoning grounded in price movement
- factual price explanations

DO NOT create DataContexts for:
- indicator computation
- pattern detection
- trend structure
- decision synthesis

If dialogue does NOT require raw market data:
→ data_contexts_required MUST be an empty list

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATA CONTEXT REQUIREMENTS (STRICT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Each DataContext MUST include:
- symbol
- timeframe
- start_datetime
- end_datetime

ALL datetimes MUST:
- be ISO-8601
- include timezone (Asia/Kolkata)
- use CURRENT_DATETIME as reference

If ANY of these cannot be determined:
→ need_clarification = true
→ data_contexts_required MUST be empty

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIMEFRAME RULES (YAHOO FINANCE SAFE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Allowed timeframes ONLY:
["5m", "15m", "1h", "4h", "1d", "1w", "1mo"]

If timeframe is missing:
- Infer ONLY if horizon is explicit
- Otherwise ask for clarification

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HORIZON RULES (SEMANTIC — NOT TIMEFRAME)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
horizon MUST be one of:
- "intraday"
- "swing"
- "long_term"

Horizon represents user INTENT, not data resolution.
DO NOT auto-infer horizon from timeframe.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATE & TIME RULES (NO AMBIGUITY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You MUST compute start_datetime and end_datetime when DataContext is needed.

Rules:
1. If user says "now", "today", "current":
   - end_datetime = CURRENT_DATETIME
   - start_datetime depends on timeframe:
     - 5m / 15m / 1h / 4h → same trading day market hours
     - 1d → 30 days before CURRENT_DATETIME
     - 1w → 90 days before CURRENT_DATETIME
     - 1mo → 365 days before CURRENT_DATETIME

2. If user specifies a single date:
   - Use that date’s market hours

3. If user specifies a date range:
   - Use exactly what is provided

4. If intent = "explain":
   - data_contexts_required MUST be EMPTY
     unless raw price inspection is explicitly requested

NEVER leave datetimes null if DataContext is created.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANALYSIS AGENT ROLES (STRICT SEPARATION)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Allowed agents:
["indicator", "pattern", "trend", "decision", "dialogue"]

Roles:
- indicator / pattern / trend:
  → compute structured analysis
  → NEVER see DataContext

- decision:
  → structured BUY/SELL/HOLD synthesis
  → NEVER speaks to user
  → NEVER sees raw data

- dialogue:
  → user-facing explanation
  → MAY receive DataContext
  → MAY reason over raw OHLCV

The dialogue agent runs ONCE per user query at the very end (except clarify).
Do NOT include "dialogue" inside analyses_required[*].run.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANALYSIS SELECTION RULES (STRICT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
trade:
- quick opinion → ["trend", "decision"]
- full analysis → ["indicator", "pattern", "trend", "decision"]

trend:
- quick → ["trend", "decision"]
- full → ["trend", "indicator", "decision"]

compare:
- quick → ["trend", "decision"]
- full → ["indicator", "trend", "decision"]

price_check:
→ []

explain:
→ []

clarify:
→ []

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLARIFICATION RULES (NO GUESSING)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If ANY of these are missing:
- symbol
- timeframe
- horizon
- date intent

Then:
- need_clarification = true
- clarification_question MUST be specific
- data_contexts_required MUST be empty
- analyses_required MUST be empty

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINAL SELF-CHECK (MANDATORY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Before outputting JSON, ensure:

✓ No analysis performed  
✓ No recommendations made  
✓ No cached data referenced  
✓ All required fields present  
✓ dialogue is last  
✓ Datetimes are timezone aware  
✓ No silent assumptions  

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REMEMBER:
YOU ARE A PLANNER.
NOT AN ANALYST.
NOT AN ADVISOR.
ONLY A ROUTER.

"""

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

                "need_clarification": True,
                "explanation": "I couldn’t understand your request. Could you rephrase it?",
            }

        try:
            planner_output = json.loads(json_match.group(0))
        except Exception:
            return {
                **state,
                "intent": "clarify",

                "need_clarification": True,
                "explanation": "I couldn’t parse your request properly. Could you rephrase it?",
            }

        # --------------------------------------------------
        # 4. Planner output → state update WITH new structure
        # --------------------------------------------------
        updated_state = {**state}

        updated_state["intent"] = planner_output.get("intent", "clarify")
        
        # NEW: Extract data_contexts_required (list of DataContext objects)
        data_contexts_required = planner_output.get("data_contexts_required", [])
        updated_state["data_contexts_required"] = data_contexts_required
        
        # NEW: Extract analyses_required (dict mapping context key → analysis spec)
        analyses_required = planner_output.get("analyses_required", {})
        
        # CRITICAL FIX: Ensure keys in analyses_required match data_contexts_required format
        # LLM may provide shortened keys - we must reconstruct full context keys
        if analyses_required and data_contexts_required:
            fixed_analyses_required = {}
            
            # Build lookup tables
            symbol_to_full_key = {}
            symbol_timeframe_to_full_key = {}
            
            for ctx in data_contexts_required:
                full_key = ctx.get("key", "")
                symbol = ctx.get("symbol", "")
                timeframe = ctx.get("timeframe", "")
                
                if not full_key or not symbol:
                    continue
                
                # Map symbol -> full key
                symbol_to_full_key[symbol] = full_key
                
                # Map symbol|timeframe -> full key
                if timeframe:
                    short_key = f"{symbol}|{timeframe}"
                    symbol_timeframe_to_full_key[short_key] = full_key
            
            # Fix analyses_required keys
            for key, spec in analyses_required.items():
                matched_key = None
                
                # Try exact match first
                if key in [ctx.get("key") for ctx in data_contexts_required]:
                    matched_key = key
                # Try symbol|timeframe match
                elif key in symbol_timeframe_to_full_key:
                    matched_key = symbol_timeframe_to_full_key[key]
                # Try symbol-only match
                elif key in symbol_to_full_key:
                    matched_key = symbol_to_full_key[key]
                else:
                    # Key format not recognized - skip it
                    print(f"⚠️  Planner provided invalid key format: {key} (skipping)")
                    continue
                
                fixed_analyses_required[matched_key] = spec
            
            analyses_required = fixed_analyses_required
        
        # Enforce: dialogue is NOT a per-context analysis
        if isinstance(analyses_required, dict):
            for _, spec in analyses_required.items():
                if not isinstance(spec, dict):
                    continue
                run_list = spec.get("run")
                if isinstance(run_list, list) and "dialogue" in run_list:
                    spec["run"] = [a for a in run_list if a != "dialogue"]
        updated_state["analyses_required"] = analyses_required

        need_clarification = planner_output.get("need_clarification", False)
        updated_state["need_clarification"] = need_clarification

        if need_clarification:
            updated_state["explanation"] = planner_output.get(
                "clarification_question",
                "Could you provide more details?"
            )
            # Ensure no execution happens
            updated_state["data_contexts_required"] = []
            updated_state["analyses_required"] = {}

        # --------------------------------------------------
        # 5. Debug output (KEEP THIS while developing)
        # --------------------------------------------------
        print("\n" + "=" * 60)
        print("PLANNER OUTPUT")
        print("=" * 60)
        print(f"Query               : {user_query}")
        print(f"Intent              : {updated_state['intent']}")
        print(f"Data Contexts       : {len(data_contexts_required)} contexts")
        for ctx in data_contexts_required:
            print(f"  - {ctx.get('key', 'N/A')}")
        print(f"Analyses Required   : {len(analyses_required)} context mappings")
        for key, spec in analyses_required.items():
            # Show full key to verify format
            print(f"  - {key}")
            print(f"    → {spec}")
        print(f"Clarification       : {updated_state['need_clarification']}")
        if updated_state.get("explanation"):
            print(f"Message             : {updated_state['explanation']}")
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
    required_fields = ["intent", "need_clarification", "data_contexts_required", "analyses_required"]
    
    for field in required_fields:
        if field not in planner_output:
            print(f"❌ Missing required field: {field}")
            return False
    
    valid_intents = ["trade", "trend", "compare", "explain", "price_check", "clarify"]
    if planner_output["intent"] not in valid_intents:
        print(f"❌ Invalid intent: {planner_output['intent']}")
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
    1. ALL required fields (symbols, horizon, timeframe, start_datetime, end_datetime) must be complete
    2. No guessing - if information is missing, request clarification
    3. Validate analyses_required is appropriate for intent
    
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
    data_contexts_required = state.get("data_contexts_required", [])
    analyses_required = state.get("analyses_required", {})
    # Derive flat analysis list from analyses_required
    analyses_required_dict = state.get("analyses_required", {})
    required_analyses_set = set()
    for spec in analyses_required_dict.values():
        if isinstance(spec, dict):
            required_analyses_set.update(spec.get("run", []))
    
    # Extract symbols and other info from data_contexts_required
    symbols = [ctx.get("symbol") for ctx in data_contexts_required]
    timeframes = list(set([ctx.get("timeframe") for ctx in data_contexts_required]))
    timeframe = timeframes[0] if timeframes else None
    
    # Extract horizon from analyses_required
    horizons = list(set([spec.get("horizon") for spec in analyses_required.values()]))
    horizon = horizons[0] if horizons else None
    
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
    # RULE 1: MANDATORY - Validate analyses_required completeness
    # These intents require at least one analysis context
    # ========================================================================
    
    if intent in ["trade", "trend", "compare"]:
        # These intents require analyses_required (contexts to analyze)
        # data_contexts_required is OPTIONAL (for dialogue raw data only)
        if not analyses_required:
            return ValidationResult(
                approved=False,
                reason="Missing analysis contexts for analysis intent",
                clarification="Which asset would you like to analyze? Please provide the ticker symbol (e.g., AAPL for Apple, BTC-USD for Bitcoin)."
            )
    
    # ========================================================================
    # RULE 1.5: For price_check - only validate data_contexts_required
    # ========================================================================
    
    if intent == "price_check":
        # Price check only needs data contexts, no analysis required
        if not data_contexts_required:
            return ValidationResult(
                approved=False,
                reason="Missing data contexts for price check",
                clarification="Which asset would you like to check the price for? Please provide the ticker symbol (e.g., AAPL, BTC-USD)."
            )
        
        # Validate each data context completeness
        for ctx in data_contexts_required:
            missing_fields = []
            
            if not ctx.get("symbol"):
                missing_fields.append("symbol")
            if not ctx.get("timeframe"):
                missing_fields.append("timeframe")
            if not ctx.get("start_datetime"):
                missing_fields.append("start_datetime")
            if not ctx.get("end_datetime"):
                missing_fields.append("end_datetime")
            
            if missing_fields:
                return ValidationResult(
                    approved=False,
                    reason=f"Incomplete DataContext: missing {', '.join(missing_fields)}",
                    clarification=f"I need complete information for {ctx.get('symbol', 'the asset')}. Missing: {', '.join(missing_fields)}."
                )
        
        # Price check is valid if we have data contexts
        return ValidationResult(approved=True, reason="Valid price check query")
    
    # ========================================================================
    # RULE 2: Validate data_contexts_required for analysis intents
    # ========================================================================
    
    if intent in ["trade", "trend", "compare"]:
        for ctx in data_contexts_required:
            missing_fields = []
            
            if not ctx.get("symbol"):
                missing_fields.append("symbol")
            if not ctx.get("timeframe"):
                missing_fields.append("timeframe")
            if not ctx.get("start_datetime"):
                missing_fields.append("start_datetime")
            if not ctx.get("end_datetime"):
                missing_fields.append("end_datetime")
            
            if missing_fields:
                return ValidationResult(
                    approved=False,
                    reason=f"Incomplete DataContext: missing {', '.join(missing_fields)}",
                    clarification=f"I need complete information for {ctx.get('symbol', 'the asset')}. Missing: {', '.join(missing_fields)}."
                )
        
        # Validate analyses_required has entries and proper structure
        for ctx_key, spec in analyses_required.items():
            if not spec.get("horizon"):
                return ValidationResult(
                    approved=False,
                    reason=f"Missing horizon in analyses_required for {ctx_key}",
                    clarification="Internal error: missing analysis specification. Please rephrase your query."
                )
            if not spec.get("run") or not isinstance(spec.get("run"), list):
                return ValidationResult(
                    approved=False,
                    reason=f"Missing or invalid 'run' list for {ctx_key}",
                    clarification="Internal error: missing analysis specification. Please rephrase your query."
                )
    
    # ========================================================================
    # RULE 2: Validate horizon is present in all analyses_required entries
    # This prevents unsafe financial advice by ensuring appropriate timeframe selection
    # ========================================================================
    
    if intent in ["trade", "trend", "compare"]:
        for ctx_key, spec in analyses_required.items():
            if not spec.get("horizon"):
                return ValidationResult(
                    approved=False,
                    reason=f"Missing horizon for {ctx_key}",
                    clarification="What trading horizon are you interested in? For example: intraday (minutes to hours), swing trading (days to weeks), or long-term (months)?"
                )
        
        # Check horizon consistency across all contexts
        if horizons and len(horizons) > 1:
            return ValidationResult(
                approved=False,
                reason="Mixed horizons in single query",
                clarification=f"I found multiple trading horizons ({', '.join(horizons)}). Please specify which one you'd like to focus on."
            )
    
    # ========================================================================
    # RULE 3: Comparison intent must have consistent timeframes
    # This prevents unsafe financial advice by ensuring apples-to-apples comparisons
    # ========================================================================
    
    if intent == "compare" and len(data_contexts_required) > 1:
        # Check for consistent timeframe across contexts
        if len(timeframes) > 1:
            return ValidationResult(
                approved=False,
                reason="Mixed timeframes in comparison",
                clarification=f"To compare assets fairly, please use the same timeframe for all. Found: {', '.join(timeframes)}"
            )
    
    # ========================================================================
    # RULE 4: Explain intent should not create new data contexts
    # This prevents re-analysis for clarification questions
    # ========================================================================
    
    if intent == "explain":
        if data_contexts_required:
            # Clear data contexts for explain intent
            state["data_contexts_required"] = []
            state["analyses_required"] = {}
            print(f"ℹ️  Explain intent: cleared data contexts to use cache only")
        
        # No need to set required_analyses - graph will route to dialogue automatically
        
        return ValidationResult(approved=True, reason="Using cached analysis for explanation")
    
    # ========================================================================
    # All validations passed
    # ========================================================================
    
    print(f"✓ System validation passed")
    print(f"  Intent: {intent}")
    print(f"  Data Contexts: {len(data_contexts_required)}")
    print(f"  Analyses Required: {len(analyses_required)} context mappings")
    
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
        state["context_ready"] = False
        
        return state
    
    # Validation passed - proceed to data fetch
    print(f"\n✓ Validation approved: {validation.reason}\n")
    return state
