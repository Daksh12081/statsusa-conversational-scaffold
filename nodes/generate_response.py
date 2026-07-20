from app.llm import get_llm
from app.state import ConversationState


def generate_response(state: ConversationState) -> dict:
    task_results = state.get("task_results", [])
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

Rules:
- Use only the verified task results provided above.
- Do not invent or estimate missing values.
- If a result has found=false, clearly state that the requested mock data was unavailable.
- For response_mode="single", give one concise answer.
- For response_mode="compare", clearly compare the values.
- For response_mode="combine", explain how the results relate.
- For response_mode="separate", present each result separately.
- Keep the answer concise and conversational.
"""

    response = get_llm().invoke(prompt)

    return {
        "final_response": response.content.strip(),
        "error": None,
    }
