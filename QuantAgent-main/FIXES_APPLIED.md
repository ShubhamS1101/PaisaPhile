# FIXES APPLIED

## Root Cause: Data Structure Mismatch

The analysis agents were storing data as `"result"` but the decision agent was looking for `"data"`.

### Storage Format (analysis_store_util.py line 757):
```python
analysis_store[store_key][agent_name] = {
    "result": data,        # ← Stored here
    "created_at": ...,
    "fresh_until": ...,
}
```

### Decision Agent Was Looking For (OLD):
```python
indicator_data = indicator_output["data"]  # ← Wrong key!
```

### Decision Agent Fixed (NEW):
```python
indicator_data = indicator_output.get("result", {})  # ← Correct key
```

## Changes Made

### 1. Fixed Decision Agent Format Function
**File:** `agents/decision_agent_new.py`
- Changed `indicator_output["data"]` → `indicator_output.get("result", {})`
- Changed `pattern_output["data"]` → `pattern_output.get("result", {})`  
- Changed `trend_output["data"]` → `trend_output.get("result", {})`
- Removed duplicate print statement

### 2. Fixed Dialogue Agent Metadata Extraction
**File:** `agents/dialogue_agent.py`
- Extract symbol/timeframe/horizon from agent metadata, not top-level entry
- Iterate through agents to find first available metadata

### 3. Added Debug Logging
**File:** `agents/indicator_agent_new.py`
- Added logging for context_key vs store_key
- Show available kline_data keys when lookup fails

**File:** `analysis_store_util.py`
- Added logging for filtering analysis_store
- Show constructed store_keys and lookup results

**File:** `agents/decision_agent_new.py`
- Added logging for upstream analyses check
- Show which agents are present/missing

## Key Format Architecture (This is CORRECT)

### 3-Part Key (Data Context)
Used by: `analyses_required`, `kline_data`
```
{symbol}|{timeframe}|{start}:{end}
```

### 4-Part Key (Analysis Store)  
Used by: `analysis_store`
```
{symbol}|{timeframe}|{start}:{end}|{horizon}
```

The conversion happens automatically in:
- `get_filtered_analysis_store()` - converts 3-part to 4-part for lookup
- All agent nodes - extract horizon from spec and build 4-part key

## Expected Behavior After Fixes

1. ✅ **Indicator analysis will show in responses**
   - Decision agent can now read indicator interpretation
   - Dialogue agent can display indicator results

2. ✅ **Decision confidence will be non-zero**
   - Decision agent can now synthesize from all analyses
   - Proper BUY/SELL/HOLD recommendations

3. ✅ **record.csv will be created in data/ folder**
   - Pattern agent calls `generate_kline_image()`
   - Chart generation creates data/record.csv

4. ✅ **Better debugging**
   - Key mismatches will be logged
   - Missing data will show exactly what's available
