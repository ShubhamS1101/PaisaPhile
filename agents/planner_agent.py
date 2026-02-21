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
- which WINDOWS are required (symbol, timeframe, horizon, lookback/date range)
- which analyses must run and in what order
- semantic horizon (intraday | swing | long_term)
- timeframe (data resolution)
- window_type (ROLLING or HISTORICAL)
- lookback duration (for ROLLING) or start/end dates (for HISTORICAL)

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
{{
  "intent": "<intent_type>",
  "need_clarification": <true|false>,

  "windows_required": [
    {{
      "symbol": "<ticker>",
      "timeframe": "<timeframe>",
      "horizon": "<intraday|swing|long_term>",
      "window_type": "<ROLLING|HISTORICAL>",
      "lookback": "<duration, e.g. 4d, 6m, 3y, 100C>",
      "start": "<YYYY-MM-DD, HISTORICAL only>",
      "end": "<YYYY-MM-DD, HISTORICAL only>",
      "run": ["indicator", "pattern", "trend", "decision"]
    }}
  ],

  "clarification_question": "<string|null>"
}}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WINDOW TYPE RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROLLING windows (default):
- Use for "now", "today", "current", "recent", "last N days"
- Require "lookback" (e.g. "4d", "30d", "6m", "3y", "100C")
- Do NOT include "start" or "end"
- The system resolves actual dates at fetch time

HISTORICAL windows:
- Use ONLY when user specifies an exact date range
- Require "start" and "end" as YYYY-MM-DD
- Do NOT include "lookback"

If in doubt, use ROLLING.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LOOKBACK RULES BY TIMEFRAME:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1m  → max lookback: "4d"
5m  → max lookback: "30d"
15m → max lookback: "60d"
1h  → max lookback: "90d"
4h  → max lookback: "1y"
1d  → max lookback: "10y"
1w  → max lookback: "10y"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL RULES FOR windows_required:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- NEVER use placeholder keys like "INTENT_ANALYSIS" or "ANALYSIS_1"
- Each window MUST have symbol, timeframe, horizon, and window_type
- ROLLING windows MUST have lookback
- HISTORICAL windows MUST have start and end
- For price_check intent: set run to [] (empty list) — data only
- For explain intent: windows_required MUST be empty []

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Example 1: Trade query with full analysis
Query: "Should I buy BEL.NS for intraday?"

{{
  "intent": "trade",
  "need_clarification": false,
  "windows_required": [
    {{
      "symbol": "BEL.NS",
      "timeframe": "5m",
      "horizon": "intraday",
      "window_type": "ROLLING",
      "lookback": "4d",
      "run": ["indicator", "pattern", "trend", "decision"]
    }}
  ],
  "clarification_question": null
}}

Example 2: Price check query
Query: "What's the current price of AAPL?"

{{
  "intent": "price_check",
  "need_clarification": false,
  "windows_required": [
    {{
      "symbol": "AAPL",
      "timeframe": "1d",
      "horizon": "intraday",
      "window_type": "ROLLING",
      "lookback": "2d",
      "run": []
    }}
  ],
  "clarification_question": null
}}

Example 3: General greeting
Query: "hi"

{{
  "intent": "clarify",
  "need_clarification": true,
  "windows_required": [],
  "clarification_question": "Hello! How can I assist you with your trading today? You can ask me about buy/sell recommendations, market trends, price checks, or explanations of technical indicators."
}}

Example 4: Follow-up question about existing analysis
Query: "what is the RSI of it?"
CONVERSATION_SUMMARY: "User asked for BEL.NS intraday analysis. System provided HOLD recommendation."

{{
  "intent": "explain",
  "need_clarification": false,
  "windows_required": [],
  "clarification_question": null
}}

Example 5: Historical analysis
Query: "Analyze AAPL from Jan to June 2024"

{{
  "intent": "trade",
  "need_clarification": false,
  "windows_required": [
    {{
      "symbol": "AAPL",
      "timeframe": "1d",
      "horizon": "long_term",
      "window_type": "HISTORICAL",
      "start": "2024-01-01",
      "end": "2024-06-30",
      "run": ["indicator", "trend", "decision"]
    }}
  ],
  "clarification_question": null
}}

Example 6: Long-term swing analysis
Query: "How is INFY for swing trading?"

{{
  "intent": "trade",
  "need_clarification": false,
  "windows_required": [
    {{
      "symbol": "INFY.NS",
      "timeframe": "1d",
      "horizon": "swing",
      "window_type": "ROLLING",
      "lookback": "90d",
      "run": ["indicator", "trend", "decision"]
    }}
  ],
  "clarification_question": null
}}

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
- uses pronouns like "it", "that", "this", "the stock", "the same"
- asks about specific indicator values (RSI, MACD, etc.) without mentioning a symbol
- contains words like "now tell me", "what about", "how about"
- asks clarifying questions about previous analysis

