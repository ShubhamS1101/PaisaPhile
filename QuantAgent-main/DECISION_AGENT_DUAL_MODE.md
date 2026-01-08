# Decision Agent: Dual-Mode Architecture

## Overview

The decision agent now supports **two operational modes** based on user intent, fully integrated with the `analysis_store` for efficient caching and retrieval.

---

## Mode 1: Decision Mode

**Triggered when:** `intent in ["advice", "trade", "compare", "trend_decision"]`

### Purpose
Generate **BUY/SELL/HOLD** trading recommendations by synthesizing cached analysis from `analysis_store`.

### Inputs
- `user_query`: Current user question
- `intent`: Query intent (advice, trade, etc.)
- `mode`: Execution mode
- `conversation_summary`: Historical conversation context
- `user_preferences`: User's trading preferences
- **FILTERED `analysis_store` entries** relevant to current query (via `required_analysis_keys`)

### Outputs
- `decision`: BUY | SELL | HOLD
- `explanation`: Detailed reasoning with confidence, risk warning, timeframe notes
- **Caches decision back to `analysis_store`** for future reference

### Key Features
1. **Cache-First**: Uses only pre-computed analysis from `analysis_store`
2. **Filtered Context**: Only analyzes entries relevant to current query (via `get_filtered_analysis_store()`)
3. **Multi-Symbol Support**: Can synthesize decisions across multiple symbols/timeframes
4. **Conservative Bias**: Prefers HOLD when signals conflict or are weak
5. **Decision Persistence**: Stores decision in `analysis_store[key]["decision"]` for future explanation queries

### Example Flow
```
User: "Should I buy BEL.NS?"
→ Intent: "advice"
→ Mode: DECISION
→ Retrieves from analysis_store:
  - indicator: {"report": "RSI 65, MACD bullish...", "messages": [...]}
  - pattern: {"report": "Bull flag forming...", "image": "...", "messages": [...]}
  - trend: {"report": "Uptrend confirmed...", "image": "...", "messages": [...]}
→ Synthesizes: decision="BUY", confidence="75%", reasoning=[...]
→ Stores back to analysis_store[key]["decision"] = {...}
→ Returns: "Decision: BUY (75% confidence)..."
```

---

## Mode 2: Explanation Mode

**Triggered when:** `intent in ["explain", "chat", "why", "price_check", "historical"]`

### Purpose
Answer user questions conversationally using **ONLY cached analysis** from `analysis_store`. **NO new analysis is triggered.**

### Inputs
- `user_query`: Current follow-up question
- `intent`: Query intent (explain, chat, why, etc.)
- `mode`: Execution mode
- `conversation_summary`: Historical conversation context
- `user_preferences`: User's trading preferences
- **Cached decisions and analysis** from `analysis_store`

### Outputs
- `explanation`: Conversational response based on cached data

### Key Features
1. **Cache-Only**: NEVER triggers new analysis or data fetching
2. **Decision-Aware**: Can reference previous decisions stored in `analysis_store[key]["decision"]`
3. **Conversational**: Engages with user questions naturally ("why?", "what about RSI?")
4. **Context-Rich**: Uses conversation summary and user preferences for personalized responses
5. **Multi-Turn Efficient**: Fast responses using pre-cached data

### Forbidden Actions
- ❌ Fetching new market data
- ❌ Calling indicator/pattern/trend agents
- ❌ Recomputing analysis
- ❌ Modifying market context

### Example Flow
```
User: "Should I buy BEL.NS?" → [Decision Mode runs, caches result]
User: "Why?"
→ Intent: "explain"
→ Mode: EXPLANATION
→ Retrieves from analysis_store:
  - decision: {"decision": "BUY", "confidence": "75%", "reasoning": [...]}
  - indicator: {...cached report...}
  - pattern: {...cached report...}
  - trend: {...cached report...}
→ Synthesizes: "I recommended BUY because RSI shows bullish momentum at 65..."
→ NO new computation, instant response

User: "What about the pattern?"
→ Intent: "explain"
→ Mode: EXPLANATION
→ Uses cached pattern report: "The pattern analysis identified a bull flag formation..."
```

---

## Implementation Details

### Helper Functions

#### `get_filtered_analysis_store(state)`
- Filters `analysis_store` to only entries relevant to current query
- Uses `required_analysis_keys` to determine relevance
- Returns entire store if no specific keys requested (explanation mode)

#### `format_analysis_for_llm(filtered_store)`
- Converts filtered store entries into readable text
- Combines multi-symbol/timeframe analyses
- Returns formatted strings for indicator, pattern, trend reports

