from langgraph.graph import StateGraph, END
from assistant.state import AssistantState
from assistant.nodes import retrieve_node, build_prompt_node, generate_node
from assistant.guardrail import check_scope_node
from assistant.safety import safety_check_node
from assistant.grounding_llm import grounding_llm_node


def route_after_scope_check(state: dict) -> str:
    return "retrieve" if state["in_scope"] else END


def build_graph_with_llm_grounding():
    """
    Alternative assistant pipeline that adds an LLM-based faithfulness check
    after the existing citation/command safety check. Roughly doubles
    per-query latency on CPU-only inference since it requires a second
    Ollama call; intended for GPU-enabled hardware where this cost is small.
    Swap this in for build_graph() in graph.py to use it.
    """
    graph = StateGraph(AssistantState)

    graph.add_node("check_scope", check_scope_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("build_prompt", build_prompt_node)
    graph.add_node("generate", generate_node)
    graph.add_node("run_safety_check", safety_check_node)
    graph.add_node("run_llm_grounding", grounding_llm_node)

    graph.set_entry_point("check_scope")
    graph.add_conditional_edges("check_scope", route_after_scope_check, {"retrieve": "retrieve", END: END})
    graph.add_edge("retrieve", "build_prompt")
    graph.add_edge("build_prompt", "generate")
    graph.add_edge("generate", "run_safety_check")
    graph.add_edge("run_safety_check", "run_llm_grounding")
    graph.add_edge("run_llm_grounding", END)

    return graph.compile()


assistant_graph_llm_grounding = build_graph_with_llm_grounding()