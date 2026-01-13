"""
Freshness tolerance configuration for per-agent analysis caching.

Each agent has its own freshness window based on:
- Indicator: Most sensitive (1 candle tolerance)
- Pattern: Moderately sensitive (2-3 candles)
- Trend: Least sensitive (% of analysis window)
- Decision: Derived (invalidated only by upstream changes)

Origin/freshness time is PER AGENT PER ANALYSIS, not per DataContext or global.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Timezone for all datetime operations
IST = ZoneInfo("Asia/Kolkata")


# ============================================================================
# INDICATOR AGENT TOLERANCE (MOST STRICT)
# ============================================================================
# Rule: Indicators depend on recent prices → very strict tolerance (1 candle)

INDICATOR_TOLERANCE = {
    "5m": {"max_candles": 1, "duration_minutes": 5},
    "15m": {"max_candles": 1, "duration_minutes": 15},
    "30m": {"max_candles": 1, "duration_minutes": 30},
    "1h": {"max_candles": 1, "duration_minutes": 60},
    "4h": {"max_candles": 1, "duration_minutes": 240},
    "1d": {"max_candles": 1, "duration_days": 1},
    "1w": {"max_candles": 1, "duration_days": 7},
    "1mo": {"max_candles": 1, "duration_days": 30}
}


# ============================================================================
# PATTERN AGENT TOLERANCE (MODERATELY STRICT)
# ============================================================================
# Rule: Patterns are structural → tolerate small extensions

PATTERN_TOLERANCE_INTRADAY = {
    # For timeframes < 1d
    "5m": {"max_candles": 3, "duration_minutes": 15},
    "15m": {"max_candles": 3, "duration_minutes": 45},
    "30m": {"max_candles": 2, "duration_minutes": 60},
    "1h": {"max_candles": 2, "duration_minutes": 120},
    "4h": {"max_candles": 2, "duration_minutes": 480}
}

PATTERN_TOLERANCE_SWING = {
    # For daily timeframes
    "1d": {"max_days": 2}
}

PATTERN_TOLERANCE_LONG_TERM = {
    # For weekly/monthly timeframes
    "1w": {"max_weeks": 1},
    "1mo": {"max_weeks": 2}
}


# ============================================================================
# TREND AGENT TOLERANCE (LEAST STRICT)
# ============================================================================
# Rule: Trends are macro → tolerate significant drift (% of window)

TREND_TOLERANCE = {
    "intraday": 0.25,     # 25% of analysis window
    "swing": 0.35,        # 35% of analysis window
    "long_term": 0.45     # 45% of analysis window
}

# Example: Trend computed on 60 days, new data = 10 days
# → 10/60 = 16.7% < 25% → reuse trend for intraday


# ============================================================================
# DECISION AGENT TOLERANCE
# ============================================================================
# Rule: Decision is derived (cheap to recompute)
# No time-based tolerance - invalidated only when upstream agents change

DECISION_INVALIDATION_RULE = "upstream_change"
# Decision is recomputed ONLY if any of [indicator, pattern, trend] re-ran


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_current_time_iso() -> str:
    """Get current time in ISO-8601 format with IST timezone."""
    return datetime.now(IST).isoformat()


def parse_iso_datetime(iso_string: str) -> datetime:
    """Parse ISO-8601 string to datetime object."""
    return datetime.fromisoformat(iso_string)


def add_minutes(iso_string: str, minutes: int) -> str:
    """Add minutes to ISO-8601 datetime string."""
    dt = parse_iso_datetime(iso_string)
    new_dt = dt + timedelta(minutes=minutes)
    return new_dt.isoformat()


def add_days(iso_string: str, days: int) -> str:
    """Add days to ISO-8601 datetime string."""
    dt = parse_iso_datetime(iso_string)
    new_dt = dt + timedelta(days=days)
    return new_dt.isoformat()


def add_weeks(iso_string: str, weeks: int) -> str:
    """Add weeks to ISO-8601 datetime string."""
    dt = parse_iso_datetime(iso_string)
    new_dt = dt + timedelta(weeks=weeks)
    return new_dt.isoformat()


def calculate_time_delta_minutes(start_iso: str, end_iso: str) -> float:
    """Calculate time difference in minutes between two ISO-8601 strings."""
    start_dt = parse_iso_datetime(start_iso)
    end_dt = parse_iso_datetime(end_iso)
    delta = end_dt - start_dt
    return delta.total_seconds() / 60.0


def calculate_time_delta_days(start_iso: str, end_iso: str) -> float:
    """Calculate time difference in days between two ISO-8601 strings."""
    start_dt = parse_iso_datetime(start_iso)
    end_dt = parse_iso_datetime(end_iso)
    delta = end_dt - start_dt
    return delta.total_seconds() / 86400.0


def is_time_before(time1_iso: str, time2_iso: str) -> bool:
    """Check if time1 is before time2."""
    dt1 = parse_iso_datetime(time1_iso)
    dt2 = parse_iso_datetime(time2_iso)
    return dt1 < dt2


def is_time_after(time1_iso: str, time2_iso: str) -> bool:
    """Check if time1 is after time2."""
    dt1 = parse_iso_datetime(time1_iso)
    dt2 = parse_iso_datetime(time2_iso)
    return dt1 > dt2
