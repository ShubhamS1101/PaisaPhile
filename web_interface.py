import atexit
import base64
import json
import os
import shutil
import signal
from pathlib import Path
from typing import Any, Dict

from flask import Flask, jsonify, request, send_file, send_from_directory

from trading_graph import TradingGraph


# ================================
# CLEANUP UTILITIES
# ================================

def flush_charts() -> None:
    """Clear all chart files in output/charts."""
    charts_dir = Path("output/charts")
    if charts_dir.exists():
        for subdir in ["pattern", "trend"]:
            subpath = charts_dir / subdir
            if subpath.exists():
                for file in subpath.glob("*.png"):
                    try:
                        file.unlink()
                    except Exception as e:
                        print(f"⚠️ Failed to delete chart {file}: {e}")
        print("🗑️ Charts flushed")


def flush_debug_output() -> None:
    """Clear debug_output folder contents."""
    debug_dir = Path("debug_output")
    if debug_dir.exists():
        for file in debug_dir.iterdir():
            try:
                if file.is_file():
                    file.unlink()
                elif file.is_dir():
                    shutil.rmtree(file)
            except Exception as e:
                print(f"⚠️ Failed to delete debug file {file}: {e}")
        print("🗑️ Debug output flushed")


def flush_data() -> None:
    """Clear data folder contents (record.csv, etc.)."""
    data_dir = Path("data")
    if data_dir.exists():
        for file in data_dir.iterdir():
            try:
                if file.is_file():
                    file.unlink()
                elif file.is_dir():
                    shutil.rmtree(file)
            except Exception as e:
                print(f"⚠️ Failed to delete data file {file}: {e}")
        print("🗑️ Data flushed")


def flush_conversation_state() -> None:
    """Flush charts and debug_output when conversation ends."""
    flush_charts()
    flush_debug_output()
    print("✅ Conversation state cleaned up")


def shutdown_cleanup() -> None:
    """Cleanup handler for when the web interface stops."""
    print("\n🛑 Web interface shutting down - cleaning up...")
    flush_conversation_state()
    print("✅ Shutdown cleanup complete")


# Register shutdown handlers
atexit.register(shutdown_cleanup)

app = Flask(__name__, static_folder='static/ui', static_url_path='/static/ui')


def get_default_model(provider: str, llm_type: str) -> str:
    """Get default model name based on provider and LLM type."""
    defaults = {
        "openai": {
            "agent": "gpt-4o-mini",
            "graph": "gpt-4o",
            "conversation": "gpt-4o-mini"
        },
        "anthropic": {
            "agent": "claude-haiku-4-5-20251001",
            "graph": "claude-sonnet-4-5-20251022",
            "conversation": "claude-haiku-4-5-20251001"
        },
        "gemini": {
            "agent": "gemini-2.5-flash",
            "graph": "gemini-2.5-flash",
            "conversation": "gemini-2.5-flash"
        },
        "qwen": {
            "agent": "qwen-flash",
            "graph": "qwen-max",
            "conversation": "qwen-flash"
        }
    }
    
    provider_defaults = defaults.get(provider, defaults["openai"])
    return provider_defaults.get(llm_type, provider_defaults["agent"])


