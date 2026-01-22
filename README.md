<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="templates/assets/dark_mode_logo/PaisaPhile Logo.png">
  <source media="(prefers-color-scheme: light)" srcset="templates/assets/light_mode_logo/PaisaPhile Logo.png">
  <img alt="PaisaPhile Logo" src="templates/assets/light_mode_logo/PaisaPhile Logo.png" width="300">
</picture>

<h1>PaisaPhile</h1>
<h3>Intelligent Multi-Agent Market Analysis & Trading Assistant</h3>

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Agent Descriptions](#-agent-descriptions)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Usage Examples](#-usage-examples)
- [Configuration](#-configuration)
- [Contributing](#-contributing)
- [Citation & Attribution](#-citation--attribution)
- [License](#-license)

---

## 🎯 Overview

**PaisaPhile** is a sophisticated multi-agent conversational trading analysis system designed to provide interpretable, structured market insights while maintaining strict human oversight. Built on a modular architecture with intelligent caching and freshness tracking, PaisaPhile combines technical analysis, pattern recognition, and trend analysis into a cohesive, conversation-aware framework.

### Purpose

PaisaPhile serves as an **analytical toolkit and advisory assistant**, not an automated trading system. It empowers traders, analysts, and researchers to:

- **Inspect market data** with natural language queries
- **Run comprehensive technical analyses** across multiple timeframes and horizons
- **Generate visual charts** for pattern and trend identification
- **Receive structured trading decisions** with confidence scores and detailed rationale
- **Maintain conversation context** across multi-turn interactions

### Design Philosophy

1. **Modularity**: Each agent has a single, well-defined responsibility
2. **Separation of Concerns**: Analysis, decision-making, and conversation are strictly isolated
3. **Safety First**: Structured outputs prevent accidental automated trading
4. **Intelligent Caching**: Per-agent freshness tracking minimizes redundant computation
5. **Transparency**: Every decision includes detailed reasoning and data provenance

---

## ✨ Key Features

### 🤖 **Conversational Multi-Agent System**

- **Natural Language Interface**: Query markets using plain English
- **Multi-Turn Context**: Maintains conversation history for coherent follow-up interactions
- **Intent Recognition**: Automatically classifies queries as trade decisions, trend analysis, price checks, comparisons, or explanations
- **Adaptive Responses**: Dialogue agent tailors explanations based on available analysis and data

### 📊 **Comprehensive Technical Analysis**

#### Indicator Analysis
- **Momentum Indicators**: RSI, Rate of Change (ROC)
- **Trend Indicators**: MACD with signal line and histogram
- **Volatility Indicators**: Stochastic Oscillator, Williams %R
- **Horizon-Aware Interpretation**: Tailored analysis for intraday, swing, and long-term trading

#### Pattern Recognition
- **Classical Candlestick Patterns**: Engulfing, Doji, Hammer, Shooting Star, etc.
- **Chart Pattern Detection**: Support/resistance breakouts, consolidations
- **Visual Chart Generation**: Automated pattern charts with annotations
- **Vision-Enabled Analysis**: Optional integration with vision-capable LLMs for chart interpretation

#### Trend Analysis
- **Trendline Detection**: Automatic identification of support and resistance
- **Trend Direction Classification**: Uptrend, downtrend, sideways movement
- **Multi-Timeframe Analysis**: Intraday, swing, and long-term trend views
- **Structural Insights**: Key levels, breakout points, and reversal zones

### 🎯 **Structured Decision Synthesis**

- **Non-Conversational Output**: Strict JSON format for downstream integration
- **Decision Types**: Strong Buy, Weak Buy, Neutral, Weak Sell, Strong Sell
- **Confidence Scoring**: 0-100% confidence based on analysis confluence
- **Detailed Rationale**: Per-agent reasoning (indicator, pattern, trend)
- **Risk Assessment**: Explicit risk notes for each decision
- **Auto-Trigger Logic**: Automatically re-runs when upstream analyses update

### 💾 **Intelligent Caching & Freshness**

- **Per-Agent Caching**: Each agent maintains separate cached results
- **Freshness Windows**: Context-aware cache expiration based on timeframe and horizon
- **Automatic Staleness Detection**: Decisions auto-refresh when underlying data changes
- **Selective Recomputation**: Only stale analyses are re-run, minimizing API calls
- **Metadata Tracking**: `created_at`, `ran_at`, `fresh_until` timestamps for every analysis

### 🔄 **Data Context Management**

- **Dual Context System**: Separate data contexts for analysis vs. dialogue
- **Timezone-Aware Datetime Handling**: ISO-8601 format with explicit timezone support
- **API Limit Enforcement**: Automatic validation of Yahoo Finance timeframe constraints
- **Rolling Windows**: Lookback-based data requests for live market conditions
- **Graceful Error Handling**: Clear error messages for failed fetches or invalid symbols

---

## 🏗️ System Architecture

PaisaPhile employs a **directed acyclic graph (DAG)** execution model orchestrated via **LangGraph**. The system consists of seven specialized agents with strict data flow boundaries:

```
┌─────────────────┐
│  User Query     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Planner Agent   │ ◄── Interprets intent, determines required analyses
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Data Fetch      │ ◄── Retrieves market data for specified contexts
└────────┬────────┘
         │
         ├──────────────┬──────────────┬──────────────┐
         ▼              ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Indicator    │ │ Pattern      │ │ Trend        │ │ (Cached)     │
│ Agent        │ │ Agent        │ │ Agent        │ │ Analysis     │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │                │
       └────────────────┴────────────────┴────────────────┘
                        │
                        ▼
               ┌────────────────┐
               │ Decision Agent │ ◄── Synthesizes analyses into structured decision
               └────────┬───────┘
                        │
                        ▼
               ┌────────────────┐
               │ Dialogue Agent │ ◄── Explains results in natural language
               └────────┬───────┘
                        │
                        ▼
               ┌────────────────┐
               │ User Response  │
               └────────────────┘
```

### Execution Flow

1. **Query Interpretation**: Planner agent parses user query and determines intent
2. **Data Specification**: Planner specifies required data contexts (symbol, timeframe, datetime range)
3. **Freshness Check**: Each analysis agent checks if cached results are still fresh
4. **Selective Execution**: Only stale or missing analyses are re-computed
5. **Decision Synthesis**: Decision agent consumes analyses and outputs structured JSON
6. **Conversational Response**: Dialogue agent presents results in user-friendly format
7. **Memory Update**: Conversation context is summarized and stored for next turn

---

## 🤖 Agent Descriptions

### 1. Planner Agent

**Role**: Query Interpretation & Execution Planning

**Responsibilities**:
- Parse natural language queries into structured intent
- Classify intent: `trade`, `trend`, `compare`, `price_check`, `explain`, `clarify`
- Determine required data contexts (symbol, timeframe, datetime range)
- Specify which analyses to run (indicator, pattern, trend, decision)
- Enforce Yahoo Finance API limits (1m: 4 days, 5m: 30 days, 15m: 60 days)
- Handle timezone-aware datetime calculations

**Input**: User query, conversation summary  
**Output**: JSON execution plan with data contexts and analysis requirements

**Key Features**:
- **Conversation-Aware**: Uses memory to infer symbols from context
- **Auto-Clarification**: Requests missing information instead of guessing
- **Horizon Detection**: Automatically classifies as intraday, swing, or long-term
- **Rolling Windows**: Prefers lookback-based requests over fixed session times

---

### 2. Indicator Agent

**Role**: Technical Indicator Computation

**Responsibilities**:
- Compute momentum indicators: RSI, Rate of Change (ROC)
- Compute trend indicators: MACD with signal line and histogram
- Compute volatility indicators: Stochastic Oscillator, Williams %R
- Enforce freshness: 1 candle tolerance per timeframe
- Store structured results with metadata

**Input**: OHLCV data, timeframe, horizon  
**Output**: Indicator values, interpretation, freshness metadata

**Key Features**:
- **Tool-Backed Computation**: Uses LangChain tool calling for reliable calculation
- **Fallback Mechanisms**: Direct computation if LLM fails to call tools
- **Horizon-Specific Interpretation**: Tailored insights for intraday vs. long-term
- **Selective Updates**: Only recomputes if cache is stale

---

### 3. Pattern Agent

**Role**: Candlestick & Chart Pattern Recognition

**Responsibilities**:
- Identify classical candlestick patterns (engulfing, doji, hammer, etc.)
- Detect chart patterns (breakouts, consolidations, reversals)
- Generate annotated pattern charts
- Optional vision-enabled LLM analysis of charts
- Manage chart file storage with standardized naming

**Input**: OHLCV data, timeframe, horizon  
**Output**: Pattern findings, chart path, interpretation, freshness metadata

**Key Features**:
- **Visual Chart Generation**: Produces PNG charts for manual review
- **Vision Integration**: Optionally uses vision-capable LLMs for pattern analysis
- **Pattern Library**: References comprehensive pattern descriptions
- **Chart Management**: Automatic cleanup and versioning of chart files

---

### 4. Trend Agent

**Role**: Trend Direction & Support/Resistance Analysis

**Responsibilities**:
- Identify trend direction (uptrend, downtrend, sideways)
- Detect key support and resistance levels
- Draw trendlines and structural levels
- Generate trend charts with annotations
- Assess trend strength and potential breakouts

**Input**: OHLCV data, timeframe, horizon  
**Output**: Trend direction, support/resistance levels, chart path, interpretation

**Key Features**:
- **Multi-Timeframe Awareness**: Different freshness rules per horizon
- **Structural Analysis**: Identifies key levels and zones
- **Vision-Enabled Interpretation**: Optional chart analysis via vision LLMs
- **Breakout Detection**: Highlights potential trend reversal points

---

### 5. Decision Agent

**Role**: Structured Trading Decision Synthesis

**Responsibilities**:
- Consume indicator, pattern, and trend analyses
- Synthesize findings into structured JSON decision
- Assign decision type: Strong Buy, Weak Buy, Neutral, Weak Sell, Strong Sell
- Calculate confidence score (0-100%) based on analysis confluence
- Provide per-agent reasoning and risk assessment
- **Strictly non-conversational**: Produces JSON only, never talks to user

**Input**: Cached analyses, data contexts, intent  
**Output**: Structured JSON decision with reasoning and metadata

**Key Features**:
- **Auto-Trigger Logic**: Reruns automatically when upstream analyses update
- **Confluence Scoring**: Higher confidence when multiple analyses agree
- **Risk Assessment**: Explicit risk notes for each decision
- **Version Tracking**: Monitors upstream agent versions for staleness detection
- **Safety Bias**: Defaults to HOLD when uncertain or conflicting signals

**Decision Criteria**:
- **BUY**: Bullish confluence across available analyses (confidence ≥ 70% = Strong Buy)
- **SELL**: Bearish confluence across available analyses (confidence ≥ 70% = Strong Sell)
- **HOLD**: Conflicting signals, neutral analyses, or insufficient data

---

### 6. Dialogue Agent

**Role**: User-Facing Conversational Interface

**Responsibilities**:
- Explain cached analyses and decisions in natural language
- Answer follow-up questions and clarifications
- Provide educational context about indicators and patterns
- Present price data in readable format
- **Never runs new analyses or fetches data**: Read-only access to cached results

**Input**: Analysis store, conversation summary, user query  
**Output**: Natural language response

**Key Features**:
- **Adaptive Responses**: Tailors explanation based on available data
- **Educational Mode**: Explains concepts when no analysis is available
- **Data Presentation**: Formats OHLCV data for readability
- **Error Communication**: Clear messages for failed fetches or missing data
- **Context-Aware**: References previous conversation turns

---

### 7. Conversation Memory

**Role**: Context Summarization & Storage

**Responsibilities**:
- Maintain lightweight conversation history
- Summarize multi-turn interactions
- Provide context for follow-up queries
- Track discussed symbols and timeframes

**Key Features**:
- **Compression**: Summarizes long conversations to avoid context overflow
- **Selective Retention**: Keeps recent turns and key decisions
- **Symbol Tracking**: Remembers discussed assets for implicit references

---

## 📦 Installation

### Prerequisites

- Python 3.9 or higher
- pip package manager
- (Optional) Virtual environment tool (venv, conda, poetry)

### Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/PaisaPhile.git
   cd PaisaPhile
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure API keys**:
   - Create a `.env` file in the project root
   - Add your LLM API keys (OpenAI, Anthropic, or other supported providers)
   ```bash
   OPENAI_API_KEY=your_key_here
   # Or for other providers:
   ANTHROPIC_API_KEY=your_key_here
   ```

5. **Verify installation**:
   ```bash
   python testing/test_interactive.py
   ```

---

## 🚀 Quick Start

### Interactive Terminal Mode

```bash
python test_interactive.py
```

Example queries:
```
> Should I buy AAPL for swing trading?
> What's the current price of BTC?
> Compare MSFT vs GOOGL on intraday timeframe
> Explain why you recommended HOLD
```

### Web Interface (Flask)

```bash
python web_interface.py
```

Navigate to `http://localhost:5000` in your browser.

### Programmatic Usage

```python
from graph_main import create_trading_advisor_graph
from langchain_openai import ChatOpenAI

# Initialize LLM
llm = ChatOpenAI(model="gpt-4", temperature=0)

# Create graph
graph = create_trading_advisor_graph(llm)

# Run query
result = graph.invoke({
    "user_query": "Should I buy RELIANCE.NS for intraday?",
    "conversation_summary": "",
    "analysis_store": {},
    "kline_data": {}
})

# Access decision
decision = result["decision_output"]
print(decision)

# Access dialogue response
response = result["conversation_summary"]
print(response)
```

---

## 📖 Usage Examples

### Example 1: Trade Decision Query

**Query**: "Should I buy AAPL for intraday trading?"

**System Behavior**:
1. Planner classifies as `trade` intent with `intraday` horizon
2. Fetches 5-minute OHLCV data for AAPL (last 6 hours)
3. Runs indicator, pattern, and trend agents
4. Decision agent synthesizes to structured JSON
5. Dialogue agent explains recommendation

**Response**:
```
Based on current analysis of AAPL (5m, intraday):

📊 RECOMMENDATION: WEAK BUY
Confidence: 62%

REASONING:
• Indicators: RSI at 58 (neutral momentum), MACD showing bullish crossover
• Patterns: No significant patterns detected
• Trend: Uptrend with support at $175.20

⚠️ RISK NOTES: Limited confluence. Consider waiting for stronger confirmation.
```

---

### Example 2: Price Check Query

**Query**: "What's the current price of BTC?"

**System Behavior**:
1. Planner classifies as `price_check` intent
2. Fetches 1-day OHLCV data for BTC (last 2 days)
3. Dialogue agent presents price data (no analysis needed)

**Response**:
```
💰 BTC | 1d

2026-01-21
• Open: $42,350.12
• High: $43,120.50
• Low: $42,100.00
• Close: $42,890.75
• Volume: 15,234,567

2026-01-22
• Open: $42,890.75
• High: $43,500.00
• Low: $42,750.00
• Close: $43,200.00
• Volume: 18,456,789

Period Change: +$849.88 (+2.01%)
```

---

### Example 3: Comparison Query

**Query**: "Compare MSFT vs GOOGL for swing trading"

**System Behavior**:
1. Planner classifies as `compare` intent with `swing` horizon
2. Fetches 1-hour data for both MSFT and GOOGL (last 7 days)
3. Runs parallel analyses for both symbols
4. Decision agent produces separate decisions
5. Dialogue agent presents comparative summary

**Response**:
```
📊 MSFT vs GOOGL Comparison (1h, swing)

MSFT: STRONG BUY (78% confidence)
• Indicators: RSI 65, MACD bullish, Stochastic oversold recovery
• Patterns: Bullish engulfing on daily chart
• Trend: Clear uptrend with strong support at $380

GOOGL: HOLD (45% confidence)
• Indicators: RSI 52 (neutral), MACD flat
• Patterns: Consolidation pattern forming
• Trend: Sideways movement, no clear direction

RECOMMENDATION: MSFT shows stronger setup for swing entry.
```

---

### Example 4: Follow-Up Question (Explain Intent)

**Previous Context**: User received HOLD recommendation for TSLA

**Query**: "Why did you recommend HOLD? The price is going up!"

**System Behavior**:
1. Planner classifies as `explain` intent (no new analysis)
2. Dialogue agent accesses cached analyses
3. Provides detailed explanation using existing data

**Response**:
```
I understand your concern. While the price is indeed rising, here's why I recommended HOLD:

1. CONFLICTING SIGNALS:
   • RSI at 72 indicates overbought conditions (potential reversal)
   • Price increase lacks volume confirmation
   • MACD histogram showing divergence (weakening momentum)

2. PATTERN ANALYSIS:
   • Forming a potential double top pattern
   • Resistance at $245 has rejected price 3 times

3. RISK ASSESSMENT:
   • Current rally may be exhaustion move
   • Better entry opportunity likely after pullback

SUGGESTION: Wait for price to consolidate or pull back to $235 support before entering.

This is a cautious stance to protect against buying at local top. If you're already in the trade, consider taking partial profits.
```

---

## ⚙️ Configuration

### Freshness Rules

Configure cache expiration in `freshness_config.py`:

```python
FRESHNESS_CONFIG = {
    "indicator": {
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "1d": timedelta(days=1)
    },
    "pattern": {
        "intraday": timedelta(hours=2),
        "swing": timedelta(days=1),
        "long_term": timedelta(days=3)
    },
    "trend": {
        "intraday": timedelta(hours=4),
        "swing": timedelta(days=2),
        "long_term": timedelta(days=7)
    }
}
```

### LLM Configuration

Specify models in `default_config.py`:

```python
LLM_CONFIG = {
    "tool_llm": "gpt-4-turbo",  # For indicator/pattern/trend tools
    "graph_llm": "gpt-4-vision",  # For chart analysis
    "decision_llm": "gpt-4",  # For decision synthesis
    "dialogue_llm": "gpt-4"  # For conversational responses
}
```

### Timeframe Limits

Adjust API limits in `planner_agent.py`:

```python
TIMEFRAME_LIMITS = {
    "1m": {"max_days": 4, "min_end_offset_minutes": 5},
    "5m": {"max_days": 30, "min_end_offset_minutes": 10},
    "15m": {"max_days": 60, "min_end_offset_minutes": 30},
    "1h": {"max_days": 730},
    "1d": {"max_days": None}  # No limit
}
```

---

## 🤝 Contributing

We welcome contributions! Please follow these guidelines:

### Development Setup

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Install dev dependencies: `pip install -r requirements-dev.txt`
4. Make your changes with tests
5. Run tests: `pytest testing/`
6. Submit a pull request

### Contribution Areas

- **New Indicators**: Add tools in `graph_util.py`
- **Pattern Detection**: Enhance pattern library in `pattern_agent_new.py`
- **Visualization**: Improve chart generation in `chart_manager.py`
- **Agent Logic**: Refine agent prompts and decision criteria
- **Documentation**: Improve docs, add examples, fix typos

### Code Style

- Follow PEP 8 conventions
- Add docstrings to all functions
- Include type hints where applicable
- Write unit tests for new features

---

## 📚 Citation & Attribution

PaisaPhile was developed as an evolution of the **QuantAgent** project, originally created by researchers at Stony Brook University, Carnegie Mellon University, University of British Columbia, Yale University, and Fudan University.

### Original QuantAgent Paper

```bibtex
@article{xiong2024quantagent,
  title={QuantAgent: Price-Driven Multi-Agent LLMs for High-Frequency Trading},
  author={Xiong, Fei and Zhang, Xiang and Feng, Aosong and Sun, Siqi and You, Chenyu},
  journal={arXiv preprint arXiv:2509.09995},
  year={2024},
  url={https://arxiv.org/abs/2509.09995}
}
```

### Key References

- **QuantAgent Project**: [https://Y-Research-SBU.github.io/QuantAgent](https://Y-Research-SBU.github.io/QuantAgent)
- **QuantAgent Repository**: [https://github.com/Y-Research-SBU/QuantAgent](https://github.com/Y-Research-SBU/QuantAgent)
- **Research Paper**: [https://arxiv.org/abs/2509.09995](https://arxiv.org/abs/2509.09995)

### PaisaPhile Evolution

PaisaPhile builds upon QuantAgent's foundational multi-agent architecture with the following enhancements:

1. **Conversational Interface**: Added multi-turn dialogue with conversation memory
2. **Intelligent Caching**: Implemented per-agent freshness tracking and selective recomputation
3. **Strict Separation**: Isolated decision synthesis from conversational explanation
4. **Vision Integration**: Added optional vision-enabled chart analysis
5. **Horizon Awareness**: Introduced semantic trading horizons (intraday, swing, long-term)
6. **Enhanced Safety**: Structured JSON decisions prevent accidental automated trading

**Acknowledgment**: We thank the QuantAgent team for their pioneering work in applying multi-agent LLM systems to financial analysis. PaisaPhile would not exist without their foundational contributions.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### Disclaimer

**IMPORTANT**: PaisaPhile is provided for **research and educational purposes only**.

- ❌ **NOT FINANCIAL ADVICE**: This system does not provide licensed financial advice
- ❌ **NO GUARANTEES**: Past performance does not indicate future results
- ❌ **USE AT YOUR OWN RISK**: Trading involves substantial risk of loss
- ✅ **EDUCATIONAL TOOL**: Designed for learning and research, not live trading
- ✅ **HUMAN OVERSIGHT**: Always validate outputs before making trading decisions

**The developers assume no liability for financial losses incurred through the use of this software.**

---

## 🛠️ Troubleshooting

### Common Issues

**Issue**: "No data available for symbol"  
**Solution**: Ensure you're using correct Yahoo Finance ticker symbols (e.g., AAPL, BTC-USD, RELIANCE.NS)

**Issue**: "Analysis cache is stale"  
**Solution**: This is expected behavior. The system will automatically recompute stale analyses.

**Issue**: "LLM did not call any tools"  
**Solution**: Check your LLM configuration. Some models require explicit tool calling instructions.

**Issue**: "Chart generation failed"  
**Solution**: Ensure matplotlib and required image libraries are installed: `pip install matplotlib pillow`

### Getting Help

- **Documentation**: See `info/` directory for detailed architecture docs
- **Issues**: Open a GitHub issue with error logs and reproduction steps
- **Discussions**: Join community discussions for usage questions

---

## 🔗 Additional Resources

### Documentation
- [Architecture Overview](info/ARCHITECTURE.md)
- [Implementation Summary](info/IMPLEMENTATION_SUMMARY.md)
- [Quick Start Guide](info/QUICKSTART.md)
- [LLM Configuration](info/LLM_CONFIGURATION.md)

### Community
- **GitHub Discussions**: For feature requests and general questions
- **Issues**: For bug reports and technical problems

---

<div align="center">

**Built with ❤️ for the trading and research community**

If you find PaisaPhile useful, please ⭐ star the repository and cite the original QuantAgent paper!

</div>
