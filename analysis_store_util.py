"""
Utility functions for managing the analysis_store in TradingAdvisorState.

The analysis_store is a persistent cache keyed by SEMANTIC window identities:

  ROLLING:    "{symbol}|{timeframe}|ROLLING|{horizon}|{lookback}"
  HISTORICAL: "{symbol}|{timeframe}|HISTORICAL|{start}:{end}|{horizon}"

ROLLING windows never contain exact timestamps in their key.
The actual data range lives inside each component's metadata.

HISTORICAL windows have pinned date boundaries (YYYY-MM-DD only).

Each agent output has its own freshness window:
  - Indicator: Most sensitive (1 candle tolerance)
  - Pattern: Moderately sensitive (2-3 candles)
  - Trend: Least sensitive (% of analysis window)
  - Decision: Derived (invalidated when upstream is newer by > tolerance)
"""

from datetime import datetime, timedelta
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
    is_time_after,
)


# ============================================================================
# WINDOW KEY CONSTRUCTION & PARSING
# ============================================================================

def make_rolling_key(
    symbol: str,
    timeframe: str,
    horizon: str,
    lookback: str,
) -> str:
    """
    Build a ROLLING window key.

    Format: "{symbol}|{timeframe}|ROLLING|{horizon}|{lookback}"
    Example: "BEL.NS|1d|ROLLING|long_term|3y"

    ROLLING keys contain NO timestamps — they represent a stable semantic slot.
    """
    return f"{symbol}|{timeframe}|ROLLING|{horizon}|{lookback}"


def make_historical_key(
    symbol: str,
    timeframe: str,
    start: str,
    end: str,
    horizon: str,
) -> str:
    """
    Build a HISTORICAL window key.

    Format: "{symbol}|{timeframe}|HISTORICAL|{start}:{end}|{horizon}"
    Example: "BEL.NS|1d|HISTORICAL|2024-01-01:2024-06-30|long_term"

    start/end are date strings (YYYY-MM-DD), NOT full ISO-8601 timestamps.
    """
    return f"{symbol}|{timeframe}|HISTORICAL|{start}:{end}|{horizon}"


def make_data_id(symbol: str, timeframe: str) -> str:
    """
    Build a data_id for raw data fetch requests (price_check etc.).

    Format: "{symbol}_{timeframe}_{iso_timestamp}"
    Example: "AAPL_1d_2026-02-22T14:30:00"

    The timestamp makes each request unique per turn.
    """
    ts = get_current_time_iso().replace(":", "-")  # filesystem-safe
    return f"{symbol}_{timeframe}_{ts}"


def make_window_key(spec: Dict[str, Any]) -> str:
    """
    Build a window key from a WindowSpec dict.

    Dispatches to make_rolling_key or make_historical_key based on window_type.

    Args:
        spec: WindowSpec dict with symbol, timeframe, horizon, window_type,
              and either lookback (ROLLING) or start+end (HISTORICAL)
    """
    wtype = spec.get("window_type", "ROLLING").upper()
    symbol = spec["symbol"]
    timeframe = spec["timeframe"]
    horizon = spec["horizon"]

    if wtype == "HISTORICAL":
        return make_historical_key(symbol, timeframe, spec["start"], spec["end"], horizon)
    else:
        return make_rolling_key(symbol, timeframe, horizon, spec.get("lookback", "default"))


def parse_window_key(key: str) -> Dict[str, str]:
    """
    Parse a window key back into its components.

    Returns dict with:
      - symbol, timeframe, window_type, horizon
      - lookback (ROLLING only)
      - start, end (HISTORICAL only)

    Raises ValueError on unrecognized format.
    """
    parts = key.split("|")

    if len(parts) < 4:
        raise ValueError(f"Invalid window key (too few parts): {key}")

    symbol = parts[0]
    timeframe = parts[1]
    window_type = parts[2]  # "ROLLING" or "HISTORICAL"

    if window_type == "ROLLING":
        if len(parts) != 5:
            raise ValueError(f"ROLLING key must have 5 parts: {key}")
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "window_type": "ROLLING",
            "horizon": parts[3],
            "lookback": parts[4],
        }
    elif window_type == "HISTORICAL":
        if len(parts) != 5:
            raise ValueError(f"HISTORICAL key must have 5 parts: {key}")
        date_range = parts[3]
        horizon = parts[4]
        # date_range is "YYYY-MM-DD:YYYY-MM-DD"
        colon_idx = date_range.index(":")
        start = date_range[:colon_idx]
        end = date_range[colon_idx + 1:]
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "window_type": "HISTORICAL",
            "start": start,
            "end": end,
            "horizon": horizon,
        }
    else:
        raise ValueError(f"Unknown window_type '{window_type}' in key: {key}")


