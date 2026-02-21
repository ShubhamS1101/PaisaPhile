"""
Decision Freshness Check Logic

Ensures decision always reflects the latest upstream analysis (indicator/pattern/trend).
If any upstream agent has ran_at newer than decision.ran_at beyond tolerance, decision is stale.

Tolerance windows by horizon:
- intraday: 5-15 minutes
- swing: 1-6 hours  
- long_term: 1-3 days
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# Tolerance windows for decision freshness check
DECISION_TOLERANCE = {
    "intraday": timedelta(minutes=15),      # 15 minutes
    "swing": timedelta(hours=6),            # 6 hours
    "long_term": timedelta(days=3)          # 3 days
}


def parse_iso_datetime(dt_str: str) -> datetime:
    """Parse ISO-8601 datetime string to datetime object."""
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return dt
    except (ValueError, AttributeError):
        return datetime.now(IST)


def is_decision_stale(
    analysis_entry: Dict[str, Any],
    horizon: str
) -> bool:
    """
    Check if decision is stale compared to upstream agents.
    
    Decision is stale if any upstream agent (indicator/pattern/trend) has
    ran_at that is newer than decision.ran_at by more than the tolerance window.
    
    Args:
        analysis_entry: Analysis store entry for a data context
        horizon: "intraday" | "swing" | "long_term"
        
    Returns:
        True if decision needs to be rerun, False if it's still fresh
    """
    
    # Get decision metadata
    decision_output = analysis_entry.get("decision")
    if not decision_output:
        # No decision exists, must run
        return True
    
    decision_metadata = decision_output.get("metadata", {})
    decision_ran_at_str = decision_metadata.get("ran_at")
    
    if not decision_ran_at_str:
        # No ran_at timestamp, assume stale
        return True
    
    decision_ran_at = parse_iso_datetime(decision_ran_at_str)
    tolerance = DECISION_TOLERANCE.get(horizon, timedelta(minutes=15))
    
    # Check each upstream agent
    upstream_agents = ["indicator", "pattern", "trend"]
    
    for agent_name in upstream_agents:
        agent_output = analysis_entry.get(agent_name)
        if not agent_output:
            # Agent hasn't run yet, skip
            continue
        
        agent_metadata = agent_output.get("metadata", {})
        agent_ran_at_str = agent_metadata.get("ran_at")
        
        if not agent_ran_at_str:
            # No ran_at timestamp, skip
            continue
        
        agent_ran_at = parse_iso_datetime(agent_ran_at_str)
        
        # Check if upstream agent is significantly newer
        time_diff = agent_ran_at - decision_ran_at
        
        if time_diff > tolerance:
            # Upstream agent is newer by more than tolerance
            print(f"  ⚠️  Decision stale: {agent_name}.ran_at ({agent_ran_at_str}) > "
                  f"decision.ran_at ({decision_ran_at_str}) by {time_diff} (tolerance: {tolerance})")
            return True
    
    # All upstream agents are within tolerance
    return False


def should_run_decision(
    state: Dict[str, Any],
    window_key: str,
) -> bool:
    """
    Determine if decision agent should run for a given window.
    
    Decision runs if:
    1. Explicitly listed in analyses_required[window_key].run, OR
    2. Decision exists but is stale (upstream agents have newer ran_at)
    
    Args:
        state: TradingAdvisorState
        window_key: Window identity key (ROLLING or HISTORICAL)
        
    Returns:
        True if decision should run, False otherwise
    """
    analyses_required = state.get("analyses_required", {})
    spec = analyses_required.get(window_key, {})
    run_list = spec.get("run", [])
    
    # Check if explicitly requested
    if "decision" in run_list:
        return True
    
    # Extract horizon from window key
    from analysis_store_util import parse_window_key
    try:
        parsed = parse_window_key(window_key)
        horizon = parsed["horizon"]
    except (ValueError, KeyError):
        horizon = "intraday"
    
    # Check freshness
    analysis_store = state.get("analysis_store", {})
    analysis_entry = analysis_store.get(window_key, {})
    
    if is_decision_stale(analysis_entry, horizon):
        print(f"  🔄 Decision stale for {window_key}, will rerun")
        return True
    
    print(f"  ✓ Decision fresh for {window_key}, skipping")
    return False
