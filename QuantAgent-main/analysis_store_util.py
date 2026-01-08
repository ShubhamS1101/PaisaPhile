"""
Utility functions for managing the analysis_store and per-query execution fields in TradingAdvisorState.

The analysis_store is a persistent cache for all analysis results,
structured to enable efficient lookups and updates across conversation turns.

Per-query execution fields (data_required_keys, required_analysis_keys) are
reset every turn and guide router execution without being passed to LLMs.

Key Format: "{symbol}|{timeframe}|{start_date}:{end_date}"
Example: "BEL.NS|15m|2026-01-01:2026-01-02"
"""

from datetime import datetime
from typing import Dict, Any, Optional, List


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
    required_keys = state.get("required_analysis_keys", {})
    
    # If no specific keys requested, return all (explanation mode might need this)
    if not required_keys:
        return analysis_store
    
    # Filter to only required keys
    filtered = {}
    for key in required_keys.keys():
        if key in analysis_store:
            filtered[key] = analysis_store[key]
    
    return filtered


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
