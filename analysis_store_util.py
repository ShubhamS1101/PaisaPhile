"""
Utility functions for managing the analysis_store and per-query execution fields in TradingAdvisorState.

The analysis_store is a persistent cache for all analysis results with per-agent freshness tracking.

Key Format: "{symbol}|{timeframe}|{start_datetime}:{end_datetime}|{horizon}"
Example: "BTC|15m|2026-01-12T09:00+05:30:2026-01-12T12:00+05:30|intraday"

Each agent output has its own freshness window:
- Indicator: Most sensitive (1 candle tolerance)
- Pattern: Moderately sensitive (2-3 candles)
- Trend: Least sensitive (% of analysis window)
- Decision: Derived (invalidated only by upstream changes)
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from freshness_config import (
    INDICATOR_TOLERANCE,
    PATTERN_TOLERANCE_INTRADAY,
    PATTERN_TOLERANCE_SWING,
    PATTERN_TOLERANCE_LONG_TERM,
    TREND_TOLERANCE,
    get_current_time_iso,
    parse_iso_datetime,
    add_minutes,
    add_days,
    add_weeks,
    calculate_time_delta_minutes,
    calculate_time_delta_days,
    is_time_before,
    is_time_after
)


# ============================================================================
# NOTE ON DATA SHAPE
# ============================================================================
# We keep analysis_store entries compatible with agent_state.AgentOutput:
#   AgentOutput = {
#     "result": {...},
#     "created_at": <iso>,
#     "fresh_until": <iso|None>,
#     "model_version": <str>
#   }
#
# For convenience and backwards/interop with earlier drafts, we also include
# a redundant "metadata" dict inside the stored AgentOutput that mirrors
# created_at/fresh_until/timeframe/agent. This DOES NOT require changes to
# agent_state.py because TypedDict is not runtime-enforced.


# ============================================================================
# PER-QUERY EXECUTION FIELD MANAGEMENT
# These fields are RESET every turn and guide routing logic only
# ============================================================================

def reset_execution_fields(state: Dict[str, Any]) -> None:
    """
    Reset per-query execution fields at the start of a new user query.
    
    This should be called by the planner before processing a new query.
    
    Fields reset:
    - user_query (cleared after planning)
    - data_required_keys (cleared to [])
    - required_analysis_keys (cleared to {})
    
    Args:
        state: TradingAdvisorState dict (modified in-place)
    """
    state["data_required_keys"] = []
    state["required_analysis_keys"] = {}


def populate_execution_keys(
    state: Dict[str, Any],
    symbols: List[str],
    timeframe: str,
    start_date: str,
    end_date: str,
    required_analyses: List[str]
) -> None:
    """
    Populate execution keys based on planner output.
    
    This generates the data_required_keys and required_analysis_keys
    that will guide the router execution.
    
    Args:
        state: TradingAdvisorState dict (modified in-place)
        symbols: List of symbols to analyze
        timeframe: Chart timeframe
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        required_analyses: List of analyses needed ["indicator", "pattern", "trend", "decision"]
    """
    data_keys = []
    analysis_keys = {}
    
    for symbol in symbols:
        key = make_analysis_key(symbol, timeframe, start_date, end_date)
        data_keys.append(key)
        analysis_keys[key] = required_analyses.copy()
    
    state["data_required_keys"] = data_keys
    state["required_analysis_keys"] = analysis_keys


def get_pending_analyses(state: Dict[str, Any], key: str) -> List[str]:
    """
    Get the list of analyses that still need to run for a given key.
    
    Checks both required_analysis_keys (what's needed this turn) and
    analysis_store (what's already cached) to determine what's pending.
    
    Args:
        state: TradingAdvisorState dict
        key: Analysis key
        
    Returns:
        List of pending analysis types (e.g., ["indicator", "pattern"])
        Empty list if all required analyses are cached
    """
    required = state.get("required_analysis_keys", {}).get(key, [])
    if not required:
        return []
    
    analysis_store = state.get("analysis_store", {})
    if key not in analysis_store:
        return required
    
    entry = analysis_store[key]
    pending = []
    
    for analysis_type in required:
        if analysis_type == "decision":
            # Decision always runs (it synthesizes results)
            pending.append(analysis_type)
        elif entry.get(analysis_type) is None:
            # Analysis not cached
            pending.append(analysis_type)
    
    return pending


def mark_analysis_complete(state: Dict[str, Any], key: str, analysis_type: str) -> None:
    """
    Mark an analysis as complete for the current query by removing it from required_analysis_keys.
    
    This is used by the router to track progress within a single query execution.
    Note: This does NOT update analysis_store - that's done by agents.
    
    Args:
        state: TradingAdvisorState dict (modified in-place)
        key: Analysis key
        analysis_type: Type of analysis completed ("indicator", "pattern", "trend", "decision")
    """
    required_keys = state.get("required_analysis_keys", {})
    if key in required_keys:
        if analysis_type in required_keys[key]:
            required_keys[key].remove(analysis_type)


def has_pending_work(state: Dict[str, Any]) -> bool:
    """
    Check if there's any pending analysis work for the current query.
    
    Returns:
        True if any key has pending analyses, False if all work is complete
    """
    required_keys = state.get("required_analysis_keys", {})
    for key, analyses in required_keys.items():
        if analyses:  # If list is non-empty, there's pending work
            return True
    return False


# ============================================================================
# ANALYSIS STORE MANAGEMENT (PERSISTENT ACROSS TURNS)
# ============================================================================

def get_filtered_analysis_store(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Extract ONLY analysis_store entries relevant to the current query.
    
    Uses required_analysis_keys to determine which cached analyses are relevant.
    If required_analysis_keys is empty, returns entire analysis_store.
    
    Args:
        state: Trading advisor state with analysis_store and required_analysis_keys
        
    Returns:
        Filtered dict of {key: analysis_entry} relevant to current query
    """
    analysis_store = state.get("analysis_store", {})

    # NEW ARCH: filter using analyses_required (DataContext.key -> {horizon, run})
    analyses_required = state.get("analyses_required", {})
    if analyses_required:
        filtered: Dict[str, Dict[str, Any]] = {}
        print(f"\n🔍 Filtering analysis_store:")
        print(f"   analyses_required keys: {list(analyses_required.keys())}")
        print(f"   analysis_store keys: {list(analysis_store.keys())}")
        
        for ctx_key, spec in analyses_required.items():
            try:
                # ctx_key: "{symbol}|{timeframe}|{start}:{end}"
                # Note: datetimes contain colons (e.g., 2026-01-13T10:30:00+05:30)
                parts = ctx_key.split("|")
                if len(parts) != 3:
                    continue
                symbol = parts[0]
                timeframe = parts[1]
                datetime_range = parts[2]
                
                # Parse datetime range with timezone-aware regex
                import re
                match = re.match(r'^(.+?[+-]\d{2}:\d{2}):(.+)$', datetime_range)
                if not match:
                    match = re.match(r'^(.+?Z):(.+)$', datetime_range)
                if not match:
                    continue
                start_datetime = match.group(1)
                end_datetime = match.group(2)
                
                horizon = spec.get("horizon")
                if not horizon:
                    continue
                store_key = make_analysis_store_key(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_datetime=start_datetime,
                    end_datetime=end_datetime,
                    horizon=horizon,
                )
                print(f"   Constructed store_key: {store_key}")
                if store_key in analysis_store:
                    filtered[store_key] = analysis_store[store_key]
                    print(f"   ✅ Found in analysis_store")
                else:
                    print(f"   ❌ Not found in analysis_store")
            except Exception as e:
                print(f"   ⚠️ Error processing ctx_key {ctx_key}: {e}")
                continue
        
        print(f"   Filtered store has {len(filtered)} entries\n")
        return filtered

    # LEGACY ARCH: filter using required_analysis_keys if present
    required_keys = state.get("required_analysis_keys", {})
    if required_keys:
        filtered = {}
        for key in required_keys.keys():
            if key in analysis_store:
                filtered[key] = analysis_store[key]
        return filtered

    # If no specific keys requested, return all
    return analysis_store


def make_analysis_key(symbol: str, timeframe: str, start_date: str, end_date: str) -> str:
    """
    Generate a unique key for the analysis_store.
    
    Args:
        symbol: Ticker symbol (e.g., "BEL.NS")
        timeframe: Chart timeframe (e.g., "15m", "1h")
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        
    Returns:
        Unique key string: "{symbol}|{timeframe}|{start_date}:{end_date}"
    """
    return f"{symbol}|{timeframe}|{start_date}:{end_date}"


def get_analysis_entry(
    analysis_store: Dict[str, Dict[str, Any]],
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str
) -> Optional[Dict[str, Any]]:
    """
    Retrieve an analysis entry from the store.
    
    Returns None if the entry doesn't exist.
    """
    key = make_analysis_key(symbol, timeframe, start_date, end_date)
    return analysis_store.get(key)


def init_analysis_entry(
    analysis_store: Dict[str, Dict[str, Any]],
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    horizon: str
) -> str:
    """
    Initialize a new analysis entry in the store if it doesn't exist.
    
    Returns the key for the created/existing entry.
    """
    key = make_analysis_key(symbol, timeframe, start_date, end_date)
    
    if key not in analysis_store:
        analysis_store[key] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "indicator": None,
            "pattern": None,
            "trend": None,
            "decision": None,
            "metadata": {
                "horizon": horizon,
                "created_at": datetime.utcnow().isoformat()
            }
        }
    
    return key


def update_analysis_field(
    analysis_store: Dict[str, Dict[str, Any]],
    key: str,
    field: str,
    data: Any
) -> None:
    """
    Update a specific field in an existing analysis entry.
    
    Args:
        analysis_store: The analysis store dict
        key: The analysis key (from make_analysis_key)
        field: One of "indicator", "pattern", "trend", "decision"
        data: The data to store in this field
        
    Raises:
        KeyError: If the key doesn't exist in the store
        ValueError: If the field name is invalid
    """
    valid_fields = {"indicator", "pattern", "trend", "decision"}
    if field not in valid_fields:
        raise ValueError(f"Invalid field '{field}'. Must be one of {valid_fields}")
    
    if key not in analysis_store:
        raise KeyError(f"Analysis key '{key}' not found in store")
    
    analysis_store[key][field] = data


def has_field(
    analysis_store: Dict[str, Dict[str, Any]],
    key: str,
    field: str
) -> bool:
    """
    Check if a specific field has been populated in an analysis entry.
    
    Returns:
        True if the field exists and is not None, False otherwise
    """
    if key not in analysis_store:
        return False
    
    entry = analysis_store[key]
    return entry.get(field) is not None


def get_field(
    analysis_store: Dict[str, Dict[str, Any]],
    key: str,
    field: str
) -> Optional[Any]:
    """
    Get a specific field from an analysis entry.
    
    Returns:
        The field value if it exists, None otherwise
    """
    if key not in analysis_store:
        return None
    
    return analysis_store[key].get(field)


def clear_analysis_store(analysis_store: Dict[str, Dict[str, Any]]) -> None:
    """
    Clear all entries from the analysis store.
    
    Use this when starting a new conversation or session.
    """
    analysis_store.clear()


def get_all_symbols_analyzed(analysis_store: Dict[str, Dict[str, Any]]) -> set:
    """
    Get a set of all symbols that have been analyzed.
    
    Returns:
        Set of symbol strings
    """
    return {entry["symbol"] for entry in analysis_store.values()}


def print_store_summary(analysis_store: Dict[str, Dict[str, Any]]) -> None:
    """
    Print a human-readable summary of the analysis store contents.
    
    Useful for debugging.
    """
    if not analysis_store:
        print("📦 Analysis Store: EMPTY")
        return
    
    print(f"📦 Analysis Store: {len(analysis_store)} entries")
    print("=" * 60)
    
    for key, entry in analysis_store.items():
        symbol = entry["symbol"]
        tf = entry["timeframe"]
        horizon = entry["metadata"]["horizon"]
        
        # Check which analyses are complete
        completed = []
        if entry.get("indicator"):
            completed.append("IND")
        if entry.get("pattern"):
            completed.append("PAT")
        if entry.get("trend"):
            completed.append("TRN")
        if entry.get("decision"):
            completed.append("DEC")
        
        status = "+".join(completed) if completed else "EMPTY"
        
        print(f"  {symbol} | {tf} | {horizon} | [{status}]")
    
    print("=" * 60)


# ============================================================================
# ANALYSIS STORE KEY GENERATION (WITH HORIZON)
# ============================================================================

def make_analysis_store_key(
    symbol: str,
    timeframe: str,
    start_datetime: str,
    end_datetime: str,
    horizon: str
) -> str:
    """
    Generate the CANONICAL key for analysis_store with horizon.
    
    Format: "{symbol}|{timeframe}|{start_datetime}:{end_datetime}|{horizon}"
    
    Args:
        symbol: Ticker symbol (e.g., "BTC", "AAPL")
        timeframe: Chart timeframe (e.g., "15m", "1h", "1d")
        start_datetime: ISO-8601 with timezone (e.g., "2026-01-12T09:00:00+05:30")
        end_datetime: ISO-8601 with timezone
        horizon: "intraday" | "swing" | "long_term"
        
    Returns:
        Canonical store key string
    """
    return f"{symbol}|{timeframe}|{start_datetime}:{end_datetime}|{horizon}"


def parse_analysis_store_key(key: str) -> Dict[str, str]:
    """
    Parse an analysis_store key back into components.
    
    Args:
        key: Store key string
        
    Returns:
        Dict with symbol, timeframe, start_datetime, end_datetime, horizon
    """
    parts = key.split("|")
    if len(parts) != 4:
        raise ValueError(f"Invalid store key format: {key}")
    
    symbol = parts[0]
    timeframe = parts[1]
    datetime_range = parts[2]
    horizon = parts[3]
    
    start_datetime, end_datetime = datetime_range.split(":")
    
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "start_datetime": start_datetime,
        "end_datetime": end_datetime,
        "horizon": horizon
    }


