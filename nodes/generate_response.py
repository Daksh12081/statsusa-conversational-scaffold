from app.llm import get_llm
from app.llm_utils import response_text
from app.state import ConversationState


def _resolve_assumed_year(task_results: list[dict]) -> int | None:
    """The single year the executor auto-selected, when every task result
    agrees on one -- used only when the user never specified a year."""
    years = set()

    for task_result in task_results:
        result = task_result.get("result") or {}
        if result.get("year") is not None:
            years.add(result["year"])
        for item in result.get("items", []):
            if item.get("year") is not None:
                years.add(item["year"])

    return years.pop() if len(years) == 1 else None


def generate_response(state: ConversationState) -> dict:
    task_results = state.get("task_results", [])
    graph_needed = state.get("graph_needed", False)
    graph_type = state.get("graph_type")
    graph_title = state.get("graph_title")
    graph_reason = state.get("graph_reason")
    graph_spec = state.get("graph_spec")
    response_mode = state.get("response_mode") or "single"
    standalone_query = state.get("standalone_query") or state["user_query"]

    requested_years = (state.get("current_intent") or {}).get("years") or []
    assumed_year = None if requested_years else _resolve_assumed_year(task_results)

    if assumed_year is not None:
        year_assumption_note = (
            f"No year was specified, so the latest available year "
            f"({assumed_year}) was used automatically."
        )
    else:
        year_assumption_note = "Not applicable."

    prompt = f"""
You are the response-generation component of a conversational statistics assistant.

User request:
{standalone_query}

Response mode:
{response_mode}

Verified task results:
{task_results}

Graph recommendation:
Needed: {graph_needed}
Type: {graph_type}
Title: {graph_title}
Reason: {graph_reason}

Year assumption:
{year_assumption_note}

Rules:
- Use only the verified task results provided above.
- Do not invent or estimate missing values.
- If a result has found=false, clearly state that the requested data was unavailable.
- For response_mode="single", give one concise answer.
- For response_mode="compare", clearly compare the values.
- For response_mode="combine", explain how the results relate.
- For response_mode="separate", present each result separately.
- Keep the answer concise and conversational.
- If the year assumption above is not "Not applicable.", explicitly mention in your response that the latest available year was used because none was specified.
- If graph_needed is true, append a short section at the end exactly in this format:

Recommended Visualization:
<graph_title>
Type: <graph_type>
Reason: <graph_reason>

- If graph_needed is false, do not mention visualizations.
"""

    response = get_llm().invoke(prompt)

    return {
        "final_response": response_text(response),
        "graph_spec": graph_spec,
        "error": None,
    }
