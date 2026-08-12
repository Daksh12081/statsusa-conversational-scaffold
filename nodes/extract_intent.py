from app.llm import get_llm
from app.schemas import StructuredIntent
from app.state import ConversationState



def get_intent_llm():
    return get_llm().with_structured_output(StructuredIntent)


PROMPT = """
You are extracting the user's intent for a conversational analytics assistant.

Return ONLY a StructuredIntent.

Determine:
- intent_type (retrieve, compare, rank, trend, combine, clarify, metadata, conversation)
- domains (insurance, housing, death)
- metrics
- geographies
- years
- whether the user explicitly requested a visualization
- requested chart type if mentioned
- metadata_category when intent_type is metadata
- metadata_query when intent_type is metadata
- conversation_query when intent_type is conversation

For domain="death", metrics may include: "deaths", "crude rate" (or "crude death rate"), "age adjusted rate" (or "age-adjusted death rate"), "population".
For domain="housing", metrics may include: "median listing price" (also referred to as "median home price", "home price", "housing price", or "home value"), "average listing price" (also referred to as "average home price"), "days on market", "listing count".
For domain="insurance", metrics may include: "uninsured rate" (or "percent uninsured"), "insured rate" (or "percent insured"), "uninsured population", "insured population", "total population".

Use intent_type="metadata" for questions about what data, domains, metrics, geographies, years, or capabilities are supported.
For metadata queries, choose one metadata_category from:
- available_domains
- available_metrics
- available_geographies
- available_years
- capabilities
For metadata queries, metrics and geographies may be empty.

Use intent_type="conversation" for questions about the conversation itself, such as:
- what was discussed first or last
- what the user's previous question was
- which metric, geography, or year was previously discussed
- requests to summarize the conversation
For conversation queries, choose one conversation_query from:
- first_topic
- last_topic
- last_question
- summary
- previous_metric
- previous_geography
- previous_year
For conversation queries, domains, metrics, geographies, and years may be empty.

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

    if intent_data.get("intent_type") not in {"metadata", "conversation"}:
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