# ============================================================================
# FRESHNESS CALCULATION FUNCTIONS (PER AGENT)
# ============================================================================

def calculate_indicator_freshness(
    created_at: str,
    timeframe: str
) -> str:
    """
    Calculate fresh_until for indicator agent output.
    
    Rule: Indicators depend on recent prices → very strict tolerance (1 candle)
    
    Args:
        created_at: ISO-8601 timestamp when analysis was created
        timeframe: Chart timeframe (e.g., "15m", "1h")
        
    Returns:
        ISO-8601 timestamp for fresh_until
    """
    tolerance = INDICATOR_TOLERANCE.get(timeframe)
    if not tolerance:
        # Default to 15 minutes if timeframe not recognized
        return add_minutes(created_at, 15)
    
    if "duration_minutes" in tolerance:
        return add_minutes(created_at, tolerance["duration_minutes"])
    elif "duration_days" in tolerance:
        return add_days(created_at, tolerance["duration_days"])
    else:
        return add_minutes(created_at, 15)


def calculate_pattern_freshness(
    created_at: str,
    timeframe: str,
    horizon: str
) -> str:
    """
    Calculate fresh_until for pattern agent output.
    
    Rule: Patterns are structural → tolerate small extensions (2-3 candles)
    
    Args:
        created_at: ISO-8601 timestamp when analysis was created
        timeframe: Chart timeframe
        horizon: "intraday" | "swing" | "long_term"
        
    Returns:
        ISO-8601 timestamp for fresh_until
    """
    if horizon == "intraday":
        tolerance = PATTERN_TOLERANCE_INTRADAY.get(timeframe)
        if tolerance and "duration_minutes" in tolerance:
            return add_minutes(created_at, tolerance["duration_minutes"])
    elif horizon == "swing":
        tolerance = PATTERN_TOLERANCE_SWING.get(timeframe)
        if tolerance and "max_days" in tolerance:
            return add_days(created_at, tolerance["max_days"])
    elif horizon == "long_term":
        tolerance = PATTERN_TOLERANCE_LONG_TERM.get(timeframe)
        if tolerance:
            if "max_weeks" in tolerance:
                return add_weeks(created_at, tolerance["max_weeks"])
    
    # Default fallback
    return add_minutes(created_at, 60)


