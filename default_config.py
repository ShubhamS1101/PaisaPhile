DEFAULT_CONFIG = {
    # Agent LLM: For cheap/fast operations (planner, dialogue, decision)
    "agent_llm_model": "gpt-4o-mini",
    "agent_llm_provider": "openai",  # "openai", "anthropic", "qwen", or "gemini"
    "agent_llm_temperature": 0.1,
    
    # Graph LLM: For reasoning/vision operations (indicator, pattern, trend analysis)
    "graph_llm_model": "gpt-4o",
    "graph_llm_provider": "openai",  # "openai", "anthropic", "qwen", or "gemini"
    "graph_llm_temperature": 0.1,
    
    # Conversation Summary LLM: For moderate conversation summarization
    "conversation_summary_llm_model": "gpt-4o-mini",
    "conversation_summary_llm_provider": "openai",  # "openai", "anthropic", "qwen", or "gemini"
    "conversation_summary_llm_temperature": 0.3,
    
    # API Keys
    "api_key": "sk-",  # OpenAI API key
    "anthropic_api_key": "sk-",  # Anthropic API key (optional, can also use ANTHROPIC_API_KEY env var)
    "qwen_api_key": "sk-",  # Qwen API key (optional, can also use DASHSCOPE_API_KEY env var)
    "gemini_api_key": "",  # Gemini API key (optional, can also use GOOGLE_API_KEY env var)
    "conversation_summary_api_key": "",  # Separate API key for conversation summary (optional, defaults to api_key)
}