CRITICAL RULE FOR FOLLOW-UP QUESTIONS:
If the query uses "it", "that", or other pronouns referring to previously analyzed assets,
AND does not introduce a new symbol or explicitly request re-analysis,
ALWAYS use intent = "explain" with NO windows_required and NO analyses_required.
The dialogue agent will use cached analysis from conversation context.

Use intent = "trade" / "trend" / "compare" ONLY when:
- a NEW symbol is explicitly introduced in the query
- user explicitly asks for re-analysis ("analyze again", "refresh", "update")
- timeframe or horizon is explicitly changed
- user asks "should I buy/sell" for a NEW or explicitly named symbol

Examples of EXPLAIN intent (use cached data):
- "what is the RSI of it?"
- "now just tell me the RSI of it?"
- "why did you recommend that?"
- "what about the MACD?"
- "explain the indicators"
- "how is the trend?"

Examples of NEW ANALYSIS intent:
- "what about AAPL?" (new symbol)
- "analyze BEL.NS again" (explicit re-analysis)
- "should I buy MSFT?" (new symbol with trade question)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WINDOW SEMANTICS (EXTREMELY IMPORTANT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A window represents a SEMANTIC analysis slot, NOT an exact data slice.

ROLLING windows (the default):
- Represent "latest N units" relative to current time
- Their identity is stable across queries (no timestamps in key)
- Example: "BEL.NS|1d|ROLLING|long_term|3y" is ALWAYS the same slot
- The system resolves actual date ranges at fetch time

HISTORICAL windows:
- Represent a pinned date range the user explicitly asked about
- Example: "AAPL|1d|HISTORICAL|2024-01-01:2024-06-30|long_term"

For price_check/explain intents:
- price_check: use a ROLLING window with run: [] (data only, no analysis)
- explain: windows_required MUST be empty (uses cached data)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WINDOW REQUIREMENTS (STRICT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Each window MUST include:
- symbol
- timeframe
- horizon (intraday | swing | long_term)
- window_type (ROLLING | HISTORICAL)

ROLLING additionally requires:
- lookback (e.g. "4d", "30d", "6m", "3y")

HISTORICAL additionally requires:
- start (YYYY-MM-DD)
- end (YYYY-MM-DD)

If ANY of these cannot be determined:
→ need_clarification = true
→ windows_required MUST be empty

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
DATE & TIME RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
For ROLLING windows, you do NOT compute exact datetimes.
Instead, specify a lookback duration. The system resolves dates.

Rules:
1. If user says "now", "today", "current", "recent":
   Use ROLLING with appropriate lookback for the timeframe
   5m/15m/1h: lookback = "4d" to "30d"
   1d: lookback = "30d" to "1y" depending on horizon
   1w: lookback = "90d" to "2y"

2. If user says "last 3 months", "past year":
   Use ROLLING with lookback = "3m" or "1y"

3. If user specifies exact dates ("from Jan 1 to June 30 2024"):
   Use HISTORICAL with start/end as YYYY-MM-DD

4. If intent = "explain":
   windows_required MUST be EMPTY (use cached analysis)

NEVER leave lookback empty for ROLLING windows.
NEVER leave start/end empty for HISTORICAL windows.

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
- windows_required MUST be empty
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
        # 4. Planner output → state update WITH new window model
        # --------------------------------------------------
        from analysis_store_util import make_window_key

        updated_state = {**state}

        updated_state["intent"] = planner_output.get("intent", "clarify")
        
        # Extract windows_required (list of WindowSpec dicts from LLM)
        windows_required = planner_output.get("windows_required", [])
        updated_state["windows_required"] = windows_required
        
        # Build analyses_required from windows_required
        # Each WindowSpec → window_key → {run: [...], data_needed: true}
        analyses_required = {}
        for spec in windows_required:
            try:
                window_key = make_window_key(spec)
                run_list = spec.get("run", [])
                # Strip "dialogue" from per-window run lists
                run_list = [a for a in run_list if a != "dialogue"]
                analyses_required[window_key] = {
                    "run": run_list,
                    "data_needed": True,
                }
            except (KeyError, ValueError) as e:
                print(f"⚠️  Invalid window spec from planner: {spec} ({e})")
                continue
        
        updated_state["analyses_required"] = analyses_required

        need_clarification = planner_output.get("need_clarification", False)
        updated_state["need_clarification"] = need_clarification

        if need_clarification:
            updated_state["explanation"] = planner_output.get(
                "clarification_question",
                "Could you provide more details?"
            )
            # Ensure no execution happens
            updated_state["windows_required"] = []
            updated_state["analyses_required"] = {}

        # --------------------------------------------------
        # 5. Debug output (KEEP THIS while developing)
        # --------------------------------------------------
        print("\n" + "=" * 60)
        print("PLANNER OUTPUT")
        print("=" * 60)
        print(f"Query               : {user_query}")
        print(f"Intent              : {updated_state['intent']}")
        print(f"Windows Required    : {len(windows_required)} windows")
        for spec in windows_required:
            wtype = spec.get("window_type", "?")
            sym = spec.get("symbol", "?")
            tf = spec.get("timeframe", "?")
            hz = spec.get("horizon", "?")
            lb = spec.get("lookback", "")
            run = spec.get("run", [])
            print(f"  - {sym}|{tf}|{wtype}|{hz} (lookback={lb}) → {run}")
        print(f"Analyses Required   : {len(analyses_required)} window keys")
        for key, spec in analyses_required.items():
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
    required_fields = ["intent", "need_clarification", "windows_required"]
    
    for field in required_fields:
        if field not in planner_output:
            print(f"❌ Missing required field: {field}")
            return False
    
    valid_intents = ["trade", "trend", "compare", "explain", "price_check", "clarify", "historical"]
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
    1. ALL required fields (symbols, horizon, timeframe, window_type) must be complete
    2. No guessing - if information is missing, request clarification
    3. Validate windows_required is appropriate for intent
    
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
    windows_required = state.get("windows_required", [])
    analyses_required = state.get("analyses_required", {})
    
    # Extract info from windows_required
    symbols = [w.get("symbol") for w in windows_required if w.get("symbol")]
    timeframes = list(set([w.get("timeframe") for w in windows_required if w.get("timeframe")]))
    horizons = list(set([w.get("horizon") for w in windows_required if w.get("horizon")]))
    
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
    # RULE 1: Analysis intents require at least one window
    # ========================================================================
    
    if intent in ["trade", "trend", "compare"]:
        if not windows_required:
            return ValidationResult(
                approved=False,
                reason="Missing windows for analysis intent",
                clarification="Which asset would you like to analyze? Please provide the ticker symbol (e.g., AAPL for Apple, BTC-USD for Bitcoin)."
            )
    
    # ========================================================================
    # RULE 1.5: Price check requires at least one window (with empty run list)
    # ========================================================================
    
    if intent == "price_check":
        if not windows_required:
            return ValidationResult(
                approved=False,
                reason="Missing windows for price check",
                clarification="Which asset would you like to check the price for? Please provide the ticker symbol (e.g., AAPL, BTC-USD)."
            )
    
    # ========================================================================
    # RULE 2: Validate each window spec completeness
    # ========================================================================
    
    if intent in ["trade", "trend", "compare", "price_check"]:
        for w in windows_required:
            missing = []
            if not w.get("symbol"):
                missing.append("symbol")
            if not w.get("timeframe"):
                missing.append("timeframe")
            if not w.get("horizon"):
                missing.append("horizon")
            if not w.get("window_type"):
                missing.append("window_type")
            
            wtype = w.get("window_type", "").upper()
            if wtype == "ROLLING" and not w.get("lookback"):
                missing.append("lookback")
            elif wtype == "HISTORICAL":
                if not w.get("start"):
                    missing.append("start")
                if not w.get("end"):
                    missing.append("end")
            
            if missing:
                return ValidationResult(
                    approved=False,
                    reason=f"Incomplete window spec: missing {', '.join(missing)}",
                    clarification=f"I need complete information for {w.get('symbol', 'the asset')}. Missing: {', '.join(missing)}."
                )
    
    # ========================================================================
    # RULE 3: Horizon consistency across all windows
    # ========================================================================
    
    if intent in ["trade", "trend", "compare"] and len(horizons) > 1:
        return ValidationResult(
            approved=False,
            reason="Mixed horizons in single query",
            clarification=f"I found multiple trading horizons ({', '.join(horizons)}). Please specify which one you'd like to focus on."
        )
    
    # ========================================================================
    # RULE 4: Comparison intent must have consistent timeframes
    # ========================================================================
    
    if intent == "compare" and len(windows_required) > 1:
        if len(timeframes) > 1:
            return ValidationResult(
                approved=False,
                reason="Mixed timeframes in comparison",
                clarification=f"To compare assets fairly, please use the same timeframe for all. Found: {', '.join(timeframes)}"
            )
    
    # ========================================================================
    # RULE 5: Explain intent should not create new windows
    # ========================================================================
    
    if intent == "explain":
        if windows_required:
            state["windows_required"] = []
            state["analyses_required"] = {}
            print(f"ℹ️  Explain intent: cleared windows to use cache only")
        
        return ValidationResult(approved=True, reason="Using cached analysis for explanation")
    
    # ========================================================================
    # All validations passed
    # ========================================================================
    
    print(f"✓ System validation passed")
    print(f"  Intent: {intent}")
    print(f"  Windows: {len(windows_required)}")
    print(f"  Analyses Required: {len(analyses_required)} window keys")
    
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
