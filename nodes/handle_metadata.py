from app.state import ConversationState
from services.clickhouse_service import ClickHouseQueryError, clickhouse_service


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

DEATH_MIN_YEAR = 1999
DEATH_MAX_YEAR = 2024
INSURANCE_MIN_YEAR = 2012
INSURANCE_MAX_YEAR = 2024


def _clickhouse_state_names(table: str) -> list[str]:
    try:
        rows = clickhouse_service.query(
            f"SELECT DISTINCT area_name FROM {table} "
            "WHERE fips_val_type = 'S' AND state != 'US' AND area_name IS NOT NULL "
            "ORDER BY area_name"
        )
        return [row["area_name"] for row in rows if row.get("area_name")]
    except ClickHouseQueryError:
        return []


def _housing_year_range() -> tuple[int | None, int | None]:
    try:
        rows = clickhouse_service.query(
            "SELECT min(year) AS miny, max(year) AS maxy FROM housing_prices"
        )
        if rows:
            return rows[0].get("miny"), rows[0].get("maxy")
    except ClickHouseQueryError:
        pass
    return None, None


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
        death_states = _clickhouse_state_names("deaths_and_death_rate")
        housing_states = _clickhouse_state_names("housing_prices")
        insurance_states = _clickhouse_state_names("health_insurance")

        parts = []
        if death_states:
            parts.append(f"death data covers {len(death_states)} states nationwide")
        if housing_states:
            parts.append(f"housing data covers {len(housing_states)} states nationwide")
        if insurance_states:
            parts.append(f"insurance data covers {len(insurance_states)} states nationwide")

        response = "; ".join(parts) + "." if parts else "Geography data is currently unavailable."

    elif category == "available_years":
        housing_min, housing_max = _housing_year_range()
        housing_range = (
            f"{housing_min}–{housing_max}" if housing_min and housing_max else "recent years"
        )

        response = (
            f"Death data is available for {DEATH_MIN_YEAR}–{DEATH_MAX_YEAR}. "
            f"Housing data is available for {housing_range}. "
            f"Insurance data is available for {INSURANCE_MIN_YEAR}–{INSURANCE_MAX_YEAR}."
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
