from langgraph.graph import StateGraph, END
from assistant.state import AssistantState
from assistant.nodes import retrieve_node, build_prompt_node, generate_node


def build_graph():
    """Build and compile the LangGraph assistant pipeline."""
    graph = StateGraph(AssistantState)

    graph.add_node("retrieve", retrieve_node)
    graph.add_node("build_prompt", build_prompt_node)
    graph.add_node("generate", generate_node)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "build_prompt")
    graph.add_edge("build_prompt", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


assistant_graph = build_graph()