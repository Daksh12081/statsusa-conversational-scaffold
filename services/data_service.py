import re

from services.clickhouse_service import clickhouse_service, ClickHouseQueryError


CLICKHOUSE_DOMAINS = {"death", "housing", "insurance"}

DEATH_MIN_YEAR = 1999
DEATH_MAX_YEAR = 2024
DEATH_YEAR_COLUMNS = [f"y{year}" for year in range(DEATH_MIN_YEAR, DEATH_MAX_YEAR + 1)]
DEFAULT_DEATH_CATEGORY = "Crude Rate"

DEFAULT_HOUSING_CATEGORY = "median_listing_price"

INSURANCE_MIN_YEAR = 2012
INSURANCE_MAX_YEAR = 2024
INSURANCE_YEAR_COLUMNS = [f"y{year}" for year in range(INSURANCE_MIN_YEAR, INSURANCE_MAX_YEAR + 1)]
DEFAULT_INSURANCE_CATEGORY = "Percent Uninsured"

INSURANCE_CATEGORY_PARENT = {
    "Total": "Population by Age",
    "Insured": "Insured Population (Number) by Age",
    "Uninsured": "Uninsured Population (Number) by Age",
    "Percent Insured": "Insured Population (Percent) by Age",
    "Percent Uninsured": "Uninsured Population (Percent) by Age",
}

INSURANCE_TOTAL_FILTER = "category_name = 'Total, all ages' AND data_type = 'Estimate'"

STATE_LEVEL_FILTER = "fips_val_type = 'S'"

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


def resolve_insurance_category(metrics: list[str] | None, query: str | None) -> str:
    text = " ".join([*(metrics or []), query or ""]).lower()

    if "percent uninsured" in text or "uninsured rate" in text:
        return "Percent Uninsured"
    if "percent insured" in text or "insured rate" in text:
        return "Percent Insured"
    if "uninsured population" in text:
        return "Uninsured"
    if "insured population" in text:
        return "Insured"
    if "total population" in text:
        return "Total"
    if "uninsured" in text:
        return "Percent Uninsured"
    if "insured" in text:
        return "Percent Insured"
    return DEFAULT_INSURANCE_CATEGORY


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
    def execute(
        self,
        domain: str,
        state: str,
        year: int | None,
        query: str | None = None,
        intent: dict | None = None,
    ) -> dict:
        try:
            if domain == "death":
                return self._execute_death(state=state, year=year, query=query, intent=intent)

            if domain == "housing":
                return self._execute_housing(state=state, year=year, query=query, intent=intent)

            return self._execute_insurance(state=state, year=year, query=query, intent=intent)
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
        try:
            if domain == "death":
                return self._rank_death(year=year, top_n=top_n, query=query, intent=intent)

            if domain == "housing":
                return self._rank_housing(year=year, top_n=top_n, query=query, intent=intent)

            return self._rank_insurance(year=year, top_n=top_n, query=query, intent=intent)
        except ClickHouseQueryError:
            return []

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

    def _execute_insurance(
        self,
        state: str,
        year: int | None,
        query: str | None,
        intent: dict | None,
    ) -> dict:
        metrics = (intent or {}).get("metrics") if intent else None
        category = resolve_insurance_category(metrics=metrics, query=query)
        parent_category = INSURANCE_CATEGORY_PARENT[category]

        if year is not None:
            try:
                year = _validate_year(year, INSURANCE_MIN_YEAR, INSURANCE_MAX_YEAR)
            except ValueError as exc:
                return self._not_found("insurance", state, year, category, str(exc))

            sql = f"""
                SELECT y{year} AS value
                FROM health_insurance
                WHERE {STATE_LEVEL_FILTER}
                  AND area_name = {{state:String}}
                  AND coverage_category = {{category:String}}
                  AND parent_category = {{parent_category:String}}
                  AND {INSURANCE_TOTAL_FILTER}
                LIMIT 1
            """
            rows = clickhouse_service.query(
                sql, {"state": state, "category": category, "parent_category": parent_category}
            )
            value = _to_float(rows[0]["value"]) if rows else None
        else:
            sql = f"""
                SELECT {", ".join(INSURANCE_YEAR_COLUMNS)}
                FROM health_insurance
                WHERE {STATE_LEVEL_FILTER}
                  AND area_name = {{state:String}}
                  AND coverage_category = {{category:String}}
                  AND parent_category = {{parent_category:String}}
                  AND {INSURANCE_TOTAL_FILTER}
                LIMIT 1
            """
            rows = clickhouse_service.query(
                sql, {"state": state, "category": category, "parent_category": parent_category}
            )
            year, value = _latest_valid_year(rows[0] if rows else {}, INSURANCE_MIN_YEAR, INSURANCE_MAX_YEAR)

        if value is None:
            return self._not_found(
                "insurance", state, year, category, f"No insurance data found for {state} ({year})."
            )

        result = {
            "found": True,
            "domain": "insurance",
            "state": state,
            "year": year,
            "metric": category,
            "category": category,
            "value": value,
            "units": "percent" if category in ("Percent Insured", "Percent Uninsured") else "number",
        }

        if category == "Percent Uninsured":
            result["uninsured_rate"] = value

        return result

    def _rank_insurance(
        self,
        year: int | None,
        top_n: int,
        query: str | None,
        intent: dict | None,
    ) -> list[dict]:
        metrics = (intent or {}).get("metrics") if intent else None
        category = resolve_insurance_category(metrics=metrics, query=query)
        parent_category = INSURANCE_CATEGORY_PARENT[category]

        if year is not None:
            try:
                year = _validate_year(year, INSURANCE_MIN_YEAR, INSURANCE_MAX_YEAR)
            except ValueError:
                return []
        else:
            sql = f"""
                SELECT {", ".join(INSURANCE_YEAR_COLUMNS)}
                FROM health_insurance
                WHERE {STATE_LEVEL_FILTER} AND state = 'US'
                  AND coverage_category = {{category:String}}
                  AND parent_category = {{parent_category:String}}
                  AND {INSURANCE_TOTAL_FILTER}
                LIMIT 1
            """
            rows = clickhouse_service.query(
                sql, {"category": category, "parent_category": parent_category}
            )
            year, _ = _latest_valid_year(rows[0] if rows else {}, INSURANCE_MIN_YEAR, INSURANCE_MAX_YEAR)
            if year is None:
                return []

        column = f"y{year}"
        sql = f"""
            SELECT area_name AS state, {column} AS value
            FROM health_insurance
            WHERE {STATE_LEVEL_FILTER} AND state != 'US'
              AND coverage_category = {{category:String}}
              AND parent_category = {{parent_category:String}}
              AND {INSURANCE_TOTAL_FILTER}
            ORDER BY toFloat64OrNull({column}) DESC
            LIMIT {{top_n:UInt32}}
        """
        rows = clickhouse_service.query(
            sql, {"category": category, "parent_category": parent_category, "top_n": top_n}
        )
        items = self._to_ranked_items(rows, year, category)

        if category == "Percent Uninsured":
            for item in items:
                item["uninsured_rate"] = item["value"]

        return items

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


data_service = DataService()
