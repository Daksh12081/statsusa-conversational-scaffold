

from app.state import ConversationState


def handle_clarification(state: ConversationState) -> dict:
    question = state.get("clarification_question")

    if not question:
        question = "Could you provide more information about what you would like to know?"

    return {
        "final_response": question,
        "tasks": [],
        "task_results": [],
        "error": None,
    }