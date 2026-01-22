"""
Graph Runner & Visualizer
This file DOES NOT modify the graph definition.
It only imports, builds, runs, and visualizes the graph.
"""

from graph_main import create_trading_graph
from default_config import DEFAULT_CONFIG


# ==========================================================
# BUILD GRAPH (NO MODIFICATIONS)
# ==========================================================
# Use production graph from graph_main.py
config = DEFAULT_CONFIG.copy()

graph = create_trading_graph(config)


# ==========================================================
# OPTIONAL: SAVE GRAPH IMAGE
# ==========================================================
def save_graph_image(path="graph.png"):
    """
    Saves LangGraph structure as PNG.
    Requires graphviz installed.
    """
    graph.get_graph().draw_mermaid_png(output_file_path=path)
    print(f"📊 Graph image saved to {path}")


# ==========================================================
# OPTIONAL: RUN GRAPH
# ==========================================================
def run_graph(initial_state: dict):
    """
    Runs the trading graph with an initial state.
    """
    return graph.invoke(initial_state)


# ==========================================================
# DEBUG ENTRY POINT
# ==========================================================
if __name__ == "__main__":
    save_graph_image()
