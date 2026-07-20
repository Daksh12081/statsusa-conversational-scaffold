from app.state import ConversationState


def confirm_intent(state: ConversationState) -> dict:
    """
    Handles the confirmation stage before task planning.
    If no confirmation is pending, allow the graph to continue.
    If confirmation is pending, return the confirmation question.
    """

    if not state.get("pending_confirmation"):
        return {}

    return {
        "final_response": state.get(
            "intent_confirmation_question",
            "Could you confirm your request?",
        )
    }
