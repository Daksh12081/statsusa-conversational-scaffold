from app.llm import get_llm
from app.schemas import ExecutionPlan
from app.state import ConversationState


def get_task_planner():
    return get_llm().with_structured_output(ExecutionPlan)


def create_task_plan(state: ConversationState) -> dict:
    standalone_query = state.get("standalone_query") or state["user_query"]

    prompt = f"""
You are the task-planning component of a conversational statistics assistant.

Convert the user request into one or more executable tasks.

Available domains:
- insurance
- housing
- death

User request:
{standalone_query}

Rules:
- Use one task when the request belongs to one domain.
- Split the request into multiple tasks when it contains multiple domains.
- Each task query must be complete and executable on its own.
- Use depends_on only when a task requires the result of an earlier task.
- For dependent tasks, include the exact earlier task_id inside depends_on.
- Example: if task_2 requires the output of task_1, set depends_on=["task_1"].
- Use response_mode="single" for one task.
- Use response_mode="separate" for unrelated independent tasks.
- Use response_mode="combine" when results should be merged.
- Use response_mode="compare" when the user asks for a comparison.
- Do not answer the statistical question.
"""

    plan = get_task_planner().invoke(prompt)

    tasks = [task.model_dump() for task in plan.tasks]

    response_mode = getattr(plan, "response_mode", None)
    if response_mode is None:
        if len(tasks) == 1:
            response_mode = "single"
        elif any(task.get("depends_on") for task in tasks):
            response_mode = "combine"
        else:
            response_mode = "separate"

    return {
        "tasks": tasks,
        "response_mode": response_mode,
        "task_results": [],
        "error": None,
    }