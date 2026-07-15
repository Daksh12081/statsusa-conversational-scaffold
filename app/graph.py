from typing import Literal

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3

from app.state import ConversationState
from nodes import analyze_query, create_task_plan
from nodes.clarification import handle_clarification
from nodes.resolve_context import resolve_context
from nodes.execute_tasks import execute_tasks
from nodes.generate_response import generate_response


def route_after_analysis(
    state: ConversationState,
) -> Literal["clarification", "resolve_context"]:
    if state.get("clarification_needed"):
        return "clarification"

    return "resolve_context"


builder = StateGraph(ConversationState)

builder.add_node("analyze_query", analyze_query)
builder.add_node("clarification", handle_clarification)
builder.add_node("resolve_context", resolve_context)
builder.add_node("create_task_plan", create_task_plan)
builder.add_node("execute_tasks", execute_tasks)
builder.add_node("generate_response", generate_response)

builder.set_entry_point("analyze_query")

builder.add_conditional_edges(
    "analyze_query",
    route_after_analysis,
    {
        "clarification": "clarification",
        "resolve_context": "resolve_context",
    },
)

builder.add_edge("clarification", END)
builder.add_edge("resolve_context", "create_task_plan")
builder.add_edge("create_task_plan", "execute_tasks")
builder.add_edge("execute_tasks", "generate_response")
builder.add_edge("generate_response", END)

connection = sqlite3.connect("statsusa_memory.db", check_same_thread=False)
checkpointer = SqliteSaver(connection)
graph = builder.compile(checkpointer=checkpointer)