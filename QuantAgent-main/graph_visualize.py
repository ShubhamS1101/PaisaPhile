"""
Graph Runner & Visualizer
This file DOES NOT modify the graph definition.
It only imports, builds, runs, and visualizes the graph.
"""

from graph_setup import SetGraph
from graph_util import TechnicalTools
from langchain_openai import ChatOpenAI


# ==========================================================
# LLM SETUP
# ==========================================================
agent_llm = ChatOpenAI(
    model="gemini-2.5-flash",
    temperature=0.1,
)

graph_llm = ChatOpenAI(
    model="gemini-2.5-flash",
    temperature=0.1,
)

toolkit = TechnicalTools()


# ==========================================================
# BUILD GRAPH (NO MODIFICATIONS)
# ==========================================================
graph_builder = SetGraph(
    agent_llm=agent_llm,
    graph_llm=graph_llm,
    toolkit=toolkit,
)

graph = graph_builder.set_graph()


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
