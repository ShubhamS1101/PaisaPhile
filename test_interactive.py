"""
Interactive Conversational Testing - Full System with Memory

This script provides a while-loop interface to test:
1. Persistent analysis_store across multiple queries
2. Conversational memory (summary updates)
3. Decision staleness detection
4. Cached analysis reuse
5. Natural follow-up questions

Type your queries and watch the system maintain context!
Type 'exit', 'quit', or 'q' to end the conversation.
"""

import sys
import os
# Add parent directory to path so we can import modules from the main directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from graph_main import create_trading_graph
import json
import shutil

# Configuration
config = {
    "agent_llm_model": "gemini-2.5-flash",
    "graph_llm_model": "gemini-2.5-flash",
    "agent_llm_provider": "gemini",
    "graph_llm_provider": "gemini",
    "agent_llm_temperature": 0.1,
    "graph_llm_temperature": 0.1,
    "conversation_summary_llm_provider": "gemini",
    "conversation_summary_llm_model": "gemini-2.5-flash",
    "conversation_summary_llm_temperature": 0.3,
    "gemini_api_key": "AIzaSyCCCoHv7PNNuvMOy-mdi_boZAeY0DOp-8I",
}

def cleanup_output_folders():
    """Clean up output and debug folders when conversation ends."""
    folders_to_clean = [
        "output/charts",
        "debug_output"
    ]
    
    print("\n🧹 Cleaning up output folders...")
    
    for folder in folders_to_clean:
        if os.path.exists(folder):
            try:
                # Remove all files in the folder
                for filename in os.listdir(folder):
                    file_path = os.path.join(folder, filename)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                print(f"   ✓ Cleaned {folder}/")
            except Exception as e:
                print(f"   ⚠️  Could not clean {folder}/: {e}")
        else:
            print(f"   ℹ️  {folder}/ does not exist")
    
    print("✅ Cleanup complete!\n")


def print_separator(title=""):
    """Print a nice separator."""
    if title:
        print(f"\n{'='*80}")
        print(f" {title}")
        print(f"{'='*80}\n")
    else:
        print(f"{'='*80}\n")

def print_state_summary(state):
    """Print a compact summary of current state."""
    print(f"\n{'─'*80}")
    print("📊 STATE SUMMARY:")
    print(f"{'─'*80}")
    
    # Analysis store
    store = state.get("analysis_store", {})
    if store:
        print(f"🗄️  Analysis Store: {len(store)} entries")
        for key in list(store.keys())[:3]:  # Show first 3
            agents = list(store[key].keys())
            print(f"   - {key}: [{', '.join(agents)}]")
        if len(store) > 3:
            print(f"   ... +{len(store) - 3} more contexts")
    else:
        print("🗄️  Analysis Store: Empty")
    
    # Conversation memory
    summary = state.get("conversation_summary", "")
    if summary:
        lines = summary.strip().splitlines()
        print(f"\n💬 Conversation Memory ({len(lines)} lines):")
        for line in lines[:3]:  # Show first 3 lines
            print(f"   {line}")
        if len(lines) > 3:
            print(f"   ... +{len(lines) - 3} more lines")
    else:
        print("\n💬 Conversation Memory: Empty")
    
    print(f"{'─'*80}\n")

def main():
    """Main interactive loop."""
    print_separator("🤖 TRADING AGENTIC SYSTEM - INTERACTIVE MODE")
    
    print("Welcome to the interactive trading advisor!")
    print("This system maintains context across your conversation.")
    print()
    print("💡 Try queries like:")
    print("   - Should I buy AAPL for intraday?")
    print("   - What about MSFT for swing trading?")
    print("   - Explain the RSI indicator")
    print("   - What was my last decision for AAPL?")
    print()
    print("Type 'exit', 'quit', or 'q' to end the conversation.")
    print_separator()
    
    # Initialize graph
    print("⚙️  Initializing trading graph...")
    try:
        graph = create_trading_graph(config)
        print("✅ Graph initialized successfully!\n")
    except Exception as e:
        print(f"❌ Failed to initialize graph: {e}")
        return
    
    # Initialize persistent state
    state = {
        "analysis_store": {},  # Persists across queries
        "conversation_summary": "",  # Persists across queries
        "user_preferences": {}
    }
    
    query_count = 0
    
    # Main conversation loop
    while True:
        try:
            # Get user input
            user_input = input("👤 You: ").strip()
            
            # Check for exit commands
            if user_input.lower() in ['exit', 'quit', 'q', '']:
                print("\n👋 Thanks for using the trading advisor!")
                cleanup_output_folders()
                print("Goodbye!\n")
                break
            
            query_count += 1
            print_separator(f"QUERY #{query_count}")
            
            # Update state with new query
            state["user_query"] = user_input
            
            # Clear temporary fields from previous turn
            state.pop("kline_data", None)
            state.pop("explanation", None)
            state.pop("intent", None)
            state.pop("symbols", None)
            state.pop("horizon", None)
            state.pop("analyses_required", None)
            state.pop("windows_required", None)
            
            # Invoke graph
            print(f"🔄 Processing: \"{user_input}\"\n")
            
            result = graph.invoke(state)
            
            # Debug: Check what's in the result
            print(f"\n🔍 DEBUG - Result keys: {list(result.keys())}")
            explanation = result.get("explanation")
            if explanation:
                print(f"🔍 DEBUG - Explanation length: {len(explanation)}")
                print(f"🔍 DEBUG - Explanation preview: {explanation[:100]}...")
            elif explanation is None:
                print(f"⚠️  DEBUG - 'explanation' key exists but value is None!")
            else:
                print(f"⚠️  DEBUG - No 'explanation' key in result!")
            
            # Extract response
            if explanation:
                print_separator("🤖 ASSISTANT RESPONSE")
                print(explanation)
                print_separator()
            else:
                print("⚠️  No response generated (possible error)\n")
            
            # Update persistent state for next turn
            prev_store_size = len(state.get("analysis_store", {}))
            state["analysis_store"] = result.get("analysis_store", {})
            state["conversation_summary"] = result.get("conversation_summary", "")
            state["user_preferences"] = result.get("user_preferences", {})
            new_store_size = len(state["analysis_store"])
            
            # Save to files for monitoring
            os.makedirs("debug_output", exist_ok=True)
            
            # Save analysis_store as JSON
            with open("debug_output/analysis_store.json", "w", encoding="utf-8") as f:
                json.dump(state["analysis_store"], f, indent=2, default=str)
            
            # Save conversation_summary as txt
            with open("debug_output/conversation_summary.txt", "w", encoding="utf-8") as f:
                f.write(f"Query #{query_count}\n")
                f.write(f"Last Query: {user_input}\n")
                f.write(f"{'='*60}\n\n")
                f.write(state["conversation_summary"])
            
            # Log persistence
            if new_store_size > prev_store_size:
                print(f"✅ Analysis store GREW: {prev_store_size} → {new_store_size} entries")
            elif new_store_size == prev_store_size and new_store_size > 0:
                print(f"✅ Analysis store PERSISTED: {new_store_size} entries maintained")
            
            print(f"📁 State saved to debug_output/ folder\n")
            
            # Show state summary
            print_state_summary(state)
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user. Type 'exit' to quit properly.\n")
            continue
        
        except Exception as e:
            print(f"\n❌ Error processing query: {e}\n")
            import traceback
            traceback.print_exc()
            print("\n💡 You can continue with a new query or type 'exit' to quit.\n")
            continue

if __name__ == "__main__":
    main()
