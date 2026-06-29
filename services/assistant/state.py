from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class AssistantState(TypedDict):
    query: str
    in_scope: bool
    retrieved_chunks: list[dict]
    prompt: str
    answer: str
    sources: list[dict]
    safety_check: dict
    grounding_llm: dict
    messages: Annotated[list, add_messages]