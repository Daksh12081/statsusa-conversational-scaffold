from app.llm import get_llm
from app.llm_utils import response_text
from app.state import ConversationState


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
    return response_text(response)


def _answer_conversation_question(
    question: str,
    history: list[dict],
    summary: str,
) -> str:
    history_text = "\n".join(
        f"{m.get('role', 'unknown')}: {m.get('content', '')}"
        for m in history
    )

    prompt = f"""
You answer questions about an ongoing conversation.

Conversation summary:
{summary or 'No long-term summary available.'}

Recent conversation:
{history_text or 'No recent conversation.'}

User question:
{question}

Instructions:
- Answer only using the summary and recent conversation.
- Prefer the recent conversation if it conflicts with the summary.
- If the answer cannot be determined, say so clearly.
- Be concise.
"""

    response = get_llm().invoke(prompt)
    return response_text(response)


def handle_conversation(state: ConversationState):
    history = state.get("chat_history", []) or []
    summary = state.get("conversation_summary", "") or ""
    intent = state.get("current_intent", {}) or {}
    query_type = intent.get("conversation_query")

    if query_type == "summary":
        if history or summary:
            response = _generate_conversation_summary(history, summary)
        else:
            response = "There is no conversation to summarize yet."
    else:
        question = state.get("standalone_query") or state.get("user_query") or ""
        response = _answer_conversation_question(question, history, summary)

    return {
        "tasks": [],
        "task_results": [],
        "response_mode": "conversation",
        "final_response": response,
    }