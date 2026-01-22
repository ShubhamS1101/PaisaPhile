"""
TradingGraph: Orchestrates the multi-agent trading system using LangChain and LangGraph.
Initializes LLMs, toolkits, and agent nodes for indicator, pattern, and trend analysis.
"""

import os
from typing import Dict

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_qwq import ChatQwen
from langgraph.prebuilt import ToolNode

from default_config import DEFAULT_CONFIG
from graph_main import TradingGraphV2
from graph_util import TechnicalTools


class TradingGraph:
    """
    Main orchestrator for the multi-agent trading system.
    Sets up LLMs, toolkits, and agent nodes for indicator, pattern, and trend analysis.
    """

    def __init__(self, config=None):
        # --- Configuration and LLMs ---
        self.config = config if config is not None else DEFAULT_CONFIG.copy()

        # Initialize LLMs with provider support
        self.agent_llm = self._create_llm(
            provider=self.config.get("agent_llm_provider", "openai"),
            model=self.config.get("agent_llm_model", "gpt-4o-mini"),
            temperature=self.config.get("agent_llm_temperature", 0.1),
        )
        self.graph_llm = self._create_llm(
            provider=self.config.get("graph_llm_provider", "openai"),
            model=self.config.get("graph_llm_model", "gpt-4o"),
            temperature=self.config.get("graph_llm_temperature", 0.1),
        )
        self.conversation_summary_llm = self._create_llm(
            provider=self.config.get("conversation_summary_llm_provider", "openai"),
            model=self.config.get("conversation_summary_llm_model", "gpt-4o-mini"),
            temperature=self.config.get("conversation_summary_llm_temperature", 0.3),
            use_conversation_api_key=True,
        )
        self.toolkit = TechnicalTools()

        # --- Create tool nodes for each agent ---
        # self.tool_nodes = self._set_tool_nodes()

        # --- Graph logic and setup ---
        # Use TradingGraphV2 from graph_main which has all the latest fixes
        self.graph = TradingGraphV2(
            config=self.config,
            agent_llm=self.agent_llm,
            graph_llm=self.graph_llm,
            conversation_summary_llm=self.conversation_summary_llm,
            toolkit=self.toolkit
        ).set_graph()

    def _get_api_key(self, provider: str = "openai", use_conversation_api_key: bool = False) -> str:
        """
        Get API key with proper validation and error handling.
        
        Args:
            provider: The provider name ("openai", "anthropic", or "qwen")
            use_conversation_api_key: If True, use conversation_summary_api_key (falls back to default)
        
        Returns:
            str: The API key for the specified provider
            
        Raises:
            ValueError: If API key is missing or invalid
        """
        if provider == "openai":
            # First check if API key is provided in config
            if use_conversation_api_key:
                api_key = self.config.get("conversation_summary_api_key") or self.config.get("api_key")
            else:
                api_key = self.config.get("api_key")
            
            # If not in config, check environment variable
            if not api_key:
                api_key = os.environ.get("OPENAI_API_KEY")
            
            # Validate the API key
            if not api_key:
                raise ValueError(
                    "OpenAI API key not found. Please set it using one of these methods:\n"
                    "1. Set environment variable: export OPENAI_API_KEY='your-key-here'\n"
                    "2. Update the config with: config['api_key'] = 'your-key-here'\n"
                    "3. Use the web interface to update the API key"
                )
            
            if api_key == "your-openai-api-key-here" or api_key == "":
                raise ValueError(
                    "Please replace the placeholder API key with your actual OpenAI API key. "
                    "You can get one from: https://platform.openai.com/api-keys"
                )
        elif provider == "anthropic":
            # First check if API key is provided in config
            api_key = self.config.get("anthropic_api_key")
            
            # If not in config, check environment variable
            if not api_key:
                api_key = os.environ.get("ANTHROPIC_API_KEY")
            
            # Validate the API key
            if not api_key:
                raise ValueError(
                    "Anthropic API key not found. Please set it using one of these methods:\n"
                    "1. Set environment variable: export ANTHROPIC_API_KEY='your-key-here'\n"
                    "2. Update the config with: config['anthropic_api_key'] = 'your-key-here'\n"
                )
            
            if api_key == "":
                raise ValueError(
                    "Please provide your actual Anthropic API key. "
                    "You can get one from: https://console.anthropic.com/"
                )
        elif provider == "qwen":
            # First check if API key is provided in config
            api_key = self.config.get("qwen_api_key")
            
            # If not in config, check environment variable
            if not api_key:
                api_key = os.environ.get("DASHSCOPE_API_KEY")
            
            # Validate the API key
            if not api_key:
                raise ValueError(
                    "Qwen API key not found. Please set it using one of these methods:\n"
                    "1. Set environment variable: export DASHSCOPE_API_KEY='your-key-here'\n"
                    "2. Update the config with: config['qwen_api_key'] = 'your-key-here'\n"
                )
            
            if api_key == "":
                raise ValueError(
                    "Please provide your actual Qwen API key. "
                    "You can get one from: https://dashscope.console.aliyun.com/"
                )
        elif provider == "gemini":
            # First check if API key is provided in config
            api_key = self.config.get("gemini_api_key")
            
            # If not in config, check environment variable
            if not api_key:
                api_key = os.environ.get("GOOGLE_API_KEY")
            
            # Validate the API key
            if not api_key:
                raise ValueError(
                    "Gemini API key not found. Please set it using one of these methods:\n"
                    "1. Set environment variable: export GOOGLE_API_KEY='your-key-here'\n"
                    "2. Update the config with: config['gemini_api_key'] = 'your-key-here'\n"
                )
            
            if api_key == "":
                raise ValueError(
                    "Please provide your actual Gemini API key. "
                    "You can get one from: https://makersuite.google.com/app/apikey"
                )
        else:
            raise ValueError(f"Unsupported provider: {provider}. Must be 'openai', 'anthropic', 'qwen', or 'gemini'")
        
        return api_key

    def _create_llm(
        self, provider: str, model: str, temperature: float, use_conversation_api_key: bool = False
    ) -> BaseChatModel:
        """
        Create an LLM instance based on the provider.
        
        Args:
            provider: The provider name ("openai", "anthropic", or "qwen")
            model: The model name (e.g., "gpt-4o", "claude-3-5-sonnet-20241022", "qwen-vl-max-latest")
            temperature: The temperature setting for the model
            use_conversation_api_key: If True, use conversation_summary_api_key
            
        Returns:
            BaseChatModel: An instance of the appropriate LLM class
        """
        api_key = self._get_api_key(provider, use_conversation_api_key)
        
        if provider == "openai":
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                api_key=api_key,
            )
        elif provider == "anthropic":
            # ChatAnthropic handles SystemMessage extraction automatically
            # It extracts SystemMessage from the message list and passes it as 'system' parameter
            # The messages array should contain at least one non-SystemMessage
            return ChatAnthropic(
                model=model,
                temperature=temperature,
                api_key=api_key,
            )
        elif provider == "qwen":
            return ChatQwen(
                model=model,
                temperature=temperature,
                api_key=api_key,
                max_retries=4,
            )
        elif provider == "gemini":
            return ChatGoogleGenerativeAI(
                model=model,
                temperature=temperature,
                google_api_key=api_key,
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}. Must be 'openai', 'anthropic', 'qwen', or 'gemini'")

    # def _set_tool_nodes(self) -> Dict[str, ToolNode]:
    #     """
    #     Define tool nodes for each agent type (indicator, pattern, trend).
    #     """
    #     return {
    #         "indicator": ToolNode(
    #             [
    #                 self.toolkit.compute_macd,
    #                 self.toolkit.compute_roc,
    #                 self.toolkit.compute_rsi,
    #                 self.toolkit.compute_stoch,
    #                 self.toolkit.compute_willr,
    #             ]
    #         ),
    #         "pattern": ToolNode(
    #             [
    #                 self.toolkit.generate_kline_image,
    #             ]
    #         ),
    #         "trend": ToolNode([self.toolkit.generate_trend_image]),
    #     }

    def refresh_llms(self):
        """
        Refresh the LLM objects with the current API key from environment.
        This is called when the API key is updated.
        """
        # Recreate LLM objects with current config values
        self.agent_llm = self._create_llm(
            provider=self.config.get("agent_llm_provider", "openai"),
            model=self.config.get("agent_llm_model", "gpt-4o-mini"),
            temperature=self.config.get("agent_llm_temperature", 0.1),
        )
        self.graph_llm = self._create_llm(
            provider=self.config.get("graph_llm_provider", "openai"),
            model=self.config.get("graph_llm_model", "gpt-4o"),
            temperature=self.config.get("graph_llm_temperature", 0.1),
        )
        self.conversation_summary_llm = self._create_llm(
            provider=self.config.get("conversation_summary_llm_provider", "openai"),
            model=self.config.get("conversation_summary_llm_model", "gpt-4o-mini"),
            temperature=self.config.get("conversation_summary_llm_temperature", 0.3),
            use_conversation_api_key=True,
        )

        # Recreate the graph with new LLMs
        self.graph = TradingGraphV2(
            config=self.config,
            agent_llm=self.agent_llm,
            graph_llm=self.graph_llm,
            conversation_summary_llm=self.conversation_summary_llm,
            toolkit=self.toolkit
        ).set_graph()

    def update_api_key(self, api_key: str, provider: str = "openai"):
        """
        Update the API key in the config and refresh LLMs.
        This method is called by the web interface when API key is updated.
        
        Args:
            api_key (str): The new API key
            provider (str): The provider name ("openai" or "anthropic"), defaults to "openai"
        """
        if provider == "openai":
            # Update the config with the new API key
            self.config["api_key"] = api_key
            
            # Also update the environment variable for consistency
            os.environ["OPENAI_API_KEY"] = api_key
        elif provider == "anthropic":
            # Update the config with the new API key
            self.config["anthropic_api_key"] = api_key
            
            # Also update the environment variable for consistency
            os.environ["ANTHROPIC_API_KEY"] = api_key
        elif provider == "qwen":
            # Update the config with the new API key
            self.config["qwen_api_key"] = api_key
            
            # Also update the environment variable for consistency
            os.environ["DASHSCOPE_API_KEY"] = api_key
        elif provider == "gemini":
            # Update the config with the new API key
            self.config["gemini_api_key"] = api_key
            
            # Also update the environment variable for consistency
            os.environ["GOOGLE_API_KEY"] = api_key
        else:
            raise ValueError(f"Unsupported provider: {provider}. Must be 'openai', 'anthropic', 'qwen', or 'gemini'")
        
        # Refresh the LLMs with the new API key
        self.refresh_llms()

    def prepare_context(self, kline_data: dict, time_frame: str, stock_name: str, 
                       pattern_image: str = None, trend_image: str = None) -> dict:
        """
        Prepare market context WITHOUT running analysis.
        This is called when ticker/timeframe is selected.
        
        Args:
            kline_data: OHLCV data dictionary
            time_frame: Timeframe string (e.g., "4h", "1d")
            stock_name: Stock/ticker name
            pattern_image: Optional pre-generated pattern image
            trend_image: Optional pre-generated trend image
            
        Returns:
            State dict with context_ready=True and should_analyze=False
        """
        initial_state = {
            "context_ready": True,
            "should_analyze": False,  # Do NOT run agents
            "user_query": None,
            "kline_data": kline_data,
            "time_frame": time_frame,
            "stock_name": stock_name,
            "pattern_image": pattern_image or "",
            "trend_image": trend_image or "",
            "messages": [],
            "analysis_results": None,
        }
        
        # Run graph - will hit router and go straight to END
        final_state = self.graph.invoke(initial_state)
        return final_state

    def run_analysis(self, state: dict) -> dict:
        """
        Run full analysis on prepared context.
        This is called when user asks a query that requires analysis.
        
        Args:
            state: Existing state with context_ready=True
            
        Returns:
            State dict with analysis results
        """
        # Update state to trigger analysis
        state["should_analyze"] = True
        
        # Run graph - will execute all agents
        final_state = self.graph.invoke(state)
        return final_state
