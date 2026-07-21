from app.llm import get_llm
from app.state import ConversationState


def resolve_context(state: ConversationState) -> dict:
    """
    Resolves follow-up queries into standalone queries.
    If the query is not a follow-up, it simply returns the existing standalone query.
    """

    if state.get("query_type") != "follow_up":
        return {
            "standalone_query": state.get("standalone_query") or state["user_query"]
        }

    conversation_summary = state.get("conversation_summary", "")

    history = "\n".join(
        f'{msg["role"]}: {msg["content"]}'
        for msg in state.get("chat_history", [])[-6:]
    )

    prompt = f"""
You are a conversation context resolver.

Your job is to rewrite the user's latest message into a complete standalone request.

Long-term Conversation Summary:
{conversation_summary or 'No long-term summary available.'}

Conversation History:
{history or 'No previous conversation.'}

Latest User Message:
{state['user_query']}

Rules:
- Preserve the user's original intent.
- Inherit missing context from both the long-term summary and the recent conversation history.
- If the summary and recent conversation disagree, always trust the recent conversation.
- Do not invent information.
- Prefer using entities already mentioned in the conversation instead of introducing new ones.
- Return ONLY the rewritten standalone query.
"""

    response = get_llm().invoke(prompt)

    return {
        "standalone_query": response.content.strip()
    }