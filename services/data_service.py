import re

from services.clickhouse_service import clickhouse_service, ClickHouseQueryError
from tools.mock_data import DATASETS, lookup


CLICKHOUSE_DOMAINS = {"death", "housing"}

DEATH_MIN_YEAR = 1999
DEATH_MAX_YEAR = 2024
DEATH_YEAR_COLUMNS = [f"y{year}" for year in range(DEATH_MIN_YEAR, DEATH_MAX_YEAR + 1)]
DEFAULT_DEATH_CATEGORY = "Crude Rate"

DEFAULT_HOUSING_CATEGORY = "median_listing_price"

# Every state/national-level row in both ClickHouse tables is identified by
# fips_val_type='S'; area_name is the clean state name (full_state_name has
# a " (totals)" suffix, e.g. "California (totals)", so it's a worse match key).
STATE_LEVEL_FILTER = "fips_val_type = 'S'"

# The "grand total" breakdown row in deaths_and_death_rate: every row also
# carries age/gender/race/chapter_code/sub_chapter_code breakdown dimensions,
# and this combination is the one that represents the overall state total.
DEATH_TOTAL_FILTER = (
    "age = 'All ages' AND gender = 'Both genders' AND race = 'All races' "
    "AND chapter_code = 'All' AND sub_chapter_code = 'All'"
)


def resolve_death_category(metrics: list[str] | None, query: str | None) -> str:
    text = " ".join([*(metrics or []), query or ""]).lower()

    if "age adjusted" in text or "age-adjusted" in text:
        return "Age Adjusted Rate"
    if "population" in text:
        return "Population"
    if "crude rate" in text or "crude death rate" in text:
        return "Crude Rate"
    if "death count" in text or "number of deaths" in text or re.search(r"\bdeaths\b", text):
        return "Deaths"
    if "death rate" in text or "rate" in text:
        return "Crude Rate"
    return DEFAULT_DEATH_CATEGORY


def resolve_housing_category(metrics: list[str] | None, query: str | None) -> str:
    text = " ".join([*(metrics or []), query or ""]).lower()

    if "square foot" in text or "per square" in text:
        return "median_listing_price_per_square_foot"
    if "days on market" in text:
        return "median_days_on_market"
    if "active listing" in text or "listing count" in text:
        return "active_listing_count"
    if "average" in text and ("price" in text or "listing" in text):
        return "average_listing_price"
    return DEFAULT_HOUSING_CATEGORY


def _to_float(raw) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _validate_year(year: int, min_year: int, max_year: int) -> int:
    if not isinstance(year, int) or not (min_year <= year <= max_year):
        raise ValueError(f"Year must be between {min_year} and {max_year}.")
    return year


def _latest_valid_year(row: dict, min_year: int, max_year: int) -> tuple[int | None, float | None]:
    for year in range(max_year, min_year - 1, -1):
        value = _to_float(row.get(f"y{year}"))
        if value is not None:
            return year, value
    return None, None


