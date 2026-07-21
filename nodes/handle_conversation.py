from app.llm import get_llm
from app.state import ConversationState


def _user_messages(history: list[dict]) -> list[str]:
    return [m.get("content", "") for m in history if m.get("role") == "user"]


def _extract_last_state(history: list[dict]):
    states = [
        "Texas",
        "California",
        "Florida",
        "Arizona",
        "Nevada",
        "Washington",
        "Utah",
    ]
    for message in reversed(history):
        text = message.get("content", "")
        for state in states:
            if state.lower() in text.lower():
                return state
    return None


def _generate_conversation_summary(
    history: list[dict],
    existing_summary: str,
) -> str:
    history_text = "\n".join(
        f"{message.get('role', 'unknown')}: {message.get('content', '')}"
        for message in history
    )

    prompt = f"""
You are summarizing a conversation between a user and a statistics assistant.

Existing long-term summary:
{existing_summary or 'No existing summary.'}

Recent conversation:
{history_text or 'No recent conversation.'}

Create a concise, accurate summary of the discussion.

Rules:
- Treat the recent conversation as the source of truth.
- Ignore details from the existing summary if they conflict with recent messages.
- Mention important metrics, states, years, comparisons and requests discussed.
- Mention unresolved questions or unavailable data when relevant.
- Do not mention implementation details or internal state.
- Return only the summary.
"""

    response = get_llm().invoke(prompt)
    return response.content.strip()


def handle_conversation(state: ConversationState):
    history = state.get("chat_history", []) or []
    summary = state.get("conversation_summary", "") or ""
    intent = state.get("current_intent", {}) or {}
    query_type = intent.get("conversation_query")

    user_history = _user_messages(history)

    if query_type == "last_question":
        response = user_history[-1] if user_history else "No previous user question is available."

    elif query_type == "summary":
        if history or summary:
            response = _generate_conversation_summary(history, summary)
        else:
            response = "There is no conversation to summarize yet."

    elif query_type in {"first_topic", "previous_geography"}:
        state_name = None
        for message in history:
            state_name = _extract_last_state([message])
            if state_name:
                break
        response = (
            f"The first state discussed was {state_name}."
            if state_name
            else "I couldn't determine the first state we discussed."
        )

    elif query_type == "last_topic":
        state_name = _extract_last_state(history)
        response = (
            f"The most recently discussed state was {state_name}."
            if state_name
            else "I couldn't determine the latest topic."
        )

    else:
        response = "I couldn't determine which part of our conversation you were referring to."

    return {
        "tasks": [],
        "task_results": [],
        "response_mode": "conversation",
        "final_response": response,
    }