def is_rolling_key(key: str) -> bool:
    """Check if a window key is ROLLING format."""
    parts = key.split("|")
    return len(parts) >= 3 and parts[2] == "ROLLING"


def is_historical_key(key: str) -> bool:
    """Check if a window key is HISTORICAL format."""
    parts = key.split("|")
    return len(parts) >= 3 and parts[2] == "HISTORICAL"


def get_symbol_from_key(key: str) -> str:
    """Extract symbol from any window key."""
    return key.split("|")[0]


def get_timeframe_from_key(key: str) -> str:
    """Extract timeframe from any window key."""
    return key.split("|")[1]


def get_horizon_from_key(key: str) -> str:
    """Extract horizon from a window key."""
    parsed = parse_window_key(key)
    return parsed["horizon"]


# ============================================================================
# STATIC DEPENDENCY GRAPH
# ============================================================================
#
#   indicator ──→ trend ──→ decision
#   pattern  ─────────────→ decision
#
# Rules:
#   - If indicator is stale/recomputed → trend AND decision must rerun
#   - If trend is stale/recomputed     → decision must rerun
#   - If pattern is stale/recomputed   → decision must rerun
#   - If decision is stale             → NO back-propagation
# ============================================================================

# Maps each agent to its direct downstream dependents
AGENT_DEPENDENTS = {
    "indicator": ["trend", "decision"],
    "pattern": ["decision"],
    "trend": ["decision"],
    "decision": [],  # No back-propagation
}

# Maps each agent to its upstream dependencies
AGENT_DEPENDENCIES = {
    "indicator": [],
    "pattern": [],
    "trend": ["indicator"],
    "decision": ["indicator", "pattern", "trend"],
}


def get_dependents(agent_name: str) -> List[str]:
    """Get all transitive dependents of an agent (downstream cascade)."""
    visited = set()
    stack = list(AGENT_DEPENDENTS.get(agent_name, []))
    while stack:
        dep = stack.pop()
        if dep not in visited:
            visited.add(dep)
            stack.extend(AGENT_DEPENDENTS.get(dep, []))
    return list(visited)


def propagate_staleness(
    state: Dict[str, Any],
    current_time: Optional[str] = None,
) -> None:
    """
    Pre-execution dependency propagation.

    For each window in analyses_required, check which agents are stale
    or already marked to run, then cascade to dependents.

    Called ONCE after fetch and BEFORE any agent executes.

    Modifies analyses_required[window_key]["run"] in-place.
    """
    if current_time is None:
        current_time = get_current_time_iso()

    analyses_required = state.get("analyses_required", {})
    analysis_store = state.get("analysis_store", {})

    for window_key, spec in analyses_required.items():
        run_list = spec.get("run", [])
        entry = analysis_store.get(window_key, {})

        # Collect agents that WILL run (explicitly listed or stale)
        will_run = set(run_list)

        # Also check freshness: if an agent is in the entry but stale,
        # it will rerun even if not explicitly listed (agents do their own
        # freshness check). We anticipate that here for cascade purposes.
        for agent_name in ["indicator", "pattern", "trend"]:
            if agent_name in will_run:
                continue  # Already marked
            if not is_agent_output_fresh(analysis_store, window_key, agent_name, current_time):
                if entry.get(agent_name) is not None:
                    # Exists but stale → will rerun
                    will_run.add(agent_name)

        # Now propagate: for every agent that will run, add its dependents
        to_add = set()
        for agent_name in will_run:
            for dep in get_dependents(agent_name):
                to_add.add(dep)

        # Inject dependents into run list
        added = []
        for dep in to_add:
            if dep not in run_list:
                run_list.append(dep)
                added.append(dep)

        if added:
            print(
                f"  📡 Dependency cascade for {window_key}: "
                f"{list(will_run)} → adding {added}"
            )