def calculate_trend_freshness(
    created_at: str,
    start_datetime: str,
    end_datetime: str,
    horizon: str
) -> str:
    """
    Calculate fresh_until for trend agent output.
    
    Rule: Trends are macro → tolerate significant drift (% of window)
    
    Args:
        created_at: ISO-8601 timestamp when analysis was created
        start_datetime: Start of analysis window (ISO-8601)
        end_datetime: End of analysis window (ISO-8601)
        horizon: "intraday" | "swing" | "long_term"
        
    Returns:
        ISO-8601 timestamp for fresh_until
    """
    # Calculate window duration
    window_minutes = calculate_time_delta_minutes(start_datetime, end_datetime)
    
    # Get tolerance % for horizon
    tolerance_pct = TREND_TOLERANCE.get(horizon, 0.25)
    
    # Calculate freshness window
    freshness_minutes = int(window_minutes * tolerance_pct)
    
    return add_minutes(created_at, freshness_minutes)


# ============================================================================
# FRESHNESS CHECKING FUNCTIONS
# ============================================================================

def is_agent_output_fresh(
    analysis_store: Dict[str, Any],
    store_key: str,
    agent_name: str,
    current_time: Optional[str] = None
) -> bool:
    """
    Check if a specific agent's output is still fresh.
    
    Args:
        analysis_store: The analysis store dict
        store_key: Full store key (with horizon)
        agent_name: "indicator" | "pattern" | "trend"
        current_time: ISO-8601 timestamp (defaults to now)
        
    Returns:
        True if agent output exists and is fresh, False otherwise
    """
    if current_time is None:
        current_time = get_current_time_iso()
    
    # Check if store entry exists
    if store_key not in analysis_store:
        return False
    
    entry = analysis_store[store_key]
    
    # Check if agent output exists
    if agent_name not in entry or entry[agent_name] is None:
        return False
    
    agent_output = entry[agent_name]

    # Preferred: top-level fresh_until (AgentOutput)
    fresh_until = agent_output.get("fresh_until")

    # Back-compat: nested metadata.fresh_until
    if fresh_until is None and isinstance(agent_output.get("metadata"), dict):
        fresh_until = agent_output["metadata"].get("fresh_until")

    if fresh_until is None:
        return False

    return is_time_before(current_time, fresh_until) or current_time == fresh_until


