from app.llm import get_llm
from app.state import ConversationState


def generate_response(state: ConversationState) -> dict:
    task_results = state.get("task_results", [])
    graph_needed = state.get("graph_needed", False)
    graph_type = state.get("graph_type")
    graph_title = state.get("graph_title")
    graph_reason = state.get("graph_reason")
    graph_spec = state.get("graph_spec")
    response_mode = state.get("response_mode") or "single"
    standalone_query = state.get("standalone_query") or state["user_query"]

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

Rules:
- Use only the verified task results provided above.
- Do not invent or estimate missing values.
- If a result has found=false, clearly state that the requested mock data was unavailable.
- For response_mode="single", give one concise answer.
- For response_mode="compare", clearly compare the values.
- For response_mode="combine", explain how the results relate.
- For response_mode="separate", present each result separately.
- Keep the answer concise and conversational.
- If graph_needed is true, append a short section at the end exactly in this format:

Recommended Visualization:
<graph_title>
Type: <graph_type>
Reason: <graph_reason>

- If graph_needed is false, do not mention visualizations.
"""

    response = get_llm().invoke(prompt)

    return {
        "final_response": response.content.strip(),
        "graph_spec": graph_spec,
        "error": None,
    }
