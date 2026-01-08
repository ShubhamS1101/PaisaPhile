from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage


# ============================================================================
# NEW UNIFIED STATE FOR CONVERSATIONAL TRADING ADVISOR
# ============================================================================

class LookbackWindow(TypedDict, total=False):
    days: int
    hours: int
    minutes: int


class TradingAdvisorState(TypedDict):
    """
    Unified state for conversational trading advisor system.
    Supports multi-turn dialogue, dynamic data fetching, and intelligent routing.
    """

    # ========================================================================
    # 1. PER-QUERY EXECUTION FIELDS (RESET EVERY TURN)
    # These fields control routing and execution for the current query ONLY
    # They are cleared at the start of each new user query
    # ========================================================================
    
    user_query: Annotated[
        str,
        """
        Current user query for this turn only.
        RESET at the start of each new query.
        Used by planner to determine intent and routing.
        """
    ]
    
    data_required_keys: Annotated[
        List[str],
        """
        List of data cache keys that need to be fetched for this query.
        Format: ["{symbol}|{timeframe}|{start_date}:{end_date}", ...]
        Example: ["AAPL|1d|2024-01-01:2025-01-01", "BTC-USD|1h|2026-01-01:2026-01-02"]
        
        RESET every turn by planner based on current query requirements.
        Used by router to determine which data to fetch.
        NOT passed to LLMs - internal routing only.
        """
    ]
    
    required_analysis_keys: Annotated[
        Dict[str, List[str]],
        """
        Maps data keys to required analysis types for this query.
        Format: {"{symbol}|{timeframe}|{start}:{end}": ["indicator", "pattern", "trend"]}
        Example: {
            "AAPL|1d|2024-01-01:2025-01-01": ["indicator", "trend", "decision"],
            "BTC-USD|1h|2026-01-01:2026-01-02": ["pattern", "decision"]
        }
        
        RESET every turn by planner based on required_analyses field.
        Used by router to determine which agents to invoke.
        NOT passed to LLMs - internal routing only.
        """
    ]

    # ========================================================================
    # 2. MARKET CONTEXT (PLANNER-owned, per-turn)
    # These fields are set by planner for the current query
    # ========================================================================
    
    data_requirement: Annotated[
        str,
        "One of: 'required' | 'optional' | 'not_required'"
    ]

    symbols: Annotated[
        List[str], 
        "List of ticker symbols to analyze (e.g., ['BTC-USD', 'AAPL'])"
    ]
    
    horizon: Annotated[
        str,
        "Trading horizon: intraday | swing | long_term"
    ]
    
    timeframe: Annotated[
        Optional[str],
        "Chart timeframe (e.g., 5m | 15m | 1h | 4h | 1d | 1w). Set by planner or system."
    ]
    
    start_date: Annotated[
        Optional[str],
        "Start date for historical data in YYYY-MM-DD format"
    ]
    
    end_date: Annotated[
        Optional[str],
        "End date for historical data in YYYY-MM-DD format"
    ]
    
    mode: Annotated[
        str,
        "Analysis mode: 'single' (one symbol), 'comparison' (multiple symbols), 'split' (different timeframes)"
    ]
    
    required_analyses: Annotated[
        List[str],
        "List of analyses to run: ['indicator', 'pattern', 'trend', 'decision'] or subset"
    ]

    # ========================================================================
    # 3. MARKET DATA (SYSTEM-owned, persistent)
    # Populated by data fetcher, consumed by agents
    # ========================================================================
    
    kline_data_map: Annotated[
        Dict[str, dict],
        "Map of symbol -> OHLCV data. Key: ticker, Value: {Datetime, Open, High, Low, Close, Volume}"
    ]
    
    context_ready: Annotated[
        bool,
        "True when market data has been fetched and is ready for analysis"
    ]

    # ========================================================================
    # 4. PLANNER OUTPUT (PLANNER-owned, per-turn)
    # Set by planner agent after interpreting user query
    # ========================================================================
    
    intent: Annotated[
        str,
        "User intent: 'trade', 'trend', 'compare', 'explain', 'historical', 'price_check', 'clarify'"
    ]
    
    need_clarification: Annotated[
        bool,
        "True if planner needs more information from user"
    ]

    # ========================================================================
    # 5. PERSISTENT ANALYSIS STORE (CROSS-TURN CACHE)
    # Structured storage for all analysis results, keyed by context
    # ========================================================================
    
    analysis_store: Annotated[
        Dict[str, Dict[str, Any]],
        """
        Persistent analysis cache keyed by: '{symbol}|{timeframe}|{start_date}:{end_date}'
        
        Structure for each key:
        {
            "symbol": str,              # e.g., "BEL.NS"
            "timeframe": str,           # e.g., "15m"
            "start_date": str,          # e.g., "2026-01-01"
            "end_date": str,            # e.g., "2026-01-02"
            "indicator": Optional[dict],  # Indicator analysis results
            "pattern": Optional[dict],    # Pattern analysis results
            "trend": Optional[dict],      # Trend analysis results
            "decision": Optional[dict],   # Decision results
            "metadata": {
                "horizon": str,         # e.g., "intraday"
                "created_at": str       # ISO timestamp
            }
        }
        
        Rules:
        - Analysis agents update ONLY their respective fields
        - Persists across queries within the same conversation
        - Never flushed unless conversation ends
        - No raw market data stored here (only analysis results)
        """
    ]

    # ========================================================================
    # 6. LEGACY ANALYSIS CACHE (AGENT-owned, DEPRECATED)
    # Kept for backward compatibility during migration
    # ========================================================================
    
    indicators: Annotated[
        Dict[str, Any],
        "DEPRECATED - Use analysis_store instead. Cached indicator analysis results."
    ]
    
    trend: Annotated[
        Dict[str, Any],
        "DEPRECATED - Use analysis_store instead. Cached trend analysis results."
    ]
    
    pattern: Annotated[
        Dict[str, Any],
        "DEPRECATED - Use analysis_store instead. Cached pattern analysis results."
    ]

    # ========================================================================
    # 7. DECISION LAYER (DECISION AGENT-owned)
    # Final trading recommendation and reasoning
    # ========================================================================
    
    decision: Annotated[
        Optional[str],
        "Final trading decision: 'BUY', 'SELL', 'HOLD', or None if not yet decided"
    ]
    
    explanation: Annotated[
        Optional[str],
        "Detailed explanation of the decision or answer to user query"
    ]

    # ========================================================================
    # 8. CONVERSATION MEMORY (SYSTEM/PLANNER-owned)
    # Maintains context across multiple turns
    # ========================================================================
    
    conversation_summary: Annotated[
        str,
        "Summary of conversation history for context continuity"
    ]
    
    user_preferences: Annotated[
        Dict[str, str],
        "Learned user preferences (e.g., preferred timeframe, risk tolerance, favorite symbols)"
    ]
    
    # DO NOT STORE RAW MESSAGE HISTORY
    # Reason: Storing List[BaseMessage] or raw chat history is forbidden for safety and compactness.
    #         Only a rolling summary is kept for context continuity.


