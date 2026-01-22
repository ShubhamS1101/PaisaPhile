# Trading Agentic System - Architecture Summary

## System Overview

Complete conversational agentic trading system with persistent analysis caching, freshness tracking, and automatic decision staleness detection.

## Core Components

### 1. State Management (`agent_state.py`)
**Status: ✅ PRODUCTION READY**

Defines `TradingAdvisorState` with:
- **Per-turn fields**: `user_query`, `intent`, `need_clarification`, `kline_data`, `explanation`
- **Persistent fields**: `analysis_store` (NOT flushed until conversation ends), `conversation_summary`, `user_preferences`
- **Dual contexts**:
  - `analyses_required`: Dict mapping data contexts → analysis specs (indicator/pattern/trend/decision)
  - `data_contexts_required`: Raw data slices passed directly to dialogue

### 2. Planner (`planner_agent.py`)
**Status: ✅ PRODUCTION READY**

- Runs ONCE per query
- Determines intent: `trade`, `trend`, `compare`, `price_check`, `explain`, `clarify`
- Populates `analyses_required` dict with required agents per data context
- Populates `data_contexts_required` for dialogue raw data needs
- **Never** includes `dialogue` in `analyses_required[*].run` (dialogue runs once at end)

### 3. Validator (`planner_agent.py::validate_and_route`)
**Status: ✅ PRODUCTION READY**

- Validates all required fields present
- Ensures horizon consistency across contexts
- Checks timeframe alignment for comparisons
- Blocks execution if incomplete

### 4. Data Fetcher (`graph_main.py::_fetch_data_node`)
**Status: ✅ PRODUCTION READY**

- Fetches OHLCV data for contexts in `analyses_required` (NOT `data_contexts_required`)
- Stores in `kline_data` keyed by `context_key`
- Skips already-fetched data
- Uses yfinance with proper column handling

### 5. Analysis Agents

#### Indicator Agent (`indicator_agent_new.py`)
**Status: ✅ PRODUCTION READY**

- Checks freshness before running (1 candle tolerance)
- Stores results with `ran_at` timestamp
- Updates only indicator field in analysis_store

#### Pattern Agent (`pattern_agent_new.py`)
**Status: ✅ PRODUCTION READY**

- Checks freshness (2-3 candles tolerance)
- Stores results with `ran_at` timestamp
- Updates only pattern field

#### Trend Agent (`trend_agent_new.py`)
**Status: ✅ PRODUCTION READY**

- Checks freshness (% of analysis window)
- Stores results with `ran_at` timestamp
- Updates only trend field

#### Decision Agent (`decision_agent_new.py`)
**Status: ✅ PRODUCTION READY**

- **Automatic staleness detection**: Checks if any upstream agent (indicator/pattern/trend) has `ran_at` newer than decision by MORE than tolerance
- **Tolerance windows**:
  - intraday: 15 minutes
  - swing: 6 hours
  - long_term: 3 days
- Reruns automatically if stale, even if not in `analyses_required[*].run`
- Non-conversational, produces only structured JSON

### 6. Dialogue Agent (`dialogue_agent.py`)
**Status: ✅ PRODUCTION READY**

- Runs ONCE per query at the end
- Receives:
  - `analysis_store`: All analysis results
  - `data_contexts_required`: Raw data slices for direct inspection
- Generates user-facing conversational response

### 7. Memory (`conversation_memory.py`)
**Status: ✅ PRODUCTION READY**

- Updates `conversation_summary` after each turn
- Persistent across queries

### 8. Main Graph (`graph_main.py`)
**Status: ✅ PRODUCTION READY**

Sequential execution flow:
```
START → normalize → planner → validator → fetch → 
indicator → pattern → trend → decision → dialogue → 
memory → cleanup → END
```

Key features:
- `analysis_store` persists (NOT cleared)
- `kline_data` cleared after each turn
- Automatic routing based on intent and validation

## Freshness Logic

### Per-Agent Freshness
Each agent has its own `ran_at` timestamp stored in `analysis_store[store_key][agent_name].metadata.ran_at`.

### Decision Staleness Detection
**Algorithm** (`analysis_store_util.py::decision_is_stale`):
1. Get decision's `ran_at`
2. For each upstream agent (indicator/pattern/trend):
   - Get upstream's `ran_at`
   - Calculate time difference: `upstream_ran_at - decision_ran_at`
   - If difference > tolerance window → decision is stale
3. If stale → rerun decision automatically

**Tolerance Windows**:
- **intraday**: 15 minutes
- **swing**: 6 hours
- **long_term**: 3 days

This ensures decision always reflects latest analysis without redundant reruns.

## Key Format Standards