class WebTradingAnalyzer:
    def __init__(self):
        """Initialize the web trading analyzer."""
        from default_config import DEFAULT_CONFIG
        # Start with default config
        self.config = DEFAULT_CONFIG.copy()
        # Create graph using the same method as test_interactive
        self.graph = None
        self._initialize_graph()
        
    def _initialize_graph(self):
        """Initialize the trading graph (same as test_interactive)."""
        from graph_main import create_trading_graph
        try:
            self.graph = create_trading_graph(self.config)
            print("✅ Graph initialized successfully")
        except Exception as e:
            print(f"❌ Failed to initialize graph: {e}")
            raise

    def validate_api_key(self, provider: str = None) -> Dict[str, Any]:
        """Validate the current API key by making a simple test call."""
        try:
            # Get provider from config if not provided
            if provider is None:
                provider = self.config.get("agent_llm_provider", "openai")
            
            if provider == "openai":
                from openai import OpenAI
                client = OpenAI()
                
                # Make a simple test call
                _ = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "Hello"}],
                    max_tokens=5,
                )
                
                provider_name = "OpenAI"
            elif provider == "anthropic":
                from anthropic import Anthropic
                api_key = os.environ.get("ANTHROPIC_API_KEY") or self.config.get("anthropic_api_key", "")
                if not api_key:
                    return {
                        "valid": False,
                        "error": "❌ Invalid API Key: The Anthropic API key is not set. Please update it in the Settings section.",
                    }
                
                client = Anthropic(api_key=api_key)
                
                # Make a simple test call
                _ = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=5,
                    messages=[{"role": "user", "content": "Hello"}],
                )
                
                provider_name = "Anthropic"
            elif provider == "qwen":
                from langchain_qwq import ChatQwen
                api_key = os.environ.get("DASHSCOPE_API_KEY") or self.config.get("qwen_api_key", "")
                if not api_key:
                    return {
                        "valid": False,
                        "error": "❌ Invalid API Key: The Qwen API key is not set. Please update it in the Settings section.",
                    }
                
                # Make a simple test call using LangChain
                llm = ChatQwen(model="qwen-flash", api_key=api_key)
                _ = llm.invoke([("user", "Hello")])
                
                provider_name = "Qwen"
            elif provider == "gemini":
                import google.generativeai as genai
                api_key = os.environ.get("GOOGLE_API_KEY") or self.config.get("gemini_api_key", "")
                if not api_key:
                    return {
                        "valid": False,
                        "error": "❌ Invalid API Key: The Gemini API key is not set. Please update it in the Settings section.",
                    }
                
                # Configure and make a simple test call
                genai.configure(api_key=api_key)
                # Use the stable gemini-1.5-flash or gemini-pro model for validation
                model = genai.GenerativeModel('gemini-2.5-flash')
                _ = model.generate_content("Hello", generation_config={"max_output_tokens": 5})
                
                provider_name = "Gemini"
            else:
                return {
                    "valid": False,
                    "error": f"❌ Unsupported provider: {provider}"
                }
            return {"valid": True, "message": f"{provider_name} API key is valid"}

        except Exception as e:
            error_msg = str(e)
            
            # Determine provider name for error messages
            if provider is None:
                provider = self.config.get("agent_llm_provider", "openai")
            if provider == "openai":
                provider_name = "OpenAI"
            elif provider == "anthropic":
                provider_name = "Anthropic"
            elif provider == "qwen":
                provider_name = "Qwen"
            else:
                provider_name = "Gemini"

            if (
                "authentication" in error_msg.lower()
                or "invalid api key" in error_msg.lower()
                or "api key not valid" in error_msg.lower()
                or "api_key_invalid" in error_msg.lower()
                or "401" in error_msg
                or "invalid_api_key" in error_msg.lower()
                or "permission_denied" in error_msg.lower()
            ):
                return {
                    "valid": False,
                    "error": f"❌ Invalid API Key: The {provider_name} API key is invalid or has expired. Please update it in the Settings section.",
                }
            elif "rate limit" in error_msg.lower() or "429" in error_msg or "resource_exhausted" in error_msg.lower():
                return {
                    "valid": False,
                    "error": f"⚠️ Rate Limit Exceeded: You've hit the {provider_name} API rate limit. Please wait a moment and try again.",
                }
            elif "not found" in error_msg.lower() or "404" in error_msg or "does not exist" in error_msg.lower():
                return {
                    "valid": False,
                    "error": f"❌ Model Not Found: The requested model is not available. Full error: {error_msg}",
                }
            elif "quota" in error_msg.lower() or "billing" in error_msg.lower():
                return {
                    "valid": False,
                    "error": f"💳 Billing Issue: Your {provider_name} account has insufficient credits or billing issues. Please check your {provider_name} account.",
                }
            elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                return {
                    "valid": False,
                    "error": f"🌐 Network Error: Unable to connect to {provider_name} servers. Please check your internet connection.",
                }
            else:
                return {"valid": False, "error": f"❌ Error: {error_msg}"}


# Initialize the analyzer
analyzer = WebTradingAnalyzer()


@app.route("/")
def index():
    """Main landing page - new organized UI."""
    return send_from_directory('static/ui', 'index.html')


