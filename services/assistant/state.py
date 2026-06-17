from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class AssistantState(TypedDict):
    query: str
    retrieved_chunks: list[dict]
    prompt: str
    answer: str
    sources: list[dict]
    messages: Annotated[list, add_messages]