### Context Key (in `analyses_required`)
Format: `{symbol}|{timeframe}|{start_datetime}:{end_datetime}`

Example: `BEL.NS|15m|2026-01-13T09:00:00+05:30:2026-01-13T16:00:00+05:30`

### Store Key (in `analysis_store`)
Format: `{symbol}|{timeframe}|{start_datetime}:{end_datetime}|{horizon}`

Example: `BEL.NS|15m|2026-01-13T09:00:00+05:30:2026-01-13T16:00:00+05:30|intraday`

## Utilities

### `analysis_store_util.py`
**Status: ✅ PRODUCTION READY**

- `make_analysis_store_key()`: Generate store keys
- `store_agent_output()`: Store agent results with metadata
- `decision_is_stale()`: Check decision freshness with tolerance
- `get_filtered_analysis_store()`: Get relevant analyses for current query

### `freshness_config.py`
**Status: ✅ PRODUCTION READY**

- Tolerance configuration for each agent type
- Datetime utilities (parse, add, compare)
- Timezone handling (Asia/Kolkata)

### `decision_freshness.py`
**Status: ✅ PRODUCTION READY (NEW)**

- Standalone decision freshness checker
- Can be imported for testing/debugging

## Obsolete Files

### ❌ Files to DELETE or IGNORE:

1. **`graph_setup.py`** - Legacy graph with `required_analyses` flat list, outdated routing
2. **`indicator_agent.py`** - Legacy indicator without proper caching
3. **`pattern_agent.py`** - Legacy pattern without proper caching
4. **`trend_agent.py`** - Legacy trend without proper caching
5. **`test_dynamic_routing.py`** - Tests legacy `required_analyses` field
6. **`test_b.py`** - Old test file with legacy state structure
7. **`test_api.py`** - Unclear purpose, likely obsolete

### ⚠️ Files to UPDATE or REVIEW:

1. **`dialogue_agent.py`** - May need updates to properly consume `data_contexts_required`
2. **`web_interface.py`** - Needs update to use `graph_main` instead of `graph_setup`
3. **`trading_graph.py`** - TradingGraph class used for LLM initialization, keep but may simplify

### ✅ Files to KEEP:

- `agent_state.py` - Core state definition
- `planner_agent.py` - Planner with validator
- `*_agent_new.py` - All new agent implementations
- `analysis_store_util.py` - Storage utilities
- `freshness_config.py` - Configuration
- `decision_freshness.py` - Freshness checker
- `conversation_memory.py` - Memory management
- `graph_main.py` - Main orchestration
- `test_planner.py` - Simplified planner test

## Usage Example

```python
from graph_main import create_trading_graph

# Initialize graph
config = {
    "agent_llm_model": "gemini-2.5-flash",
    "graph_llm_model": "gemini-2.5-flash",
    "agent_llm_provider": "gemini",
    "graph_llm_provider": "gemini",
    "agent_llm_temperature": 0.1,
    "graph_llm_temperature": 0.1,
    "gemini_api_key": "YOUR_API_KEY"
}

graph = create_trading_graph(config)

# Run query
state = {
    "user_query": "Should I buy BEL.NS for intraday?",
    "analysis_store": {},  # Persistent across queries
    "conversation_summary": ""  # Persistent across queries
}

result = graph.invoke(state)
print(result["explanation"])  # User-facing response

# Next query - analysis_store persists!
state2 = {
    "user_query": "What about ZOMATO.NS?",
    "analysis_store": result["analysis_store"],  # Reuse!
    "conversation_summary": result["conversation_summary"]
}

result2 = graph.invoke(state2)
```

## Conversation End

To clear `analysis_store` when conversation ends:

```python
# New conversation - fresh state
state_new_conv = {
    "user_query": "Analyze AAPL",
    "analysis_store": {},  # Fresh start
    "conversation_summary": ""
}
```

## Testing

Run planner test:
```bash
python test_planner.py
```

## Key Achievements

✅ **Single source of truth**: Only `analyses_required` (no duplicate `required_analyses`)
✅ **Automatic decision freshness**: No manual planner rules for partial reruns
✅ **Tolerance-based staleness**: Prevents drift-induced redundant execution
✅ **Persistent analysis cache**: Efficient across multi-turn conversations
✅ **Per-agent ran_at tracking**: Fine-grained freshness control
✅ **Dual context handling**: Analysis contexts vs dialogue contexts
✅ **Clean separation**: Dialogue runs once, receives both analysis + raw data

## Next Steps

1. **Test full flow** with `graph_main.py`
2. **Update `web_interface.py`** to use new graph
3. **Delete obsolete files** listed above
4. **Add integration tests** for multi-turn conversations
5. **Monitor decision staleness** in production logs