@app.route("/api/validate-api-key", methods=["POST"])
def validate_api_key():
    """API endpoint to validate an API key."""
    try:
        data = request.get_json() or {}
        api_key = data.get("api_key")
        provider = data.get("provider", "openai")
        
        if not api_key:
            return jsonify({"valid": False, "error": "API key is required"})
        
        # Temporarily set the API key for validation
        old_key = None
        if provider == "openai":
            old_key = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = api_key
        elif provider == "anthropic":
            old_key = os.environ.get("ANTHROPIC_API_KEY")
            os.environ["ANTHROPIC_API_KEY"] = api_key
        elif provider == "qwen":
            old_key = os.environ.get("DASHSCOPE_API_KEY")
            os.environ["DASHSCOPE_API_KEY"] = api_key
        elif provider == "gemini":
            old_key = os.environ.get("GOOGLE_API_KEY")
            os.environ["GOOGLE_API_KEY"] = api_key
        
        validation = analyzer.validate_api_key(provider=provider)
        
        # Restore old key
        if old_key:
            if provider == "openai":
                os.environ["OPENAI_API_KEY"] = old_key
            elif provider == "anthropic":
                os.environ["ANTHROPIC_API_KEY"] = old_key
            elif provider == "qwen":
                os.environ["DASHSCOPE_API_KEY"] = old_key
            elif provider == "gemini":
                os.environ["GOOGLE_API_KEY"] = old_key
        
        return jsonify(validation)
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)})


@app.route("/api/chat", methods=["POST"])
def chat():
    """API endpoint for conversational chat interface."""
    import time
    import threading
    request_id = f"req_{int(time.time() * 1000)}_{threading.get_ident()}"
    print(f"\n🌐 [{request_id}] NEW API CALL")
    
    try:
        data = request.get_json()
        user_message = data.get("message", "").strip()
        config_update = data.get("config")
        is_settings_update = data.get("is_settings_update", False)
        
        print(f"   [{request_id}] Message: {user_message[:50]}...")
        
        if not user_message:
            return jsonify({"error": "Message is required"}), 400
        
        # Update config if provided
        if config_update:
            # Handle agent provider and API key
            if "agent_provider" in config_update:
                provider = config_update["agent_provider"]
                analyzer.config["agent_llm_provider"] = provider
                
                if "agent_api_key" in config_update and config_update["agent_api_key"]:
                    api_key = config_update["agent_api_key"]
                    if provider == "openai":
                        os.environ["OPENAI_API_KEY"] = api_key
                        analyzer.config["api_key"] = api_key
                    elif provider == "anthropic":
                        os.environ["ANTHROPIC_API_KEY"] = api_key
                        analyzer.config["anthropic_api_key"] = api_key
                    elif provider == "qwen":
                        os.environ["DASHSCOPE_API_KEY"] = api_key
                        analyzer.config["qwen_api_key"] = api_key
                    elif provider == "gemini":
                        os.environ["GOOGLE_API_KEY"] = api_key
                        analyzer.config["gemini_api_key"] = api_key
            
            # Handle graph provider and API key
            if "graph_provider" in config_update:
                provider = config_update["graph_provider"]
                analyzer.config["graph_llm_provider"] = provider
                
                if "graph_api_key" in config_update and config_update["graph_api_key"]:
                    api_key = config_update["graph_api_key"]
                    if provider == "openai":
                        os.environ["OPENAI_API_KEY"] = api_key
                        analyzer.config["api_key"] = api_key
                    elif provider == "anthropic":
                        os.environ["ANTHROPIC_API_KEY"] = api_key
                        analyzer.config["anthropic_api_key"] = api_key
                    elif provider == "qwen":
                        os.environ["DASHSCOPE_API_KEY"] = api_key
                        analyzer.config["qwen_api_key"] = api_key
                    elif provider == "gemini":
                        os.environ["GOOGLE_API_KEY"] = api_key
                        analyzer.config["gemini_api_key"] = api_key
            
            # Handle conversation provider and API key
            if "conversation_provider" in config_update:
                provider = config_update["conversation_provider"]
                analyzer.config["conversation_summary_llm_provider"] = provider
                
                if "conversation_api_key" in config_update and config_update["conversation_api_key"]:
                    api_key = config_update["conversation_api_key"]
                    if provider == "openai":
                        os.environ["OPENAI_API_KEY"] = api_key
                        analyzer.config["conversation_summary_api_key"] = api_key
                    elif provider == "anthropic":
                        os.environ["ANTHROPIC_API_KEY"] = api_key
                        analyzer.config["conversation_summary_api_key"] = api_key
                    elif provider == "qwen":
                        os.environ["DASHSCOPE_API_KEY"] = api_key
                        analyzer.config["conversation_summary_api_key"] = api_key
                    elif provider == "gemini":
                        os.environ["GOOGLE_API_KEY"] = api_key
                        analyzer.config["conversation_summary_api_key"] = api_key
            
            # Set model names with provider-specific defaults
            if "agent_model" in config_update:
                model = config_update["agent_model"]
                if model:
                    analyzer.config["agent_llm_model"] = model
                else:
                    provider = analyzer.config.get("agent_llm_provider", "openai")
                    default_model = get_default_model(provider, "agent")
                    analyzer.config["agent_llm_model"] = default_model
            
            if "graph_model" in config_update:
                model = config_update["graph_model"]
                if model:
                    analyzer.config["graph_llm_model"] = model
                else:
                    provider = analyzer.config.get("graph_llm_provider", "openai")
                    default_model = get_default_model(provider, "graph")
                    analyzer.config["graph_llm_model"] = default_model
            
            if "conversation_model" in config_update:
                model = config_update["conversation_model"]
                if model:
                    analyzer.config["conversation_summary_llm_model"] = model
                else:
                    provider = analyzer.config.get("conversation_summary_llm_provider", "openai")
                    default_model = get_default_model(provider, "conversation")
                    analyzer.config["conversation_summary_llm_model"] = default_model
                
