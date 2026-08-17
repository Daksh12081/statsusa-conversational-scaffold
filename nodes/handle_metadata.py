from app.state import ConversationState
from services.data_service import get_available_states, get_year_range


SUPPORTED_DOMAINS = ["insurance", "housing", "death"]

DEATH_METRICS = ["Deaths", "Crude Rate", "Age Adjusted Rate", "Population"]
HOUSING_METRICS = ["Median Listing Price"]
INSURANCE_METRICS = [
    "uninsured rate",
    "insured rate",
    "uninsured population",
    "insured population",
    "total population",
]
INSURANCE_SUBGROUP_DIMENSIONS = [
    "Age",
    "Gender",
    "Race & Ethnicity",
    "Income",
    "Employment Status",
    "Citizenship Status",
    "Disability Status",
    "Educational Attainment",
    "Living Arrangements",
    "Poverty Status",
]


def _format_year_range(domain: str) -> str:
    year_range = get_year_range(domain)
    if year_range is None:
        return "currently unavailable"
    min_year, max_year = year_range
    return f"{min_year}–{max_year}"


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
            f"death: {', '.join(DEATH_METRICS)}; "
            f"housing: {', '.join(HOUSING_METRICS)}; "
            f"insurance: {', '.join(INSURANCE_METRICS)} "
            f"(also breakable down by: {', '.join(INSURANCE_SUBGROUP_DIMENSIONS)})."
        )

    elif category == "available_geographies":
        death_states = get_available_states("death")
        housing_states = get_available_states("housing")
        insurance_states = get_available_states("insurance")

        parts = []
        if death_states:
            parts.append(f"death data covers {len(death_states)} states nationwide")
        if housing_states:
            parts.append(f"housing data covers {len(housing_states)} states nationwide")
        if insurance_states:
            parts.append(f"insurance data covers {len(insurance_states)} states nationwide")

        response = "; ".join(parts) + "." if parts else "Geography data is currently unavailable."

    elif category == "available_years":
        response = (
            f"Death data is available for {_format_year_range('death')}. "
            f"Housing data is available for {_format_year_range('housing')}. "
            f"Insurance data is available for {_format_year_range('insurance')}."
        )

    else:
        response = (
            "I currently support insurance, housing and death datasets, all backed by "
            "live ClickHouse data. "
            "You can retrieve values, compare locations, rank results, "
            "analyse trends and request visualizations."
        )

    return {
        "final_response": response,
        "tasks": [],
        "task_results": [],
        "response_mode": "metadata",
    }