def force_dependents_to_run(
    state: Dict[str, Any],
    window_key: str,
    agent_name: str,
) -> None:
    """
    Post-execution cascade: after an agent ACTUALLY recomputes (not cached),
    ensure all its dependents are in the run list for this window.

    Called by each agent after it runs (not when it serves from cache).
    """
    spec = state.get("analyses_required", {}).get(window_key, {})
    if not spec:
        return
    run_list = spec.get("run", [])

    added = []
    for dep in get_dependents(agent_name):
        if dep not in run_list:
            run_list.append(dep)
            added.append(dep)

    if added:
        print(
            f"  🔗 {agent_name} recomputed → forcing {added} to rerun "
            f"for {window_key}"
        )


# ============================================================================
# PER-QUERY EXECUTION FIELD MANAGEMENT
# These fields are RESET every turn and guide routing logic only
# ============================================================================

def reset_execution_fields(state: Dict[str, Any]) -> None:
    """
    Reset per-query execution fields at the start of a new user query.
    """
    state["windows_required"] = []
    state["analyses_required"] = {}


def get_pending_analyses(state: Dict[str, Any], window_key: str) -> List[str]:
    """
    Get analyses still needed for a given window_key this turn.

    Checks analyses_required (what infra determined must run) and
    analysis_store (what's already cached and fresh).
    """
    spec = state.get("analyses_required", {}).get(window_key, {})
    required = spec.get("run", [])
    if not required:
        return []

    analysis_store = state.get("analysis_store", {})
    if window_key not in analysis_store:
        return list(required)

    entry = analysis_store[window_key]
    pending = []
    for agent_name in required:
        if agent_name == "decision":
            pending.append(agent_name)  # Decision always re-evaluated
        elif entry.get(agent_name) is None:
            pending.append(agent_name)

    return pending


def mark_analysis_complete(
    state: Dict[str, Any], window_key: str, agent_name: str
) -> None:
    """
    Remove a completed agent from this turn's run list.
    """
    spec = state.get("analyses_required", {}).get(window_key, {})
    run_list = spec.get("run", [])
    if agent_name in run_list:
        run_list.remove(agent_name)


def has_pending_work(state: Dict[str, Any]) -> bool:
    """Check if any window still has agents to run this turn."""
    for _window_key, spec in state.get("analyses_required", {}).items():
        if spec.get("run"):
            return True
    return False


# ============================================================================
# ANALYSIS STORE FILTERING
# ============================================================================

