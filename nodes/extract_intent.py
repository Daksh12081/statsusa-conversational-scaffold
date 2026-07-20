from app.llm import llm
from app.schemas import StructuredIntent
from app.state import ConversationState


intent_llm = llm.with_structured_output(StructuredIntent)


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

    intent = intent_llm.invoke(
        [
            ("system", PROMPT),
            ("human", query),
        ]
    )

    history = list(state.get("intent_history", []))
    history.append(intent.model_dump())

    return {
        "current_intent": intent.model_dump(),
        "intent_history": history,
    }