# ============================================================================
# LEGACY STATE (kept for backward compatibility)
# ============================================================================

class IndicatorAgentState(TypedDict):
    """State type for the Indicator Agent including messages, input data, and analysis result."""

    # Control flags
    context_ready: Annotated[
        bool, "True when ticker/timeframe selected and data fetched, ready for user query"
    ]
    user_query: Annotated[
        str, "User's natural language query or question"
    ]
    should_analyze: Annotated[
        bool, "True if agents should run analysis, False if just setting context"
    ]

    # Market data context
    kline_data: Annotated[
        dict, "OHLCV dictionary used for computing technical indicators"
    ]
    time_frame: Annotated[str, "time period for k line data provided"]
    stock_name: Annotated[dict, "stock name for prompt"]

    # Indicator Agent Tools output values (explicitly added per indicator)
    rsi: Annotated[List[float], "Relative Strength Index values"]
    macd: Annotated[List[float], "MACD line values"]
    macd_signal: Annotated[List[float], "MACD signal line values"]
    macd_hist: Annotated[List[float], "MACD histogram values"]
    stoch_k: Annotated[List[float], "Stochastic Oscillator %K values"]
    stoch_d: Annotated[List[float], "Stochastic Oscillator %D values"]
    roc: Annotated[List[float], "Rate of Change values"]
    willr: Annotated[List[float], "Williams %R values"]
    indicator_report: Annotated[
        str, "Final indicator agent summary report to be used by downstream agents"
    ]

    # Pattern Agent
    pattern_image: Annotated[
        str, "Base64-encoded K-line chart for pattern recognition agent use"
    ]
    pattern_image_filename: Annotated[
        str, "Local file path to saved K-line chart image"
    ]
    pattern_image_description: Annotated[
        str, "Brief description of the generated K-line image"
    ]
    pattern_report: Annotated[
        str, "Final pattern agent summary report to be used by downstream agents"
    ]

    # Trend Agent
    trend_image: Annotated[
        str,
        "Base64-encoded trend-annotated candlestick (K-line) chart for trend recognition agent use",
    ]
    trend_image_filename: Annotated[
        str, "Local file path to saved trendline-enhanced K-line chart image"
    ]
    trend_image_description: Annotated[
        str,
        "Brief description of the chart, including presence of support/resistance lines and visual characteristics",
    ]
    trend_report: Annotated[
        str,
        "Final trend analysis summary, describing structure, directional bias, and technical observations for downstream agents",
    ]

    # Final analysis and messaging context
    analysis_results: Annotated[str, "Computed result of the analysis or decision"]
    messages: Annotated[
        List[BaseMessage], "List of chat messages used in LLM prompt construction"
    ]
    decision_prompt: Annotated[str, "decision prompt for reflection"]
    final_trade_decision: Annotated[
        str, "Final BUY or SELL decision made after analyzing indicators"
    ]
