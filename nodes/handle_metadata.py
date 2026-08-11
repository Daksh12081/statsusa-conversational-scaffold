from app.state import ConversationState
from services.clickhouse_service import ClickHouseQueryError, clickhouse_service


SUPPORTED_DOMAINS = ["insurance", "housing", "death"]

DEATH_METRICS = ["Deaths", "Crude Rate", "Age Adjusted Rate", "Population"]
HOUSING_METRICS = ["Median Listing Price"]
INSURANCE_MOCK_METRICS = ["uninsured rate"]

INSURANCE_MOCK_GEOGRAPHIES = ["Texas", "California", "Florida", "New York"]
INSURANCE_MOCK_YEARS = [2022]

DEATH_MIN_YEAR = 1999
DEATH_MAX_YEAR = 2024


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
            f"insurance (mock data): {', '.join(INSURANCE_MOCK_METRICS)}."
        )

    elif category == "available_geographies":
        death_states = _clickhouse_state_names("deaths_and_death_rate")
        housing_states = _clickhouse_state_names("housing_prices")

        parts = []
        if death_states:
            parts.append(f"death data covers {len(death_states)} states nationwide")
        if housing_states:
            parts.append(f"housing data covers {len(housing_states)} states nationwide")
        parts.append(
            "insurance mock data is available for: " + ", ".join(INSURANCE_MOCK_GEOGRAPHIES)
        )

        response = "; ".join(parts) + "."

    elif category == "available_years":
        housing_min, housing_max = _housing_year_range()
        housing_range = (
            f"{housing_min}–{housing_max}" if housing_min and housing_max else "recent years"
        )

        response = (
            f"Death data is available for {DEATH_MIN_YEAR}–{DEATH_MAX_YEAR}. "
            f"Housing data is available for {housing_range}. "
            "Insurance mock data is available for: "
            + ", ".join(str(year) for year in INSURANCE_MOCK_YEARS)
            + "."
        )

    else:
        response = (
            "I currently support insurance (mock data), housing and death "
            "(live ClickHouse data) datasets. "
            "You can retrieve values, compare locations, rank results, "
            "analyse trends and request visualizations."
        )

    return {
        "final_response": response,
        "tasks": [],
        "task_results": [],
        "response_mode": "metadata",
    }
