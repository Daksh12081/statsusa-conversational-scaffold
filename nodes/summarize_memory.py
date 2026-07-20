

from typing import Dict

from app.llm import get_llm


SUMMARY_PROMPT = """
You maintain a running conversation summary.

Existing summary:
{summary}

New conversation:
{history}

Update the summary by:
- Preserving important facts.
- Keeping unresolved questions.
- Remembering user preferences.
- Remembering important metrics, states and years.
- Removing repetition.

Return only the updated summary.
"""


def summarize_memory(state: Dict) -> Dict:
    chat_history = state.get("chat_history", [])
    current_summary = state.get("conversation_summary", "")

    if len(chat_history) <= 20:
        return {}

    old_history = chat_history[:-20]

    history_text = "\n".join(
        f"{message['role']}: {message['content']}"
        for message in old_history
    )

    prompt = SUMMARY_PROMPT.format(
        summary=current_summary,
        history=history_text,
    )

    response = get_llm().invoke(prompt)

    return {
        "conversation_summary": response.content.strip(),
    }