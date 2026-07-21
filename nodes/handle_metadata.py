from app.state import ConversationState


SUPPORTED_DOMAINS = ["insurance", "housing", "death"]
SUPPORTED_METRICS = {
    "insurance": ["uninsured rate"],
    "housing": ["median home price"],
    "death": ["death rate"],
}
SUPPORTED_GEOGRAPHIES = [
    "Texas",
    "California",
    "Florida",
]
SUPPORTED_YEARS = [2022]


def handle_metadata(state: ConversationState):
    intent = state.get("current_intent", {}) or {}
    category = intent.get("metadata_category")

    if category == "available_domains":
        response = (
            "I currently support these domains: "
            + ", ".join(SUPPORTED_DOMAINS)
            + "."
        )

    elif category == "available_metrics":
        response = (
            "Available metrics include: "
            "insurance: uninsured rate; "
            "housing: median home price; "
            "death: death rate."
        )

    elif category == "available_geographies":
        response = (
            "Current mock data is available for: "
            + ", ".join(SUPPORTED_GEOGRAPHIES)
            + "."
        )

    elif category == "available_years":
        response = (
            "Current mock data is available for the following years: "
            + ", ".join(str(year) for year in SUPPORTED_YEARS)
            + "."
        )

    else:
        response = (
            "I currently support insurance, housing and death datasets. "
            "You can retrieve values, compare locations, rank results, "
            "analyse trends and request visualizations."
        )

    return {
        "final_response": response,
        "tasks": [],
        "task_results": [],
        "response_mode": "metadata",
    }