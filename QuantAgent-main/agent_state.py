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
    # 1. MARKET CONTEXT (SYSTEM-owned)
    # These fields are managed by the system/data fetcher
    # ========================================================================
    user_query: Annotated[
            str,
            "Current user query for this turn only (cleared after planning)"
    ]
    
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
    
    context_ready: Annotated[
        bool,
        "True when market data has been fetched and is ready for analysis"
    ]

    # ========================================================================
    # 2. MARKET DATA (SYSTEM-owned)
    # Populated by data fetcher, consumed by agents
    # ========================================================================
    
    kline_data_map: Annotated[
        Dict[str, dict],
        "Map of symbol -> OHLCV data. Key: ticker, Value: {Datetime, Open, High, Low, Close, Volume}"
    ]

    # ========================================================================
    # 3. PLANNER OUTPUT (PLANNER-owned)
    # Set by planner agent after interpreting user query
    # ========================================================================
    
    intent: Annotated[
        str,
        "User intent: 'analyze', 'explain', 'compare', 'clarify', or 'chat'"
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
    # 4. ANALYSIS CACHE (AGENT-owned)
    # Updated by respective agents, persists across turns
    # ========================================================================
    
    indicators: Annotated[
        Dict[str, Any],
        "Cached indicator analysis results. Key: symbol, Value: {rsi, macd, stoch, etc.}"
    ]
    
    trend: Annotated[
        Dict[str, Any],
        "Cached trend analysis results. Key: symbol, Value: {trend_report, trend_image, etc.}"
    ]
    
    pattern: Annotated[
        Dict[str, Any],
        "Cached pattern analysis results. Key: symbol, Value: {pattern_report, pattern_image, etc.}"
    ]

    # ========================================================================
    # 5. DECISION LAYER (DECISION AGENT-owned)
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
    # 6. CONVERSATION MEMORY (SYSTEM/PLANNER-owned)
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