class DataService:
    """Backend abstraction layer.

    death and housing are backed by live ClickHouse OLAP tables.
    insurance still uses mock data (its ClickHouse table is empty).
    """

    def execute(
        self,
        domain: str,
        state: str,
        year: int | None,
        query: str | None = None,
        intent: dict | None = None,
    ) -> dict:
        if domain not in CLICKHOUSE_DOMAINS:
            return lookup(domain, state, year)

        try:
            if domain == "death":
                return self._execute_death(state=state, year=year, query=query, intent=intent)

            return self._execute_housing(state=state, year=year, query=query, intent=intent)
        except ClickHouseQueryError as exc:
            return self._not_found(domain, state, year, None, f"Data source unavailable: {exc}")

    def rank(
        self,
        domain: str,
        year: int | None,
        top_n: int,
        query: str | None = None,
        intent: dict | None = None,
    ) -> list[dict]:
        if domain not in CLICKHOUSE_DOMAINS:
            return self._rank_mock(domain=domain, year=year, top_n=top_n)

        try:
            if domain == "death":
                return self._rank_death(year=year, top_n=top_n, query=query, intent=intent)

            return self._rank_housing(year=year, top_n=top_n, query=query, intent=intent)
        except ClickHouseQueryError:
            return []

    # -- death ---------------------------------------------------------

    def _execute_death(
        self,
        state: str,
        year: int | None,
        query: str | None,
        intent: dict | None,
    ) -> dict:
        metrics = (intent or {}).get("metrics") if intent else None
        category = resolve_death_category(metrics=metrics, query=query)

        if year is not None:
            try:
                year = _validate_year(year, DEATH_MIN_YEAR, DEATH_MAX_YEAR)
            except ValueError as exc:
                return self._not_found("death", state, year, category, str(exc))

            sql = f"""
                SELECT y{year} AS value
                FROM deaths_and_death_rate
                WHERE {STATE_LEVEL_FILTER}
                  AND area_name = {{state:String}}
                  AND category = {{category:String}}
                  AND {DEATH_TOTAL_FILTER}
                LIMIT 1
            """
            rows = clickhouse_service.query(sql, {"state": state, "category": category})
            value = _to_float(rows[0]["value"]) if rows else None
        else:
            sql = f"""
                SELECT {", ".join(DEATH_YEAR_COLUMNS)}
                FROM deaths_and_death_rate
                WHERE {STATE_LEVEL_FILTER}
                  AND area_name = {{state:String}}
                  AND category = {{category:String}}
                  AND {DEATH_TOTAL_FILTER}
                LIMIT 1
            """
            rows = clickhouse_service.query(sql, {"state": state, "category": category})
            year, value = _latest_valid_year(rows[0] if rows else {}, DEATH_MIN_YEAR, DEATH_MAX_YEAR)

        if value is None:
            return self._not_found(
                "death", state, year, category, f"No death data found for {state} ({year})."
            )

        return {
            "found": True,
            "domain": "death",
            "state": state,
            "year": year,
            "metric": category,
            "category": category,
            "value": value,
        }

    def _rank_death(
        self,
        year: int | None,
        top_n: int,
        query: str | None,
        intent: dict | None,
    ) -> list[dict]:
        metrics = (intent or {}).get("metrics") if intent else None
        category = resolve_death_category(metrics=metrics, query=query)

        if year is not None:
            try:
                year = _validate_year(year, DEATH_MIN_YEAR, DEATH_MAX_YEAR)
            except ValueError:
                return []
        else:
            sql = f"""
                SELECT {", ".join(DEATH_YEAR_COLUMNS)}
                FROM deaths_and_death_rate
                WHERE {STATE_LEVEL_FILTER} AND state = 'US'
                  AND category = {{category:String}}
                  AND {DEATH_TOTAL_FILTER}
                LIMIT 1
            """
            rows = clickhouse_service.query(sql, {"category": category})
            year, _ = _latest_valid_year(rows[0] if rows else {}, DEATH_MIN_YEAR, DEATH_MAX_YEAR)
            if year is None:
                return []

        column = f"y{year}"
        sql = f"""
            SELECT area_name AS state, {column} AS value
            FROM deaths_and_death_rate
            WHERE {STATE_LEVEL_FILTER} AND state != 'US'
              AND category = {{category:String}}
              AND {DEATH_TOTAL_FILTER}
            ORDER BY toFloat64OrNull({column}) DESC
            LIMIT {{top_n:UInt32}}
        """
        rows = clickhouse_service.query(sql, {"category": category, "top_n": top_n})

        return self._to_ranked_items(rows, year, category)

    # -- housing ---------------------------------------------------------

    def _execute_housing(
        self,
        state: str,
        year: int | None,
        query: str | None,
        intent: dict | None,
    ) -> dict:
        metrics = (intent or {}).get("metrics") if intent else None
        category = resolve_housing_category(metrics=metrics, query=query)

        if year is None:
            year = self._latest_housing_year(category=category, state=state)
            if year is None:
                return self._not_found(
                    "housing", state, None, category, f"No housing data found for {state}."
                )

        sql = """
            SELECT avg AS value
            FROM housing_prices
            WHERE fips_val_type = 'S'
              AND area_name = {state:String}
              AND category = {category:String}
              AND year = {year:Int32}
            LIMIT 1
        """
        rows = clickhouse_service.query(sql, {"state": state, "category": category, "year": year})
        value = _to_float(rows[0]["value"]) if rows else None

        if value is None:
            return self._not_found(
                "housing", state, year, category, f"No housing data found for {state} ({year})."
            )

        result = {
            "found": True,
            "domain": "housing",
            "state": state,
            "year": year,
            "metric": category,
            "category": category,
            "value": value,
        }

        # Backward compatibility: graph_spec/frontend historically read
        # median_home_price directly; keep populating it until they migrate
        # to the normalized value/metric shape used across all domains.
        if category == DEFAULT_HOUSING_CATEGORY:
            result["median_home_price"] = value

        return result

    def _rank_housing(
        self,
        year: int | None,
        top_n: int,
        query: str | None,
        intent: dict | None,
    ) -> list[dict]:
        metrics = (intent or {}).get("metrics") if intent else None
        category = resolve_housing_category(metrics=metrics, query=query)

        if year is None:
            year = self._latest_housing_year(category=category, state=None)
            if year is None:
                return []

        sql = """
            SELECT area_name AS state, avg AS value
            FROM housing_prices
            WHERE fips_val_type = 'S' AND state != 'US'
              AND category = {category:String}
              AND year = {year:Int32}
              AND avg IS NOT NULL AND avg != 'NA' AND avg != ''
            ORDER BY toFloat64OrNull(avg) DESC
            LIMIT {top_n:UInt32}
        """
        rows = clickhouse_service.query(sql, {"category": category, "year": year, "top_n": top_n})
        items = self._to_ranked_items(rows, year, category)

        if category == DEFAULT_HOUSING_CATEGORY:
            for item in items:
                item["median_home_price"] = item["value"]

        return items

    def _latest_housing_year(self, category: str, state: str | None) -> int | None:
        conditions = [
            "fips_val_type = 'S'",
            "category = {category:String}",
            "avg IS NOT NULL",
            "avg != 'NA'",
            "avg != ''",
        ]
        parameters = {"category": category}

        if state is not None:
            conditions.append("area_name = {state:String}")
            parameters["state"] = state

        sql = f"""
            SELECT max(year) AS latest_year
            FROM housing_prices
            WHERE {" AND ".join(conditions)}
        """
        rows = clickhouse_service.query(sql, parameters)
        return rows[0]["latest_year"] if rows and rows[0].get("latest_year") else None

    # -- mock (insurance only) -------------------------------------------

    def _rank_mock(self, domain: str, year: int, top_n: int) -> list[dict]:
        dataset = DATASETS.get(domain, {})
        metric_name = {"insurance": "uninsured_rate"}[domain]

        items = []

        for (state_name, data_year), values in dataset.items():
            if data_year != year:
                continue

            items.append(
                {
                    "state": state_name,
                    "year": data_year,
                    metric_name: values[metric_name],
                }
            )

        items.sort(key=lambda item: item[metric_name], reverse=True)
        return items[:top_n]

    # -- shared helpers ----------------------------------------------------

    def _to_ranked_items(self, rows: list[dict], year: int, category: str) -> list[dict]:
        items = []

        for row in rows:
            value = _to_float(row.get("value"))
            if value is None:
                continue

            items.append(
                {
                    "state": row.get("state"),
                    "year": year,
                    "metric": category,
                    "value": value,
                }
            )

        return items

    def _not_found(
        self,
        domain: str,
        state: str,
        year: int | None,
        category: str | None,
        message: str,
    ) -> dict:
        return {
            "found": False,
            "domain": domain,
            "state": state,
            "year": year,
            "metric": category,
            "message": message,
        }


# Singleton instance used throughout the application.
data_service = DataService()