# Reinitialize graph with new config (PRESERVE persistent state)
                # Save current persistent state before reinit
                saved_persistent_state = None
                if hasattr(analyzer, 'persistent_state'):
                    saved_persistent_state = analyzer.persistent_state.copy()
                    print(f"\n💾 Preserving persistent state during settings update:")
                    print(f"   Analysis store entries: {len(saved_persistent_state.get('analysis_store', {}))}")
                    print(f"   Conversation summary length: {len(saved_persistent_state.get('conversation_summary', ''))}")
                
                analyzer._initialize_graph()
                
                # Restore persistent state after reinit
                if saved_persistent_state:
                    analyzer.persistent_state = saved_persistent_state
                    print(f"   ✅ Persistent state restored - conversation can continue")
        
        # Process the user message through the trading graph
        # The system will determine if analysis is needed based on the query
        
        # Initialize persistent state (should be maintained across conversation)
        if not hasattr(analyzer, 'persistent_state'):
            analyzer.persistent_state = {
                "analysis_store": {},
                "conversation_summary": "",
                "user_preferences": {}
            }
        
        # Create state for this query (only include persistent fields)
        initial_state = {
            "user_query": user_message,
            "analysis_store": analyzer.persistent_state.get("analysis_store", {}),
            "conversation_summary": analyzer.persistent_state.get("conversation_summary", ""),
            "user_preferences": analyzer.persistent_state.get("user_preferences", {}),
            # Clear temporary fields from previous turn
            "kline_data": {},
            "explanation": None,
            "intent": None,
            "analyses_required": {},
            "data_contexts_required": [],
        }
        
        # Run the trading graph (same as test_interactive)
        print(f"\n   [{request_id}] Starting graph execution...")
        print(f"   Config: agent={analyzer.config.get('agent_llm_provider')}, graph={analyzer.config.get('graph_llm_provider')}")
        print(f"   State keys: {list(initial_state.keys())}")
        
        try:
            final_state = analyzer.graph.invoke(initial_state)
            print(f"   [{request_id}] ✅ Graph execution completed\n")
        except Exception as e:
            print(f"   [{request_id}] ❌ Graph execution failed: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # Update persistent state for next query
        analyzer.persistent_state["analysis_store"] = final_state.get("analysis_store", {})
        analyzer.persistent_state["conversation_summary"] = final_state.get("conversation_summary", "")
        analyzer.persistent_state["user_preferences"] = final_state.get("user_preferences", {})
        
        print(f"\n💾 Persistent State Updated:")
        print(f"   Analysis store entries: {len(analyzer.persistent_state['analysis_store'])}")
        for key in list(analyzer.persistent_state['analysis_store'].keys())[:3]:
            print(f"   - {key}")
        
        # Extract response
        response = final_state.get("explanation", "I'm ready to help with your trading analysis.")
        
        # Extract chart paths from analysis_store based on analyses_required
        charts = []
        analyses_required = final_state.get("analyses_required", {})
        analysis_store = final_state.get("analysis_store", {})
        
        print(f"\n📊 Chart Extraction:")
        print(f"   Analyses required: {len(analyses_required)} contexts")
        print(f"   Analysis store: {len(analysis_store)} entries")
        if analysis_store:
            print(f"   Analysis store keys:")
            for key in list(analysis_store.keys())[:5]:
                print(f"      - {key}")
                entry = analysis_store[key]
                print(f"        Agents: {list(entry.keys())}")
        
        # Extract charts directly from analysis_store - agents remove themselves from "run" list after executing
        # So we check the store directly for pattern/trend agents with chart_path
        for store_key, entry in analysis_store.items():
            # Parse store key: "symbol|timeframe|datetime_range|horizon"
            parts = store_key.split("|")
            if len(parts) != 4:
                continue
            
            symbol = parts[0]
            timeframe = parts[1]
            horizon = parts[3]
            
            print(f"\n   Checking store entry: {store_key}")
            print(f"   Available agents: {list(entry.keys())}")
            
            # Check for pattern chart
            pattern_output = entry.get("pattern", {})
            if pattern_output:
                pattern_result = pattern_output.get("result", {})
                chart_path = pattern_result.get("chart_path", "")
                print(f"      Pattern chart_path: {chart_path}")
                
                if chart_path and os.path.exists(chart_path):
                    try:
                        with open(chart_path, "rb") as f:
                            pattern_base64 = base64.b64encode(f.read()).decode('utf-8')
                            charts.append({
                                "type": "pattern",
                                "data": f"data:image/png;base64,{pattern_base64}",
                                "caption": f"📊 Pattern Analysis: {symbol} ({timeframe}, {horizon})"
                            })
                            print(f"      ✅ Pattern chart added")
                    except Exception as e:
                        print(f"      ❌ Error loading pattern chart: {e}")
                elif chart_path:
                    print(f"      ⚠️  Pattern chart file doesn't exist: {chart_path}")
            
            # Check for trend chart
            trend_output = entry.get("trend", {})
            if trend_output:
                trend_result = trend_output.get("result", {})
                chart_path = trend_result.get("chart_path", "")
                print(f"      Trend chart_path: {chart_path}")
                
                if chart_path and os.path.exists(chart_path):
                    try:
                        with open(chart_path, "rb") as f:
                            trend_base64 = base64.b64encode(f.read()).decode('utf-8')
                            charts.append({
                                "type": "trend",
                                "data": f"data:image/png;base64,{trend_base64}",
                                "caption": f"📈 Trend Analysis: {symbol} ({timeframe}, {horizon})"
                            })
                            print(f"      ✅ Trend chart added")
                    except Exception as e:
                        print(f"      ❌ Error loading trend chart: {e}")
                elif chart_path:
                    print(f"      ⚠️  Trend chart file doesn't exist: {chart_path}")
        
        print(f"\n   📊 Total charts to send: {len(charts)}")
        
        # Flush data folder only after successful query
        flush_data()
        
        return jsonify({
            "success": True,
            "response": response,
            "charts": charts
        })
        
    except Exception as e:
        error_msg = str(e)
        
        # Determine which provider failed based on error message
        provider_name = "the LLM provider"
        
        # Check error message for provider-specific keywords
        if "openai" in error_msg.lower():
            provider_name = "OpenAI"
        elif "anthropic" in error_msg.lower() or "claude" in error_msg.lower():
            provider_name = "Anthropic"
        elif "gemini" in error_msg.lower() or "google" in error_msg.lower():
            provider_name = "Gemini"
        elif "qwen" in error_msg.lower() or "dashscope" in error_msg.lower():
            provider_name = "Qwen"
        else:
            # Fallback to checking config
            agent_provider = analyzer.config.get("agent_llm_provider", "")
            graph_provider = analyzer.config.get("graph_llm_provider", "")
            conv_provider = analyzer.config.get("conversation_summary_llm_provider", "")
            
            if agent_provider == "gemini" or graph_provider == "gemini" or conv_provider == "gemini":
                provider_name = "Gemini"
            elif agent_provider == "anthropic" or graph_provider == "anthropic" or conv_provider == "anthropic":
                provider_name = "Anthropic"
            elif agent_provider == "qwen" or graph_provider == "qwen" or conv_provider == "qwen":
                provider_name = "Qwen"
            elif agent_provider == "openai" or graph_provider == "openai" or conv_provider == "openai":
                provider_name = "OpenAI"
        
        if (
            "authentication" in error_msg.lower()
            or "invalid api key" in error_msg.lower()
            or "401" in error_msg
            or "invalid_api_key" in error_msg.lower()
            or "api key not valid" in error_msg.lower()
        ):
            return jsonify({
                "success": False,
                "error": f"❌ Invalid API Key: The {provider_name} API key is invalid or has expired. Please check your API key and try again."
            })
        elif "rate limit" in error_msg.lower() or "429" in error_msg:
            return jsonify({
                "success": False,
                "error": f"⚠️ Rate Limit Exceeded: You've hit the {provider_name} API rate limit. Please wait a moment and try again."
            })
        else:
            return jsonify({
                "success": False,
                "error": f"❌ Error: {error_msg}"
            })


@app.route("/api/configure", methods=["POST"])
def configure():
    """API endpoint to update LLM settings with validation."""
    try:
        data = request.get_json()
        llm_settings = data.get("llm_settings", {})
        
        if not llm_settings:
            return jsonify({"success": False, "error": "No settings provided"})
        
        validation_errors = []
        
        # Validate and update agent settings
        if "agent" in llm_settings:
            agent = llm_settings["agent"]
            provider = agent.get("provider", "openai")
            api_key = agent.get("api_key", "")
            
            if api_key:
                # Validate the API key
                validation = _validate_api_key_internal(provider, api_key)
                if not validation["valid"]:
                    validation_errors.append(f"Agent LLM: {validation['error']}")
                else:
                    # Only apply if valid
                    analyzer.config["agent_llm_provider"] = provider
                    if agent.get("model"):
                        analyzer.config["agent_llm_model"] = agent["model"]
                    _set_api_key_env(provider, api_key)
        
        # Validate and update graph settings
        if "graph" in llm_settings:
            graph = llm_settings["graph"]
            provider = graph.get("provider", "openai")
            api_key = graph.get("api_key", "")
            
            if api_key:
                validation = _validate_api_key_internal(provider, api_key)
                if not validation["valid"]:
                    validation_errors.append(f"Graph LLM: {validation['error']}")
                else:
                    analyzer.config["graph_llm_provider"] = provider
                    if graph.get("model"):
                        analyzer.config["graph_llm_model"] = graph["model"]
                    _set_api_key_env(provider, api_key)
        
        # Validate and update conversation settings
        if "conversation" in llm_settings:
            conv = llm_settings["conversation"]
            provider = conv.get("provider", "openai")
            api_key = conv.get("api_key", "")
            
            if api_key:
                validation = _validate_api_key_internal(provider, api_key)
                if not validation["valid"]:
                    validation_errors.append(f"Conversation LLM: {validation['error']}")
                else:
                    analyzer.config["conversation_summary_llm_provider"] = provider
                    if conv.get("model"):
                        analyzer.config["conversation_summary_llm_model"] = conv["model"]
                    _set_api_key_env(provider, api_key)
        
        # If any validation errors, return them
        if validation_errors:
            return jsonify({
                "success": False, 
                "error": "API key validation failed:\n" + "\n".join(validation_errors)
            })
        
        # Reinitialize graph with new config
        analyzer._initialize_graph()
        
        print(f"\n⚙️ Settings updated via /api/configure")
        print(f"   Agent: {analyzer.config.get('agent_llm_provider')} / {analyzer.config.get('agent_llm_model')}")
        print(f"   Graph: {analyzer.config.get('graph_llm_provider')} / {analyzer.config.get('graph_llm_model')}")
        print(f"   Conversation: {analyzer.config.get('conversation_summary_llm_provider')} / {analyzer.config.get('conversation_summary_llm_model')}")
        
        return jsonify({"success": True, "message": "Settings updated successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


def _validate_api_key_internal(provider: str, api_key: str) -> Dict[str, Any]:
    """Internal helper to validate API key for a provider."""
    try:
        if provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            _ = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5,
            )
            return {"valid": True}
        elif provider == "anthropic":
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key)
            _ = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=5,
                messages=[{"role": "user", "content": "Hello"}],
            )
            return {"valid": True}
        elif provider == "qwen":
            from langchain_qwq import ChatQwen
            llm = ChatQwen(model="qwen-flash", api_key=api_key)
            _ = llm.invoke([("user", "Hello")])
            return {"valid": True}
        elif provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
            _ = model.generate_content("Hello", generation_config={"max_output_tokens": 5})
            return {"valid": True}
        else:
            return {"valid": False, "error": f"Unsupported provider: {provider}"}
    except Exception as e:
        error_msg = str(e)
        if "authentication" in error_msg.lower() or "invalid api key" in error_msg.lower() or "401" in error_msg:
            return {"valid": False, "error": "Invalid API key"}
        elif "rate limit" in error_msg.lower() or "429" in error_msg:
            return {"valid": False, "error": "Rate limit exceeded"}
        else:
            return {"valid": False, "error": error_msg[:100]}


