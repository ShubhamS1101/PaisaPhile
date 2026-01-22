import base64
import json
import os
from pathlib import Path
from typing import Any, Dict

from flask import Flask, jsonify, request, send_file, send_from_directory

from trading_graph import TradingGraph

app = Flask(__name__, static_folder='ui', static_url_path='/static/ui')


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
    return send_from_directory('ui', 'index.html')


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
        
        # For each data context that was analyzed
        for ctx_key, spec in analyses_required.items():
            print(f"\n   Processing context: {ctx_key}")
            print(f"   Spec: {spec}")
            
            # Parse context key: "symbol|timeframe|start:end"
            parts = ctx_key.split("|")
            if len(parts) != 3:
                print(f"   ⚠️  Invalid context key format (expected 3 parts, got {len(parts)})")
                continue
            
            symbol = parts[0]
            timeframe = parts[1]
            datetime_range = parts[2]
            horizon = spec.get("horizon", "")
            
            if not horizon:
                print(f"   ⚠️  No horizon in spec")
                continue
            
            # Build store key with horizon: "symbol|timeframe|start:end|horizon"
            store_key = f"{symbol}|{timeframe}|{datetime_range}|{horizon}"
            print(f"   Looking for store_key: {store_key}")
            
            # Get analysis entry
            entry = analysis_store.get(store_key)
            if not entry:
                print(f"   ⚠️  No entry found in analysis_store")
                # Try to find any matching key (fuzzy match)
                for key in analysis_store.keys():
                    if symbol in key and timeframe in key and horizon in key:
                        print(f"   💡 Found similar key: {key}")
                        entry = analysis_store[key]
                        break
            
            if not entry:
                print(f"   ❌ No matching entry found")
                continue
            
            print(f"   ✓ Found entry with agents: {list(entry.keys())}")
            
            # Check if pattern agent was assigned and has chart
            if "pattern" in spec.get("run", []):
                print(f"   🔍 Checking pattern agent...")
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
                    else:
                        print(f"      ⚠️  Chart path missing or file doesn't exist")
            
            # Check if trend agent was assigned and has chart
            if "trend" in spec.get("run", []):
                print(f"   🔍 Checking trend agent...")
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
                    else:
                        print(f"      ⚠️  Chart path missing or file doesn't exist")
        
        print(f"\n   📊 Total charts to send: {len(charts)}")
        
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
        
        # Graph stays initialized - no need to reinit
        # This allows continuing with same settings but fresh state
        
        return jsonify({
            "success": True,
            "message": "Session reset successfully. Analysis cache and conversation history cleared."
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    """Serve static assets from the assets folder."""
    try:
        return send_file(f"assets/{filename}")
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