### Integration with analysis_store

**analysis_store Structure:**
```python
{
  "BEL.NS|15m|2026-01-01:2026-01-02": {
    "symbol": "BEL.NS",
    "timeframe": "15m",
    "start_date": "2026-01-01",
    "end_date": "2026-01-02",
    "indicator": {
      "report": "RSI 65, MACD bullish crossover...",
      "messages": [...]
    },
    "pattern": {
      "report": "Bull flag forming at resistance...",
      "image": "base64...",
      "messages": [...]
    },
    "trend": {
      "report": "Strong uptrend, higher highs/lows...",
      "image": "base64...",
      "messages": [...]
    },
    "decision": {  # ← Added by decision agent
      "decision": "BUY",
      "confidence": "75%",
      "reasoning": ["RSI bullish", "Pattern confirmed"],
      "risk_warning": "Market volatility risk",
      "timeframe_note": "Hold for 2-3 days"
    },
    "metadata": {
      "horizon": "short-term",
      "created_at": "2026-01-03T10:30:00Z"
    }
  }
}
```

### Decision Caching
When Decision Mode generates a recommendation, it:
1. Creates a decision entry with full details
2. Stores it to `analysis_store[key]["decision"]` using `update_analysis_field()`
3. Makes decision available for future explanation queries

---

## Benefits

### Multi-Turn Efficiency
```
Turn 1: "Should I buy BEL.NS?" 
  → Full analysis + decision (3 LLM calls + 1 API fetch)

Turn 2: "Why?"
  → Instant explanation using cached decision (1 LLM call, no fetch)

Turn 3: "What about RSI?"
  → Instant explanation using cached indicator report (1 LLM call, no fetch)

Turn 4: "Should I buy BEL.NS on 1h timeframe?"
  → New key → Full analysis + decision (different timeframe)
```

### Conservative Trading
- Default decision: **HOLD** (not "NO TRADE")
- Requires confluence across all three analyses
- Mandatory risk warnings
- Realistic confidence estimates

### Conversation Context
- Uses `conversation_summary` to maintain continuity
- Respects `user_preferences` for personalized advice
- Acknowledges user challenges/questions in explanation mode

---

## Router Logic

The decision agent router (in `graph_setup.py`) determines mode based on intent:

```python
decision_mode_intents = ["advice", "trade", "compare", "trend_decision"]
explanation_mode_intents = ["explain", "chat", "why", "price_check", "historical"]

if intent in decision_mode_intents:
    → Decision Mode (synthesize cached analysis → BUY/SELL/HOLD)
elif intent in explanation_mode_intents:
    → Explanation Mode (conversational response using cache)
else:
    → Default to Explanation Mode
```

---

## Migration Notes

### Changes from Legacy
- **NO TRADE** → **HOLD** (more standard trading terminology)
- Reads from `analysis_store` instead of `state["indicator_report"]`, etc.
- Caches decision back to `analysis_store` for persistence
- Supports filtered context (only relevant symbols/timeframes)
- Multi-turn conversation support via cached decisions

### Backward Compatibility
- Legacy fields (`indicator_report`, `pattern_report`, etc.) still updated by agent wrappers
- Old code can still read from state during migration
- Gradual migration path: both systems work simultaneously

---

## Testing Checklist

- [ ] Decision mode with single symbol
- [ ] Decision mode with multiple symbols
- [ ] Decision mode with different timeframes
- [ ] Explanation mode after decision ("why?")
- [ ] Explanation mode with specific question ("what about RSI?")
- [ ] Multi-turn conversation across different contexts
- [ ] Cache hit behavior (no re-computation)
- [ ] Cache miss behavior (new key requires new analysis)
- [ ] Decision persistence in analysis_store
- [ ] Filtered store retrieval (only relevant keys)

---

## Summary

The dual-mode decision agent provides:
✅ **Efficient multi-turn conversations** (explanation mode uses cached data)
✅ **Granular caching** (key-based storage by symbol/timeframe/dates)
✅ **Decision persistence** (decisions cached for future reference)
✅ **Conservative trading** (HOLD when uncertain)
✅ **Context-aware responses** (conversation history + user preferences)
✅ **Clean separation** (decision vs explanation logic isolated)

This architecture enables natural conversations like:
```
"Should I buy X?" → [Full analysis]
"Why?" → [Quick explanation]
"What about Y?" → [Different symbol, new analysis]
"Explain the RSI" → [Quick explanation from cache]
```
