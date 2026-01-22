# Conversation Summary & Validation System

## Overview

The system now includes **runtime validation** before decision execution and **concise conversation summary updates** after decision completion. These features ensure data integrity and maintain efficient conversation context across multiple turns.

---

## Conversation Summary System

### When It Runs
**AFTER decision agent execution** - Summary is updated only after the decision/explanation is generated.

### Summary Rules (STRICT)

**✅ MUST Capture:**
- Active symbols being analyzed
- Horizons (short-term, medium-term, long-term)
- Decisions made (BUY/SELL/HOLD)
- User intent (advice, explanation, comparison)

**❌ MUST NOT Include:**
- Prices or specific price values
- Indicator values (RSI 65, MACD crossing, etc.)
- Timestamps or dates
- Raw text quotes from user/system

**📏 Format Requirements:**
- Keep concise: **5-10 lines maximum**
- Use bullet points for clarity
- Rewrite (don't append) - LLM rewrites summary each time
- Advisory context only (not a fact source)

### Where Summary Is Used

**✅ Passed to:**
- **Planner agent** - For understanding conversation context when interpreting new queries
- **Decision agent** - For context-aware decision making and explanations

**❌ NEVER Passed to:**
- **Indicator agent** - Pure technical analysis, no conversation context needed
- **Pattern agent** - Pure chart pattern recognition, no conversation context needed
- **Trend agent** - Pure trend analysis, no conversation context needed

### Implementation

Located in [conversation_memory.py](conversation_memory.py):

```python
def update_conversation_summary(state, user_question, system_answer, llm) -> str:
    """
    Update rolling conversation summary AFTER decision execution.
    
    STRICT RULES:
    - 5-10 lines max
    - Capture: symbols, horizons, decisions, user intent only
    - Exclude: prices, indicators, timestamps, raw text
    """
```

**LLM Prompt Structure:**
- Previous summary context
- Latest interaction (intent, symbols, horizon, decision)
- User preferences
- Strict formatting rules
- Example of good summary format

**Guardrail:**
- If LLM output exceeds 10 lines, automatically truncate to first 10 lines

### Example Good Summary

```
- Analyzing BEL.NS for short-term trading
- User seeks buy signals with moderate risk tolerance
- Recent decision: BUY (bullish confluence across all indicators)
- Follow-up: User asking about RSI interpretation
- Preference: Conservative entries with clear stop-loss
```

### Example Bad Summary (Avoided)

```
❌ User asked "Should I buy BEL.NS at 250?"
❌ RSI is at 65.3, MACD crossed bullish at 248.50
❌ On 2026-01-03 at 10:30 AM we recommended BUY
❌ "I think it will go up because the trend is strong"
```

---

## Runtime Validation System

### When It Runs
**BEFORE decision agent execution** in decision mode (intent: advice, trade, compare, trend_decision)

### Validation Checks

#### 1. Analysis Keys Match Current Query

```python
required_keys = state.get("required_analysis_keys", {})
filtered_store = get_filtered_analysis_store(state)

if not filtered_store and required_keys:
    validation_errors.append("❌ No analysis available for required keys")
    validation_failed = True
```

**Purpose:** Ensure the decision agent has the necessary analysis cached in `analysis_store` before attempting to synthesize a decision.

**Failure Action:** Trigger clarification instead of decision.

#### 2. No OHLCV Data in Decision Input

```python
kline_data = state.get("kline_data", None)
if kline_data is not None and len(kline_data) > 0:
    print("⚠️ WARNING: kline_data present in decision input (should be cleared)")
    state["kline_data"] = {}  # Clear it
```

**Purpose:** Decision agent should NEVER see raw OHLCV data. It synthesizes from cached analysis in `analysis_store`, not raw market data.

**Action:** Automatically clear `kline_data` to prevent data pollution.

### Logging Warnings

The system logs warnings (but doesn't fail validation) for:

#### 1. Mixed Symbols

```python
if len(symbols) > 1:
    print(f"⚠️ WARNING: Mixed symbols in decision: {symbols}")
```

**Context:** User asked about multiple symbols simultaneously. Decision may need to address each separately.

**Example:** "Should I buy BEL.NS or RELIANCE.NS?"

#### 2. Mixed Timeframes

```python
if len(timeframes_in_store) > 1:
    print(f"⚠️ WARNING: Mixed timeframes in analysis: {timeframes_in_store}")
```

**Context:** Analysis_store contains entries with different timeframes (e.g., 15m and 1h). Decision may need to clarify which timeframe to prioritize.

**Example:** User first asked about 15m, then about 1h without clarifying scope.

#### 3. Missing Analysis

```python
for key, entry in filtered_store.items():
    missing_fields = []
    if "indicator" not in entry or not entry["indicator"]:
        missing_fields.append("indicator")
    if "pattern" not in entry or not entry["pattern"]:
        missing_fields.append("pattern")
    if "trend" not in entry or not entry["trend"]:
        missing_fields.append("trend")
    
    if missing_fields:
        print(f"⚠️ WARNING: Missing analysis for {key}: {missing_fields}")
        validation_failed = True
```

**Context:** One or more analysis agents haven't completed for a required key. Cannot make informed decision without all three analyses.

**Action:** Triggers validation failure → clarification response.

### Validation Failure Response

When validation fails, the system:

1. **Sets intent to "clarify"**
2. **Builds clarification message** with specific issues
3. **Returns HOLD decision** (safe default)
4. **Lists validation errors** for user transparency

```python
clarification_msg = "I need to complete the analysis before making a decision.\n\n"
clarification_msg += "Issues found:\n"
for error in validation_errors:
    clarification_msg += f"• {error}\n"

return {
    **state,
    "intent": "clarify",
    "explanation": clarification_msg,
    "decision": "HOLD"
}
```

**Example Output:**
```
I need to complete the analysis before making a decision.

Issues found:
• ❌ No analysis available for required keys
• Missing analysis: pattern, trend
```

---

## Flow Diagram

### Normal Flow (Validation Passes)

```
User Query
    ↓
Planner (uses conversation_summary for context)
    ↓
Fetch Data
    ↓
Indicator Agent (NO conversation_summary)
    ↓
Pattern Agent (NO conversation_summary)
    ↓
Trend Agent (NO conversation_summary)
    ↓
[VALIDATION CHECKS] ✓
    ↓
Decision Agent (uses conversation_summary + filtered analysis_store)
    ↓
[UPDATE CONVERSATION SUMMARY]
    ↓
Return to User
```

### Validation Failure Flow

```
User Query
    ↓
Planner
    ↓
Fetch Data
    ↓
Analysis Agents (some fail or incomplete)
    ↓
[VALIDATION CHECKS] ❌
    ↓
Clarification Response (HOLD + error messages)
    ↓
Return to User
```

---

## Implementation Details

### Location in Code

**Validation:** [graph_setup.py](graph_setup.py) lines ~555-620
```python
def run_decision(state: TradingAdvisorState):
    # ... mode determination ...
    
    if intent in decision_mode_intents:
        # VALIDATION BEFORE DECISION MODE
        validation_failed = False
        validation_errors = []
        
        # Check 1: Analysis keys match
        # Check 2: No OHLCV data present
        # Warnings: Mixed symbols/timeframes, missing analysis
        
        if validation_failed:
            return clarification_response
```

**Summary Update:** [graph_setup.py](graph_setup.py) lines ~680-695
```python
# UPDATE CONVERSATION SUMMARY (AFTER DECISION EXECUTION)
if user_question and system_answer:
    state["conversation_summary"] = update_conversation_summary(
        state=state,
        user_question=user_question,
        system_answer=system_answer,
        llm=self.graph_llm
    )
```

**Summary Function:** [conversation_memory.py](conversation_memory.py)
```python
def update_conversation_summary(state, user_question, system_answer, llm) -> str:
    # Extract key context (intent, symbols, horizon, decision)
    # Build LLM prompt with strict rules
    # Call LLM to rewrite summary
    # Truncate if > 10 lines
    return new_summary
```

---

## Benefits

### 1. Data Integrity
✅ Decision agent never sees raw OHLCV data (only synthesized analysis)
✅ Validation ensures all required analysis is complete before decision
✅ Prevents partial or corrupted decision inputs

### 2. Efficient Context Management
✅ Concise summaries (5-10 lines) prevent token bloat
✅ Captures only high-level context, not granular details
✅ Enables long conversations without exponential context growth

### 3. Separation of Concerns
✅ Analysis agents: Pure technical computation (no conversation bias)
✅ Decision agent: Context-aware synthesis (uses conversation history)
✅ Clear boundaries prevent contamination

### 4. Transparency
✅ Validation failures explicitly state what's missing
✅ Warnings logged for mixed contexts (symbols/timeframes)
✅ Users understand why HOLD decision was recommended

### 5. Safety
✅ Default to HOLD on validation failure (conservative)
✅ Clarification instead of incorrect decision
✅ Prevents decisions based on incomplete analysis

---

## Testing Checklist

- [ ] Conversation summary updates after decision
- [ ] Summary stays under 10 lines
- [ ] Summary excludes prices/indicators/timestamps
- [ ] Summary includes symbols/horizons/decisions/intent
- [ ] Analysis agents don't receive conversation_summary
- [ ] Planner receives conversation_summary
- [ ] Decision agent receives conversation_summary
- [ ] Validation catches missing analysis
- [ ] Validation catches OHLCV data in decision input
- [ ] Validation triggers clarification on failure
- [ ] Warnings logged for mixed symbols
- [ ] Warnings logged for mixed timeframes
- [ ] Warnings logged for missing analysis fields
- [ ] Multi-turn conversation maintains context
- [ ] Summary rewritten (not appended) each turn

---

## Example Scenarios

### Scenario 1: Complete Analysis → Valid Decision

```
Turn 1:
User: "Should I buy BEL.NS?"
→ Planner interprets (no summary yet)
→ Fetch data
→ Run indicator/pattern/trend agents
→ Validation: ✓ All analysis present
→ Decision: BUY (75% confidence)
→ Summary updated: "Analyzing BEL.NS for short-term trading. Decision: BUY (bullish signals)."

Turn 2:
User: "Why?"
→ Planner uses summary (knows context: BEL.NS, BUY decision)
→ Explanation mode (no new analysis)
→ Decision agent reads cached decision from analysis_store
→ Response: "I recommended BUY because..."
→ Summary updated: "...Follow-up: User asking about BUY reasoning."
```

### Scenario 2: Incomplete Analysis → Validation Failure

```
Turn 1:
User: "Should I buy XYZ?"
→ Planner interprets
→ Fetch data
→ Indicator agent completes
→ Pattern agent fails (network error)
→ Trend agent completes
→ Validation: ❌ Missing analysis for pattern
→ Clarification: "I need to complete the analysis before making a decision. Issues: Missing analysis: pattern"
→ Decision: HOLD
→ Summary updated: "User asked about XYZ. Analysis incomplete (pattern failed)."
```

### Scenario 3: Mixed Symbols → Warning

```
User: "Should I buy BEL.NS or RELIANCE.NS?"
→ Planner: symbols = ["BEL.NS", "RELIANCE.NS"]
→ Fetch data for both
→ Run analysis for both
→ Validation: ⚠️ WARNING: Mixed symbols in decision: ['BEL.NS', 'RELIANCE.NS']
→ Validation: ✓ Passes (warning only)
→ Decision: Compares both symbols
→ Summary: "Comparing BEL.NS vs RELIANCE.NS for short-term trading."
```

---

## Summary

The validation and summary system provides:

✅ **Data integrity** - Validation ensures clean inputs to decision agent
✅ **Efficient context** - Concise summaries prevent token bloat
✅ **Safety** - Default to HOLD on validation failure
✅ **Transparency** - Explicit error messages when validation fails
✅ **Separation** - Analysis agents stay pure, decision agents get context
✅ **Multi-turn support** - Summary enables natural conversation flow

This architecture enables robust, context-aware trading advice while maintaining clean separation between technical analysis and decision synthesis.
