from app.llm import get_llm
from app.schemas import StructuredIntent
from app.state import ConversationState



def get_intent_llm():
    return get_llm().with_structured_output(StructuredIntent)


PROMPT = """
You are extracting the user's intent for a conversational analytics assistant.

Return ONLY a StructuredIntent.

Determine:
- intent_type (retrieve, compare, rank, trend, combine, clarify)
- domains (insurance, housing, death)
- metrics
- geographies
- years
- whether the user explicitly requested a visualization
- requested chart type if mentioned

If no chart is requested, visualization_requested should be false.
Do not invent metrics or locations.
"""


def extract_intent(state: ConversationState):
    query = state.get("standalone_query") or state["user_query"]

    intent = get_intent_llm().invoke(
        [
            ("system", PROMPT),
            ("human", query),
        ]
    )

    history = list(state.get("intent_history", []))
    history.append(intent.model_dump())

    intent_data = intent.model_dump()

    needs_confirmation = False
    confirmation_question = None

    if not intent_data.get("metrics") or not intent_data.get("geographies"):
        needs_confirmation = True
        summary = intent_data.get("intent_type", "request")
        confirmation_question = (
            f"I understood that you want to {summary}. Is that correct?"
        )

    return {
        "current_intent": intent_data,
        "intent_history": history,
        "intent_confirmation_needed": needs_confirmation,
        "intent_confirmation_question": confirmation_question,
        "pending_confirmation": needs_confirmation,
        "pending_intent": intent_data if needs_confirmation else None,
        "confirmation_response": None,
    }