def _set_api_key_env(provider: str, api_key: str) -> None:
    """Set API key in environment and config."""
    if provider == "openai":
        os.environ["OPENAI_API_KEY"] = api_key
        analyzer.config["api_key"] = api_key
    elif provider == "anthropic":
        os.environ["ANTHROPIC_API_KEY"] = api_key
        analyzer.config["anthropic_api_key"] = api_key
    elif provider == "qwen":
        os.environ["DASHSCOPE_API_KEY"] = api_key
        analyzer.config["qwen_api_key"] = api_key
    elif provider == "gemini":
        os.environ["GOOGLE_API_KEY"] = api_key
        analyzer.config["gemini_api_key"] = api_key


@app.route("/api/reset-session", methods=["POST"])
def reset_session():
    """API endpoint to reset the conversation session (clears history and analysis store)."""
    try:
        # Clear persistent state completely
        if hasattr(analyzer, 'persistent_state'):
            print(f"\n🗑️ Resetting session - clearing all state")
            print(f"   Clearing {len(analyzer.persistent_state.get('analysis_store', {}))} analysis entries")
            analyzer.persistent_state = {
                "analysis_store": {},
                "conversation_summary": "",
                "user_preferences": {}
            }
        
        # Flush charts and debug_output when starting new chat
        flush_conversation_state()
        
        # Graph stays initialized - no need to reinit
        # This allows continuing with same settings but fresh state
        
        return jsonify({
            "success": True,
            "message": "Session reset successfully. Analysis cache, charts, and debug output cleared."
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })


