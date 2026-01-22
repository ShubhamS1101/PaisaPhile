# LLM Configuration Guide

## Overview
The system now uses **three separate LLM configurations** to optimize cost and performance:

1. **Agent LLM** - Cheap/Fast operations
2. **Graph LLM** - Reasoning/Vision operations
3. **Conversation Summary LLM** - Moderate summarization

---

## Configuration Fields

### In `default_config.py`:

```python
DEFAULT_CONFIG = {
    # Agent LLM: For cheap/fast operations
    "agent_llm_model": "gpt-4o-mini",
    "agent_llm_provider": "openai",
    "agent_llm_temperature": 0.1,
    
    # Graph LLM: For reasoning/vision operations
    "graph_llm_model": "gpt-4o",
    "graph_llm_provider": "openai",
    "graph_llm_temperature": 0.1,
    
    # Conversation Summary LLM: For summarization
    "conversation_summary_llm_model": "gpt-4o-mini",
    "conversation_summary_llm_provider": "openai",
    "conversation_summary_llm_temperature": 0.3,
    
    # API Keys
    "api_key": "sk-...",
    "anthropic_api_key": "sk-...",
    "qwen_api_key": "sk-...",
    "gemini_api_key": "...",
    "conversation_summary_api_key": "",  # Optional, falls back to api_key
}
```

---

## LLM Assignments by Agent

### **1. AGENT LLM** (Cheap - gpt-4o-mini / claude-haiku / gemini-flash)

**Properties:**
- **Type:** Cheap/Fast
- **Purpose:** Text processing, routing, formatting
- **Reasoning Level:** Low to Moderate
- **Cost:** ~$0.15-0.60 per 1M tokens

**Agents Using Agent LLM:**

| Agent | File | Purpose |
|-------|------|---------|
| **Planner Agent** | `agents/planner_agent.py` | Query interpretation & routing - parses user intent, determines required analyses, creates execution plan |
| **Dialogue Agent** | `agents/dialogue_agent.py` | User-facing explanations - formats responses, explains analysis in natural language |
| **Decision Agent** | `agents/decision_agent_new.py` | Structured decision synthesis - combines analysis results into trading decisions (no heavy computation) |

**Why Cheap LLM?**
- These agents perform **structured tasks** with well-defined prompts
- No complex reasoning or multi-step analysis required
- High-frequency operations (run on every query)
- Output is deterministic formatting and text transformation

---

### **2. GRAPH LLM** (Reasoning - gpt-4o / claude-sonnet / gemini-pro)

**Properties:**
- **Type:** Reasoning + Vision
- **Purpose:** Complex analysis, chart interpretation, multi-step reasoning
- **Reasoning Level:** High
- **Cost:** ~$2.50-15 per 1M tokens

**Agents Using Graph LLM:**

| Agent | File | Purpose |
|-------|------|---------|
| **Indicator Agent** | `agents/indicator_agent_new.py` | Technical indicator calculations & interpretation - computes RSI, MACD, ROC, Stochastic, Williams %R |
| **Pattern Agent** | `agents/pattern_agent_new.py` | Chart pattern recognition - identifies candlestick patterns, support/resistance, uses vision for chart analysis |
| **Trend Agent** | `agents/trend_agent_new.py` | Trend identification & analysis - determines market direction, uses vision to analyze trend charts |

**Why Reasoning LLM?**
- These agents perform **actual market analysis**
- Require **vision capabilities** for chart interpretation
- Need **multi-step reasoning** for technical analysis
- Low-frequency operations (cached with freshness tracking)
- Critical for trading decision quality

---

### **3. CONVERSATION SUMMARY LLM** (Moderate - gpt-4o-mini / claude-haiku)

**Properties:**
- **Type:** Moderate/Cheap
- **Purpose:** Context compression, conversation summarization
- **Reasoning Level:** Moderate
- **Cost:** ~$0.15-0.60 per 1M tokens
- **Temperature:** 0.3 (slightly higher for creative summarization)

**Module Using Conversation Summary LLM:**

| Module | File | Purpose |
|--------|------|---------|
| **Conversation Memory** | `agents/conversation_memory.py` | Rolling conversation summary - maintains concise 5-10 line summary of conversation state |

