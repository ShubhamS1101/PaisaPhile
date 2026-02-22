from typing import TypedDict, List, Dict, Optional, Any, Literal
from typing_extensions import Annotated


# ============================================================
# WINDOW SPECIFICATION (WHAT THE PLANNER REQUESTS)
# ============================================================

class WindowSpec(TypedDict, total=False):
    """
    Defines ONE analysis window requested by the planner.
    This is the planner's output — it says WHAT is needed,
    not whether it exists or is fresh.
    """
    symbol: str
    timeframe: str
    horizon: str             # "intraday" | "swing" | "long_term"
    window_type: str         # "ROLLING" | "HISTORICAL"
    lookback: str            # e.g. "3y", "6m", "100C" (ROLLING only)
    start: str               # e.g. "2024-01-01" (HISTORICAL only)
    end: str                 # e.g. "2024-06-30" (HISTORICAL only)


# ============================================================
# PER-AGENT OUTPUT WITH ORIGIN TIME
# ============================================================

class AgentOutput(TypedDict, total=False):
    result: Dict[str, Any]
    created_at: str          # ISO-8601
    fresh_until: Optional[str]
    model_version: str
    metadata: Dict[str, Any] # Per-component snapshot metadata
                             # (data_window_start, data_window_end, candles_used, etc.)


# ============================================================
# ANALYSIS RESULT (PER WINDOW)
# ============================================================

class AnalysisResult(TypedDict, total=False):
    """
    Persistent analytical memory for ONE window.

    Window identity is semantic:
      ROLLING:    "{symbol}|{timeframe}|ROLLING|{horizon}|{lookback}"
      HISTORICAL: "{symbol}|{timeframe}|HISTORICAL|{start}:{end}|{horizon}"

    Exact data timestamps live INSIDE each component's metadata,
    NOT in the window key.
    """

    # Window-level metadata
    status: str              # "active" | "archive"
    last_accessed: str       # ISO-8601 — for LRU eviction

    # Fetched data timestamps (set by fetch node after yfinance download)
    fetched_start: Optional[str]     # First candle timestamp (ISO-8601)
    fetched_end: Optional[str]       # Last candle timestamp (ISO-8601)
    candles_fetched: Optional[int]   # Number of candles fetched

    # Per-agent outputs
    indicator: Optional[AgentOutput]
    pattern: Optional[AgentOutput]
    trend: Optional[AgentOutput]
    decision: Optional[AgentOutput]


# ============================================================
# TRADING ADVISOR STATE (FINAL)
# ============================================================

class TradingAdvisorState(TypedDict):
    """
    Production-grade state for a conversational agentic trading system.
    """

    # ========================================================
    # 1. PER-TURN EXECUTION STATE (RESET EVERY QUERY)
    # ========================================================

    user_query: Annotated[
        Optional[str],
        "User input for the current turn only"
    ]

    intent: Annotated[
        str,
        "trade | trend | compare | explain | historical | price_check | clarify"
    ]

    need_clarification: Annotated[
        bool,
        "Planner requires more information"
    ]

    # --------------------------------------------------------
    # What WINDOWS are needed this turn (planner output)
    # --------------------------------------------------------

    windows_required: Annotated[
        List[WindowSpec],
        "Window specifications requested by planner for THIS query"
    ]

    # --------------------------------------------------------
    # What ANALYSES must run this turn (resolved by infra)
    # --------------------------------------------------------

    analyses_required: Annotated[
        Dict[str, Dict[str, Any]],
        """
        Maps window_id → execution instructions.
        Built by window manager + freshness checker, NOT by planner.

        Example:
        {
          "BEL.NS|1d|ROLLING|long_term|3y": {
              "run": ["indicator", "decision"],
              "data_needed": true
          }
        }
        """
    ]

    # ========================================================
    # 2. TEMPORARY MARKET DATA (SYSTEM-OWNED)
    # ========================================================

    kline_data: Annotated[
        Dict[str, Dict[str, Any]],
        """
        Temporary OHLCV data keyed by window_id or data_id.
        Exists ONLY during agent execution.
        Cleared after agents finish.
        """
    ]

    # --------------------------------------------------------
    # Raw data requests (bypass analysis, go to dialogue)
    # --------------------------------------------------------

    data_required: Annotated[
        List[Dict[str, str]],
        """
        Simple data fetch requests for dialogue (e.g. price_check).
        Each entry: {"data_id": "AAPL_1d_20260222T...", "symbol": "AAPL", "timeframe": "1d"}
        data_id format: {symbol}_{timeframe}_{iso_timestamp}
        Fetched data lands in kline_data[data_id].
        """
    ]

    # ========================================================
    # 3. PERSISTENT ANALYTICAL MEMORY (CROSS-TURN)
    # ========================================================

    analysis_store: Annotated[
        Dict[str, AnalysisResult],
        """
        Persistent cache of ALL analysis windows.

        Key formats:
          ROLLING:    "{symbol}|{timeframe}|ROLLING|{horizon}|{lookback}"
          HISTORICAL: "{symbol}|{timeframe}|HISTORICAL|{start}:{end}|{horizon}"
        """
    ]

    # ========================================================
    # 4. PER-TURN USER RESPONSE
    # ========================================================

    explanation: Annotated[
        Optional[str],
        "Final conversational response for this turn"
    ]

    # ========================================================
    # 5. CONVERSATIONAL MEMORY
    # ========================================================

    conversation_summary: Annotated[
        str,
        "Compressed rolling summary of the conversation"
    ]

    user_preferences: Annotated[
        Dict[str, Any],
        "Learned user preferences"
    ]

    # ========================================================
    # 6. CONVERSATIONAL CONVENIENCE FIELDS (per-turn, for memory)
    # ========================================================

    symbols: Annotated[
        List[str],
        "Symbols discussed this turn (extracted from windows_required + data_required)"
    ]

    horizon: Annotated[
        Optional[str],
        "Primary horizon this turn (intraday | swing | long_term)"
    ]

    decision: Annotated[
        Optional[Dict[str, Any]],
        "Latest decision result this turn (set by decision agent)"
    ]