@app.route("/api/flush-session", methods=["POST"])
def flush_session():
    """API endpoint to flush conversation state (called on tab close/unload)."""
    try:
        flush_conversation_state()
        return jsonify({"success": True, "message": "Session flushed successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    """Serve static assets from the assets folder."""
    try:
        return send_file(f"assets/{filename}")
    except FileNotFoundError:
        return jsonify({"error": "Asset not found"}), 404


@app.route("/templates/assets/<path:subpath>")
def serve_template_assets(subpath):
    """Serve static assets from the templates/assets folder."""
    try:
        return send_file(f"templates/assets/{subpath}")
    except FileNotFoundError:
        return jsonify({"error": "Asset not found"}), 404


if __name__ == "__main__":
    # Create templates directory if it doesn't exist
    templates_dir = Path("templates")
    templates_dir.mkdir(exist_ok=True)

    # Create static directory if it doesn't exist
    static_dir = Path("static")
    static_dir.mkdir(exist_ok=True)
    
    # Create UI directory symlink or serve it directly
    ui_dir = Path("ui")
    ui_dir.mkdir(exist_ok=True)
    
    # Serve UI static files through Flask static folder
    static_ui = static_dir / "ui"
    if not static_ui.exists():
        import shutil
        if ui_dir.exists():
            shutil.copytree(ui_dir / "css", static_ui / "css", dirs_exist_ok=True)
            shutil.copytree(ui_dir / "js", static_ui / "js", dirs_exist_ok=True)

    app.run(debug=True, host="127.0.0.1", port=5000)