**Why Moderate LLM?**
- Needs **good comprehension** and summarization skills
- Runs **frequently** (after each user interaction)
- Should be **cheap** to minimize ongoing costs
- Can use same tier as Agent LLM (gpt-4o-mini is sufficient)
- Higher temperature (0.3) for more natural summarization

---

## Cost Optimization

### Expected Cost Breakdown:

| LLM Type | Usage Frequency | Cost/1M Tokens | % of Total Cost |
|----------|----------------|----------------|-----------------|
| **Agent LLM** | High (every query) | $0.15-0.60 | ~15-20% |
| **Graph LLM** | Low (cached) | $2.50-15 | ~70-75% |
| **Summary LLM** | High (every query) | $0.15-0.60 | ~5-10% |

### Cost Savings:
- **Before:** All agents used Graph LLM (~100% expensive operations)
- **After:** Only 3 analysis agents use Graph LLM (~30% expensive operations)
- **Estimated Savings:** 70-80% reduction in LLM costs

---

## Recommended Model Configurations

### **Budget Configuration** (~$0.50 per 100 queries)
```python
"agent_llm_model": "gpt-4o-mini"
"graph_llm_model": "gpt-4o-mini"  # Use mini for everything
"conversation_summary_llm_model": "gpt-4o-mini"
```

### **Balanced Configuration** (~$2 per 100 queries)
```python
"agent_llm_model": "gpt-4o-mini"
"graph_llm_model": "gpt-4o"  # Use reasoning model only for analysis
"conversation_summary_llm_model": "gpt-4o-mini"
```

### **Premium Configuration** (~$5 per 100 queries)
```python
"agent_llm_model": "gpt-4o"
"graph_llm_model": "gpt-4o"
"conversation_summary_llm_model": "gpt-4o-mini"
```

### **Anthropic Alternative**
```python
"agent_llm_provider": "anthropic"
"agent_llm_model": "claude-3-5-haiku-20241022"
"graph_llm_provider": "anthropic"
"graph_llm_model": "claude-3-5-sonnet-20241022"
"conversation_summary_llm_provider": "anthropic"
"conversation_summary_llm_model": "claude-3-5-haiku-20241022"
```

---

## Implementation Details

### Files Modified:
1. `default_config.py` - Added conversation_summary_llm fields
2. `trading_graph.py` - Initialize conversation_summary_llm
3. `graph_setup_new.py` - Pass conversation_summary_llm to memory node
4. `graph_main.py` - Updated TradingGraphV2 constructor
5. `agents/conversation_memory.py` - Accept llm parameter

### Backward Compatibility:
- All existing configs will work with defaults
- `conversation_summary_api_key` is optional (falls back to `api_key`)
- No breaking changes to existing code

---

## Testing Recommendations

1. **Verify LLM Assignment:**
   - Check logs to ensure correct LLM is used by each agent
   - Monitor API calls to confirm cost reduction

2. **Quality Testing:**
   - Compare analysis quality with different graph_llm models
   - Ensure conversation summaries remain concise and accurate

3. **Cost Monitoring:**
   - Track token usage per agent type
   - Measure actual cost savings vs. expected

---

## Summary

| Component | LLM Type | Model Example | Properties | Why |
|-----------|----------|---------------|------------|-----|
| **Planner** | Agent | gpt-4o-mini | Cheap, Fast | Simple routing/parsing |
| **Dialogue** | Agent | gpt-4o-mini | Cheap, Fast | Text formatting |
| **Decision** | Agent | gpt-4o-mini | Cheap, Fast | Structured synthesis |
| **Indicator** | Graph | gpt-4o | Reasoning, Vision | Technical calculations |
| **Pattern** | Graph | gpt-4o | Reasoning, Vision | Chart pattern analysis |
| **Trend** | Graph | gpt-4o | Reasoning, Vision | Trend identification |
| **Memory** | Summary | gpt-4o-mini | Moderate, Cheap | Conversation compression |

**Result:** 70-80% cost reduction while maintaining analysis quality where it matters most.