def decision_is_stale(store_key: str, analysis_store: Dict[str, Any]) -> bool:
    """
    Detect whether the cached decision for THIS store_key is stale.

    Algorithm (timestamp-compare with tolerance, per DataContext+Horizon):
    - If decision missing => stale
    - If any upstream agent output missing => stale
    - If any upstream agent ran AFTER decision by MORE than tolerance => stale
    
    Tolerance windows by horizon:
    - intraday: 15 minutes
    - swing: 6 hours
    - long_term: 3 days
    """
    from datetime import timedelta
    
    # Tolerance windows
    DECISION_TOLERANCE = {
        "intraday": timedelta(minutes=15),
        "swing": timedelta(hours=6),
        "long_term": timedelta(days=3)
    }
    
    # Extract horizon from store_key
    # store_key format: "{symbol}|{timeframe}|{start}:{end}|{horizon}"
    parts = store_key.split("|")
    horizon = parts[4] if len(parts) > 4 else "intraday"
    tolerance = DECISION_TOLERANCE.get(horizon, timedelta(minutes=15))
    
    entry = analysis_store.get(store_key, {})
    decision = entry.get("decision")
    if not isinstance(decision, dict):
        return True

    decision_time = (
        decision.get("created_at")
        or (decision.get("metadata") or {}).get("ran_at")
        or (decision.get("metadata") or {}).get("created_at")
    )
    if not decision_time:
        return True

    try:
        decision_dt = parse_iso_datetime(decision_time)
    except Exception:
        return True

    for agent in ["indicator", "pattern", "trend"]:
        upstream = entry.get(agent)
        if not isinstance(upstream, dict):
            # Upstream missing - but don't mark stale if decision exists
            # Decision can exist even if some upstreams haven't run yet
            continue

        upstream_time = (
            upstream.get("created_at")
            or (upstream.get("metadata") or {}).get("ran_at")
            or (upstream.get("metadata") or {}).get("created_at")
        )
        if not upstream_time:
            continue

        try:
            upstream_dt = parse_iso_datetime(upstream_time)
        except Exception:
            continue

        # Check if upstream is newer by MORE than tolerance
        time_diff = upstream_dt - decision_dt
        if time_diff > tolerance:
            print(f"  ⚠️  Decision stale: {agent}.ran_at > decision.ran_at by {time_diff} (tolerance: {tolerance})")
            return True

    return False


