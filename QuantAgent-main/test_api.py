from typing import TypedDict, List

import google.generativeai as genai
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage


genai.configure(
    api_key="AIzaSyDN8gKMA7Atzy-AlvV3pECeL6qNrM6iI9o"
)

model = genai.GenerativeModel(
    model_name="gemini-2.5-flash"
)


class AgentState(TypedDict):
    messages: List[BaseMessage]


def build_prompt(messages: List[BaseMessage]) -> str:
    lines = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            lines.append(f"Human: {msg.content}")
        elif isinstance(msg, AIMessage):
            lines.append(f"AI: {msg.content}")
    return "\n".join(lines)


def ask(state: AgentState) -> AgentState:
    """Simple QA bot"""
    reponse = model.generate_content(build_prompt(state["messages"]))
    print("AI: ", reponse.text)
    state["messages"].append(AIMessage(content=reponse.text))
    print(state["messages"])
    return state

   


graph = StateGraph(AgentState)

graph.add_node("gemini_agent", ask)

graph.set_entry_point("gemini_agent")
graph.add_edge("gemini_agent", END)

app = graph.compile()



conversation_history = []
user_input = input("HUMAN: ")

while user_input.lower() not in ["exit", "quit"]:
    conversation_history.append(HumanMessage(content=user_input))
    result  = app.invoke({"messages": conversation_history})
    user_input = input("HUMAN: ")
    conversation_history = result["messages"]
