from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3

from app.state import ConversationState
from nodes import analyze_query, extract_intent, create_task_plan
from nodes.clarification import handle_clarification
from nodes.resolve_context import resolve_context
from nodes.execute_tasks import execute_tasks
from nodes.generate_response import generate_response
from nodes.summarize_memory import summarize_memory
from nodes.confirm_intent import confirm_intent
from nodes.handle_metadata import handle_metadata
from nodes.handle_conversation import handle_conversation


def route_after_analysis(
    state: ConversationState,
) -> Literal["clarification", "resolve_context"]:
    if state.get("clarification_needed"):
        return "clarification"

    return "resolve_context"


def route_after_intent(
    state: ConversationState,
) -> Literal[
    "confirm_intent",
    "handle_metadata",
    "handle_conversation",
    "create_task_plan",
]:
    current_intent = state.get("current_intent") or {}
    intent_type = current_intent.get("intent_type")

    if intent_type == "metadata":
        return "handle_metadata"

    if intent_type == "conversation":
        return "handle_conversation"

    if state.get("intent_confirmation_needed"):
        return "confirm_intent"

    return "create_task_plan"


# Inserted function for routing from START
def route_from_start(
    state: ConversationState,
) -> Literal["analyze_query", "create_task_plan"]:
    if (
        state.get("confirmation_response") is True
        and state.get("current_intent") is not None
    ):
        return "create_task_plan"

    return "analyze_query"


builder = StateGraph(ConversationState)

builder.add_node("analyze_query", analyze_query)
builder.add_node("clarification", handle_clarification)
builder.add_node("resolve_context", resolve_context)
builder.add_node("extract_intent", extract_intent)
builder.add_node("confirm_intent", confirm_intent)
builder.add_node("handle_metadata", handle_metadata)
builder.add_node("handle_conversation", handle_conversation)
builder.add_node("create_task_plan", create_task_plan)
builder.add_node("execute_tasks", execute_tasks)
builder.add_node("generate_response", generate_response)
builder.add_node("summarize_memory", summarize_memory)

builder.add_conditional_edges(
    START,
    route_from_start,
    {
        "analyze_query": "analyze_query",
        "create_task_plan": "create_task_plan",
    },
)

builder.add_conditional_edges(
    "analyze_query",
    route_after_analysis,
    {
        "clarification": "clarification",
        "resolve_context": "resolve_context",
    },
)

builder.add_edge("clarification", END)
builder.add_edge("resolve_context", "extract_intent")

builder.add_conditional_edges(
    "extract_intent",
    route_after_intent,
    {
        "confirm_intent": "confirm_intent",
        "handle_metadata": "handle_metadata",
        "handle_conversation": "handle_conversation",
        "create_task_plan": "create_task_plan",
    },
)

builder.add_edge("confirm_intent", END)
builder.add_edge("handle_metadata", END)
builder.add_edge("handle_conversation", END)
builder.add_edge("create_task_plan", "execute_tasks")
builder.add_edge("execute_tasks", "generate_response")
builder.add_edge("generate_response", "summarize_memory")
builder.add_edge("summarize_memory", END)

connection = sqlite3.connect("statsusa_memory.db", check_same_thread=False)
checkpointer = SqliteSaver(connection)
graph = builder.compile(checkpointer=checkpointer)