# ============================================================================
# ANALYSIS STORE UPDATE FUNCTIONS (WITH METADATA)
# ============================================================================

def store_agent_output(
    analysis_store: Dict[str, Any],
    store_key: str,
    agent_name: str,
    data: Any,
    metadata: Dict[str, Any]
) -> None:
    """
    Store agent output with metadata in analysis_store.
    
    Initializes store entry if it doesn't exist.
    
    Args:
        analysis_store: The analysis store dict (modified in-place)
        store_key: Full store key (with horizon)
        agent_name: "indicator" | "pattern" | "trend" | "decision"
        data: Agent output data
        metadata: Metadata dict with created_at, fresh_until, etc.
    """
    # Initialize entry if needed
    if store_key not in analysis_store:
        analysis_store[store_key] = {}
    
    created_at = metadata.get("created_at") or metadata.get("ran_at") or get_current_time_iso()
    fresh_until = metadata.get("fresh_until")
    model_version = metadata.get("model_version") or metadata.get("model") or "unknown"

    # Store agent output (AgentOutput-compatible)
    analysis_store[store_key][agent_name] = {
        "result": data,
        "created_at": created_at,
        "fresh_until": fresh_until,
        "model_version": model_version,
        "metadata": {
            **metadata,
            "ran_at": metadata.get("ran_at") or created_at,
            "created_at": created_at,
            "fresh_until": fresh_until,
            "agent": agent_name,
        },
    }


def get_agent_output(
    analysis_store: Dict[str, Any],
    store_key: str,
    agent_name: str
) -> Optional[Dict[str, Any]]:
    """
    Retrieve agent output from analysis_store.
    
    Args:
        analysis_store: The analysis store dict
        store_key: Full store key (with horizon)
        agent_name: "indicator" | "pattern" | "trend" | "decision"
        
    Returns:
        Dict with "data" and "metadata" keys, or None if not found
    """
    if store_key not in analysis_store:
        return None
    
    entry = analysis_store[store_key]
    
    if agent_name not in entry or entry[agent_name] is None:
        return None
    
    return entry[agent_name]


# ============================================================================
# LEGACY COMPATIBILITY (TO BE REMOVED)
# ============================================================================

def make_analysis_key(symbol: str, timeframe: str, start_date: str, end_date: str) -> str:
    """
    DEPRECATED: Use make_analysis_store_key() with horizon instead.
    
    Legacy key format without horizon (for backward compatibility only).
    """
    return f"{symbol}|{timeframe}|{start_date}:{end_date}"
