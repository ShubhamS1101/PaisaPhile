from typing import TypedDict, List, Dict, Optional, Any
from typing_extensions import Annotated


# ============================================================
# RAW DATA CONTEXT (WHAT DATA WAS USED)
# ============================================================

class DataContext(TypedDict):
    """
    Defines ONE precise slice of raw market data.
    """
    key: str
    # "{symbol}|{timeframe}|{start_datetime}:{end_datetime}"

    symbol: str
    timeframe: str
    start_datetime: str      # ISO-8601 with timezone
    end_datetime: str        # ISO-8601 with timezone


# ============================================================
# PER-AGENT OUTPUT WITH ORIGIN TIME
# ============================================================

class AgentOutput(TypedDict):
    result: Dict[str, Any]
    created_at: str          # ISO-8601
    fresh_until: Optional[str]
    model_version: str


# ============================================================
# ANALYSIS RESULT (PER DATA CONTEXT + HORIZON)
# ============================================================

class AnalysisResult(TypedDict, total=False):
    """
    Persistent analytical memory for ONE:
    (DataContext + Horizon)
    """

    horizon: str
    # "intraday" | "swing" | "long_term"

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
    # What RAW DATA is required this turn
    # --------------------------------------------------------

    data_contexts_required: Annotated[
        List[DataContext],
        "Data slices needed for THIS query only"
    ]

    # --------------------------------------------------------
    # What ANALYSES must run this turn
    # --------------------------------------------------------

    analyses_required: Annotated[
        Dict[str, Dict[str, Any]],
        """
        Maps DataContext.key → execution instructions.

        Example:
        {
          "<data_key>": {
              "horizon": "intraday",
              "run": ["indicator", "trend", "decision"]
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
        Temporary OHLCV data keyed by DataContext.key.
        Exists ONLY during agent execution.
        Cleared after agents finish.
        """
    ]

    # ========================================================
    # 3. PERSISTENT ANALYTICAL MEMORY (CROSS-TURN)
    # ========================================================

    analysis_store: Annotated[
        Dict[str, AnalysisResult],
        """
        Persistent cache of ALL analyses.

        Key format:
        "{symbol}|{timeframe}|{start}:{end}|{horizon}"
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
