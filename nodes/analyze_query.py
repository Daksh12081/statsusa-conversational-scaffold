import time
from app.llm import get_llm
from app.schemas import QueryAnalysis
from app.state import ConversationState


def get_query_analyzer():
    return get_llm().with_structured_output(QueryAnalysis)


def analyze_query(state: ConversationState) -> dict:
    user_query = state["user_query"]
    chat_history = state.get("chat_history", [])
    conversation_summary = state.get("conversation_summary", "")

    history_text = "\n".join(
        f'{message["role"]}: {message["content"]}'
        for message in chat_history[-6:]
    )

    prompt = f"""
You are the query analysis component of a conversational statistics assistant.

Classify the latest user message as exactly one of:
- simple: a complete request that can be answered directly
- follow_up: depends on previous conversation context
- multi_intent: contains multiple independent requests
- complex: requires multiple dependent steps
- clarification: lacks required information and cannot be resolved from history

Long-term conversation summary:
{conversation_summary or "No long-term summary available."}

Conversation history:
{history_text or "No previous conversation."}

Latest user message:
{user_query}

Rules:
- If the latest message depends on earlier context, return query_type as follow_up.
- Questions about the conversation itself (for example: "What was my last question?", "Summarize our conversation.", "What were we discussing before housing?", "What did we compare?") should still be classified as follow_up if they depend on prior context.
- For conversation-memory questions, the standalone_query should preserve the user's original wording instead of rewriting it into a different question.
- Use both the long-term summary and recent conversation history to resolve references.
- Treat recent conversation history as more authoritative than the long-term summary if they conflict.
- If enough context exists, create a complete standalone_query.
- For simple, multi_intent, and complex queries, standalone_query should contain the complete request.
- If essential information is missing and cannot be inferred, set needs_clarification to true and provide one concise clarification_question.
- Do not answer the statistical question.
"""

    start = time.time()
    analysis = get_query_analyzer().invoke(prompt)

    conversation_keywords = [
        "our conversation",
        "we discussed",
        "my last question",
        "first state",
        "last state",
        "before",
        "after",
        "what did we",
        "summarize",
        "conversation",
    ]

    lowered = user_query.lower()
    if any(keyword in lowered for keyword in conversation_keywords):
        analysis.standalone_query = user_query

    elapsed = time.time() - start
    print(f"⏱️ analyze_query: {elapsed:.2f}s")

    return {
        "query_type": analysis.query_type,
        "standalone_query": analysis.standalone_query,
        "clarification_needed": analysis.needs_clarification,
        "clarification_question": analysis.clarification_question,
        "error": None,
    }