def get_filtered_analysis_store(
    state: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """
    Extract analysis_store entries relevant to the current query.

    In the new model, window_id IS the store key, so filtering is direct:
    just look up each key from analyses_required.
    """
    analysis_store = state.get("analysis_store", {})
    analyses_required = state.get("analyses_required", {})

    if not analyses_required:
        return analysis_store

    filtered: Dict[str, Dict[str, Any]] = {}
    for window_key in analyses_required:
        if window_key in analysis_store:
            filtered[window_key] = analysis_store[window_key]

    return filtered


# ============================================================================
# WINDOW ENTRY MANAGEMENT (ACTIVE / ARCHIVE / LRU)
# ============================================================================

def init_window_entry(
    analysis_store: Dict[str, Any], window_key: str
) -> None:
    """
    Initialize a new window entry in the store if it doesn't exist.

    Sets status="active" and last_accessed to now.
    """
    if window_key not in analysis_store:
        analysis_store[window_key] = {
            "status": "active",
            "last_accessed": get_current_time_iso(),
            "fetched_start": None,
            "fetched_end": None,
            "candles_fetched": None,
            "indicator": None,
            "pattern": None,
            "trend": None,
            "decision": None,
        }


def touch_window(
    analysis_store: Dict[str, Any], window_key: str
) -> None:
    """Update last_accessed timestamp for LRU tracking."""
    if window_key in analysis_store:
        analysis_store[window_key]["last_accessed"] = get_current_time_iso()


def archive_window(
    analysis_store: Dict[str, Any], window_key: str
) -> None:
    """Mark a window as archived (evicted from active set)."""
    if window_key in analysis_store:
        analysis_store[window_key]["status"] = "archive"


def activate_window(
    analysis_store: Dict[str, Any], window_key: str
) -> None:
    """Promote an archived window back to active."""
    if window_key in analysis_store:
        analysis_store[window_key]["status"] = "active"
        touch_window(analysis_store, window_key)


def get_active_windows(
    analysis_store: Dict[str, Any],
) -> Dict[str, Any]:
    """Return only active (non-archived) windows."""
    return {
        k: v for k, v in analysis_store.items() if v.get("status") == "active"
    }


def get_archived_windows(
    analysis_store: Dict[str, Any],
) -> Dict[str, Any]:
    """Return only archived windows."""
    return {
        k: v for k, v in analysis_store.items() if v.get("status") == "archive"
    }


def evict_lru_windows(
    analysis_store: Dict[str, Any], max_active: int = 5
) -> List[str]:
    """
    Evict least-recently-used active windows to stay within max_active limit.

    Returns list of evicted window keys.
    """
    active = get_active_windows(analysis_store)
    if len(active) <= max_active:
        return []

    # Sort by last_accessed ascending (oldest first)
    sorted_keys = sorted(
        active.keys(),
        key=lambda k: active[k].get("last_accessed", ""),
    )

    evict_count = len(active) - max_active
    evicted = []
    for key in sorted_keys[:evict_count]:
        archive_window(analysis_store, key)
        evicted.append(key)

    return evicted


# ============================================================================
# FIELD-LEVEL ACCESS HELPERS
# ============================================================================

def update_analysis_field(
    analysis_store: Dict[str, Any],
    window_key: str,
    field: str,
    data: Any,
) -> None:
    """
    Update a specific field in an existing analysis entry.
    """
    valid_fields = {"indicator", "pattern", "trend", "decision"}
    if field not in valid_fields:
        raise ValueError(f"Invalid field '{field}'. Must be one of {valid_fields}")
    if window_key not in analysis_store:
        raise KeyError(f"Window key '{window_key}' not found in store")
    analysis_store[window_key][field] = data


def has_field(
    analysis_store: Dict[str, Any], window_key: str, field: str
) -> bool:
    """Check if a specific agent output exists and is not None."""
    if window_key not in analysis_store:
        return False
    return analysis_store[window_key].get(field) is not None


def get_field(
    analysis_store: Dict[str, Any], window_key: str, field: str
) -> Optional[Any]:
    """Get a specific agent output from a window entry."""
    if window_key not in analysis_store:
        return None
    return analysis_store[window_key].get(field)


def clear_analysis_store(analysis_store: Dict[str, Any]) -> None:
    """Clear all entries from the analysis store."""
    analysis_store.clear()


def get_all_symbols_analyzed(analysis_store: Dict[str, Any]) -> set:
    """Get set of all symbols that have been analyzed."""
    symbols = set()
    for key in analysis_store:
        try:
            symbols.add(get_symbol_from_key(key))
        except (IndexError, ValueError):
            continue
    return symbols


def print_store_summary(analysis_store: Dict[str, Any]) -> None:
    """Print a human-readable summary of the analysis store."""
    if not analysis_store:
        print("📦 Analysis Store: EMPTY")
        return

    print(f"📦 Analysis Store: {len(analysis_store)} entries")
    print("=" * 70)

    for key, entry in analysis_store.items():
        try:
            parsed = parse_window_key(key)
        except ValueError:
            print(f"  ⚠️ Unparseable key: {key}")
            continue

        symbol = parsed["symbol"]
        tf = parsed["timeframe"]
        wtype = parsed["window_type"]
        horizon = parsed["horizon"]
        status = entry.get("status", "?")

        completed = []
        for agent in ("indicator", "pattern", "trend", "decision"):
            if entry.get(agent):
                completed.append(agent[:3].upper())

        agent_status = "+".join(completed) if completed else "EMPTY"

        if wtype == "ROLLING":
            extra = f"lookback={parsed.get('lookback', '?')}"
        else:
            extra = f"{parsed.get('start', '?')}→{parsed.get('end', '?')}"

        print(
            f"  [{status:>7}] {symbol} | {tf} | {horizon} "
            f"| {wtype} ({extra}) | [{agent_status}]"
        )

    print("=" * 70)


# ============================================================================
# FRESHNESS CALCULATION FUNCTIONS (PER AGENT)
# These don't depend on key format — they work with timestamps only.
# ============================================================================

def calculate_indicator_freshness(created_at: str, timeframe: str) -> str:
    """
    Calculate fresh_until for indicator output.
    Rule: 1 candle tolerance.
    """
    tolerance = INDICATOR_TOLERANCE.get(timeframe)
    if not tolerance:
        return add_minutes(created_at, 15)
    if "duration_minutes" in tolerance:
        return add_minutes(created_at, tolerance["duration_minutes"])
    elif "duration_days" in tolerance:
        return add_days(created_at, tolerance["duration_days"])
    return add_minutes(created_at, 15)


def calculate_pattern_freshness(
    created_at: str, timeframe: str, horizon: str
) -> str:
    """
    Calculate fresh_until for pattern output.
    Rule: 2-3 candle tolerance, scaled by horizon.
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
        if tolerance and "max_weeks" in tolerance:
            return add_weeks(created_at, tolerance["max_weeks"])
    return add_minutes(created_at, 60)


def calculate_trend_freshness(
    created_at: str,
    start_datetime: str,
    end_datetime: str,
    horizon: str,
) -> str:
    """
    Calculate fresh_until for trend output.
    Rule: % of analysis window duration.
    """
    window_minutes = calculate_time_delta_minutes(start_datetime, end_datetime)
    tolerance_pct = TREND_TOLERANCE.get(horizon, 0.25)
    freshness_minutes = int(window_minutes * tolerance_pct)
    return add_minutes(created_at, freshness_minutes)


# ============================================================================
# FRESHNESS CHECKING
# ============================================================================

def is_agent_output_fresh(
    analysis_store: Dict[str, Any],
    store_key: str,
    agent_name: str,
    current_time: Optional[str] = None,
) -> bool:
    """
    Check if a specific agent's output is still fresh.

    Args:
        analysis_store: The analysis store dict
        store_key: Window key (ROLLING or HISTORICAL)
        agent_name: "indicator" | "pattern" | "trend"
        current_time: ISO-8601 timestamp (defaults to now)

    Returns:
        True if agent output exists and is fresh, False otherwise
    """
    if current_time is None:
        current_time = get_current_time_iso()

    if store_key not in analysis_store:
        return False

    entry = analysis_store[store_key]

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


def decision_is_stale(
    store_key: str, analysis_store: Dict[str, Any]
) -> bool:
    """
    Check whether the cached decision for a window is stale.

    Stale if:
      - Decision missing
      - Any upstream agent ran AFTER decision by more than tolerance

    Tolerance by horizon:
      - intraday: 15 minutes
      - swing: 6 hours
      - long_term: 3 days
    """
    DECISION_TOLERANCE = {
        "intraday": timedelta(minutes=15),
        "swing": timedelta(hours=6),
        "long_term": timedelta(days=3),
    }

    # Extract horizon from window key (works for both ROLLING and HISTORICAL)
    try:
        parsed = parse_window_key(store_key)
        horizon = parsed["horizon"]
    except (ValueError, KeyError):
        horizon = "intraday"

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

    for agent in ("indicator", "pattern", "trend"):
        upstream = entry.get(agent)
        if not isinstance(upstream, dict):
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

        if (upstream_dt - decision_dt) > tolerance:
            print(
                f"  ⚠️  Decision stale: {agent} newer than decision "
                f"by > {tolerance}"
            )
            return True

    return False


# ============================================================================
# STORE / RETRIEVE AGENT OUTPUT
# ============================================================================

def set_window_fetch_timestamps(
    analysis_store: Dict[str, Any],
    window_key: str,
    fetched_start: str,
    fetched_end: str,
    candles_fetched: int,
) -> None:
    """
    Record the actual data range fetched for a window.

    Called by the fetch node after yfinance download resolves
    the real first/last candle timestamps.
    """
    init_window_entry(analysis_store, window_key)
    analysis_store[window_key]["fetched_start"] = fetched_start
    analysis_store[window_key]["fetched_end"] = fetched_end
    analysis_store[window_key]["candles_fetched"] = candles_fetched


def store_agent_output(
    analysis_store: Dict[str, Any],
    store_key: str,
    agent_name: str,
    data: Any,
    metadata: Dict[str, Any],
) -> None:
    """
    Store agent output with metadata in analysis_store.

    Initializes window entry if it doesn't exist.
    Touches last_accessed for LRU.
    Also copies window-level fetched timestamps into agent metadata.

    Args:
        analysis_store: The analysis store dict (modified in-place)
        store_key: Window key (ROLLING or HISTORICAL)
        agent_name: "indicator" | "pattern" | "trend" | "decision"
        data: Agent output data
        metadata: Metadata dict with created_at, fresh_until, etc.
    """
    init_window_entry(analysis_store, store_key)
    touch_window(analysis_store, store_key)

    # Copy window-level fetch timestamps into agent metadata
    entry = analysis_store[store_key]
    if entry.get("fetched_start"):
        metadata.setdefault("data_window_start", entry["fetched_start"])
    if entry.get("fetched_end"):
        metadata.setdefault("data_window_end", entry["fetched_end"])

    created_at = (
        metadata.get("created_at")
        or metadata.get("ran_at")
        or get_current_time_iso()
    )
    fresh_until = metadata.get("fresh_until")
    model_version = (
        metadata.get("model_version") or metadata.get("model") or "unknown"
    )

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
    agent_name: str,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve agent output from analysis_store.

    Args:
        analysis_store: The analysis store dict
        store_key: Window key (ROLLING or HISTORICAL)
        agent_name: "indicator" | "pattern" | "trend" | "decision"

    Returns:
        AgentOutput dict, or None if not found
    """
    if store_key not in analysis_store:
        return None

    entry = analysis_store[store_key]

    if agent_name not in entry or entry[agent_name] is None:
        return None

    return entry[agent_name]


# ============================================================================
# DEPRECATED COMPATIBILITY SHIMS (WILL BE REMOVED)
# ============================================================================

def make_analysis_store_key(
    symbol: str,
    timeframe: str,
    start_datetime: str,
    end_datetime: str,
    horizon: str,
) -> str:
    """
    DEPRECATED: Use make_rolling_key() or make_historical_key() instead.

    This shim exists only for callers that haven't been migrated yet.
    It produces a HISTORICAL key using the provided start/end dates.
    """
    import warnings
    warnings.warn(
        "make_analysis_store_key() is deprecated. "
        "Use make_rolling_key() or make_historical_key().",
        DeprecationWarning,
        stacklevel=2,
    )
    # Extract date portion if full ISO datetime provided
    start_date = start_datetime[:10] if len(start_datetime) > 10 else start_datetime
    end_date = end_datetime[:10] if len(end_datetime) > 10 else end_datetime
    return make_historical_key(symbol, timeframe, start_date, end_date, horizon)


def parse_analysis_store_key(key: str) -> Dict[str, str]:
    """
    DEPRECATED: Use parse_window_key() instead.

    Delegates to parse_window_key and remaps field names for compatibility.
    """
    import warnings
    warnings.warn(
        "parse_analysis_store_key() is deprecated. Use parse_window_key().",
        DeprecationWarning,
        stacklevel=2,
    )
    parsed = parse_window_key(key)
    # Remap for old callers expecting start_datetime / end_datetime
    result = {
        "symbol": parsed["symbol"],
        "timeframe": parsed["timeframe"],
        "horizon": parsed["horizon"],
    }
    if parsed["window_type"] == "HISTORICAL":
        result["start_datetime"] = parsed["start"]
        result["end_datetime"] = parsed["end"]
    return result


def make_analysis_key(
    symbol: str, timeframe: str, start_date: str, end_date: str
) -> str:
    """
    DEPRECATED: Legacy 3-part key without horizon. Will be removed.
    """
    import warnings
    warnings.warn(
        "make_analysis_key() is deprecated.",
        DeprecationWarning,
        stacklevel=2,
    )
    return f"{symbol}|{timeframe}|{start_date}:{end_date}"
