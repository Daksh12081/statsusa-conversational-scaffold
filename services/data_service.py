import logging
import re
import time

from services.clickhouse_service import clickhouse_service, ClickHouseQueryError


logger = logging.getLogger(__name__)

DATA_SOURCE_UNAVAILABLE_MESSAGE = "The data source is temporarily unavailable."

DEATH_TABLE = "deaths_and_death_rate"
HOUSING_TABLE = "housing_prices"
INSURANCE_TABLE = "health_insurance"

DOMAIN_TABLES = {
    "death": DEATH_TABLE,
    "housing": HOUSING_TABLE,
    "insurance": INSURANCE_TABLE,
}

CLICKHOUSE_DOMAINS = {"death", "housing", "insurance"}

DEFAULT_DEATH_CATEGORY = "Crude Rate"
DEFAULT_HOUSING_CATEGORY = "median_listing_price"
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

_CACHE_TTL_SECONDS = 3600
_cache: dict[str, tuple[float, object]] = {}


def _cache_get(key: str):
    entry = _cache.get(key)
    if entry is None:
        return None

    expires_at, value = entry
    if time.time() >= expires_at:
        del _cache[key]
        return None

    return value


def _cache_set(key: str, value, ttl: int = _CACHE_TTL_SECONDS) -> None:
    _cache[key] = (time.time() + ttl, value)


def clear_metadata_cache() -> None:
    _cache.clear()


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


def _numeric_sql(column_expr: str) -> str:
    """SQL for parsing a Nullable(String) column as a float, tolerating
    comma thousands-separators (e.g. '1,228.90') the same way _to_float does."""
    return f"toFloat64OrNull(replaceAll({column_expr}, ',', ''))"


def _to_float(raw) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.replace(",", "")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _validate_year(year: int, year_range: tuple[int, int] | None) -> int:
    if year_range is None:
        raise ValueError("Year data is currently unavailable.")

    min_year, max_year = year_range
    if not isinstance(year, int) or not (min_year <= year <= max_year):
        raise ValueError(f"Year must be between {min_year} and {max_year}.")
    return year


def _latest_valid_year_from_columns(
    row: dict, year_columns: list[str]
) -> tuple[int | None, float | None]:
    for column in reversed(year_columns):
        value = _to_float(row.get(column))
        if value is not None:
            return int(column[1:]), value
    return None, None


def _discover_year_columns(table: str) -> list[str]:
    cache_key = f"year_columns:{table}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    sql = (
        "SELECT name FROM system.columns "
        "WHERE database = currentDatabase() AND table = {table:String} "
        "AND match(name, '^y[0-9]{4}$') ORDER BY name"
    )
    # ClickHouseQueryError intentionally propagates here rather than being
    # swallowed: the caching decision belongs to whichever caller is about
    # to write to the cache, so a transient failure never gets cached as a
    # permanent "no data" fact. See get_available_years/get_available_states.
    rows = clickhouse_service.query(sql, {"table": table})

    columns = [row["name"] for row in rows]
    _cache_set(cache_key, columns)
    return columns


def _columnar_domain_config(domain: str) -> tuple[str, list[str], dict]:
    if domain == "death":
        return (
            DEATH_TABLE,
            ["category = {category:String}", DEATH_TOTAL_FILTER],
            {"category": DEFAULT_DEATH_CATEGORY},
        )

    parent_category = INSURANCE_CATEGORY_PARENT[DEFAULT_INSURANCE_CATEGORY]
    return (
        INSURANCE_TABLE,
        [
            "coverage_category = {category:String}",
            "parent_category = {parent_category:String}",
            INSURANCE_TOTAL_FILTER,
        ],
        {"category": DEFAULT_INSURANCE_CATEGORY, "parent_category": parent_category},
    )


def _discover_columnar_years(domain: str) -> list[int]:
    table, extra_conditions, parameters = _columnar_domain_config(domain)
    year_columns = _discover_year_columns(table)
    if not year_columns:
        return []

    count_exprs = ", ".join(
        f"countIf({_numeric_sql(column)} IS NOT NULL) AS {column}"
        for column in year_columns
    )
    conditions = [STATE_LEVEL_FILTER, *extra_conditions]
    sql = f"SELECT {count_exprs} FROM {table} WHERE {' AND '.join(conditions)}"

    rows = clickhouse_service.query(sql, parameters)

    if not rows:
        return []

    row = rows[0]
    years = [
        int(column[1:])
        for column in year_columns
        if (row.get(column) or 0) > 0
    ]
    return sorted(years)


def _discover_housing_years() -> list[int]:
    sql = f"""
        SELECT DISTINCT year FROM {HOUSING_TABLE}
        WHERE {STATE_LEVEL_FILTER} AND category = {{category:String}}
          AND avg IS NOT NULL AND avg != 'NA' AND avg != ''
        ORDER BY year
    """
    rows = clickhouse_service.query(sql, {"category": DEFAULT_HOUSING_CATEGORY})

    return sorted(row["year"] for row in rows if row.get("year") is not None)


def get_available_years(domain: str) -> list[int]:
    cache_key = f"available_years:{domain}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        if domain == "housing":
            years = _discover_housing_years()
        elif domain in ("death", "insurance"):
            years = _discover_columnar_years(domain)
        else:
            years = []
    except ClickHouseQueryError as exc:
        logger.error("Failed to discover available years for domain=%s: %s", domain, exc)
        return []

    _cache_set(cache_key, years)
    return years


def get_year_range(domain: str) -> tuple[int, int] | None:
    years = get_available_years(domain)
    return (min(years), max(years)) if years else None


def get_latest_available_year(domain: str) -> int | None:
    years = get_available_years(domain)
    return max(years) if years else None


def get_available_states(domain: str) -> list[str]:
    table = DOMAIN_TABLES.get(domain)
    if table is None:
        return []

    cache_key = f"states:{domain}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    sql = f"""
        SELECT DISTINCT area_name FROM {table}
        WHERE {STATE_LEVEL_FILTER} AND state != 'US' AND area_name IS NOT NULL
        ORDER BY area_name
    """
    try:
        rows = clickhouse_service.query(sql, {})
    except ClickHouseQueryError as exc:
        logger.error("Failed to discover available states for domain=%s: %s", domain, exc)
        return []

    states = [row["area_name"] for row in rows if row.get("area_name")]
    _cache_set(cache_key, states)
    return states


def validate_grand_total_filters() -> dict[str, bool]:
    """Confirms the hardcoded grand-total filter literals still match real rows.

    A False entry means the literal category-name strings (e.g. 'All ages',
    'Total, all ages') no longer match the live data's labeling convention,
    so query results for that domain should not be trusted until investigated.
    """
    results = {}

    try:
        rows = clickhouse_service.query(
            f"SELECT count() AS n FROM {DEATH_TABLE} WHERE {STATE_LEVEL_FILTER} "
            f"AND category = {{category:String}} AND {DEATH_TOTAL_FILTER}",
            {"category": DEFAULT_DEATH_CATEGORY},
        )
        results["death"] = bool(rows and (rows[0].get("n") or 0) > 0)
    except ClickHouseQueryError as exc:
        logger.error("Grand-total filter validation failed for domain=death: %s", exc)
        results["death"] = False

    try:
        parent_category = INSURANCE_CATEGORY_PARENT[DEFAULT_INSURANCE_CATEGORY]
        rows = clickhouse_service.query(
            f"SELECT count() AS n FROM {INSURANCE_TABLE} WHERE {STATE_LEVEL_FILTER} "
            f"AND coverage_category = {{category:String}} "
            f"AND parent_category = {{parent_category:String}} AND {INSURANCE_TOTAL_FILTER}",
            {"category": DEFAULT_INSURANCE_CATEGORY, "parent_category": parent_category},
        )
        results["insurance"] = bool(rows and (rows[0].get("n") or 0) > 0)
    except ClickHouseQueryError as exc:
        logger.error("Grand-total filter validation failed for domain=insurance: %s", exc)
        results["insurance"] = False

    return results


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
            logger.error(
                "ClickHouse execute failed for domain=%s state=%s year=%s: %s",
                domain, state, year, exc,
            )
            return self._not_found(domain, state, year, None, DATA_SOURCE_UNAVAILABLE_MESSAGE)

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
        except ClickHouseQueryError as exc:
            logger.error("ClickHouse rank failed for domain=%s year=%s: %s", domain, year, exc)
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
                year = _validate_year(year, get_year_range("death"))
            except ValueError as exc:
                return self._not_found("death", state, year, category, str(exc))

            sql = f"""
                SELECT y{year} AS value
                FROM {DEATH_TABLE}
                WHERE {STATE_LEVEL_FILTER}
                  AND area_name = {{state:String}}
                  AND category = {{category:String}}
                  AND {DEATH_TOTAL_FILTER}
                LIMIT 1
            """
            rows = clickhouse_service.query(sql, {"state": state, "category": category})
            value = _to_float(rows[0]["value"]) if rows else None
        else:
            year_columns = _discover_year_columns(DEATH_TABLE)
            sql = f"""
                SELECT {", ".join(year_columns)}
                FROM {DEATH_TABLE}
                WHERE {STATE_LEVEL_FILTER}
                  AND area_name = {{state:String}}
                  AND category = {{category:String}}
                  AND {DEATH_TOTAL_FILTER}
                LIMIT 1
            """
            rows = clickhouse_service.query(sql, {"state": state, "category": category})
            year, value = _latest_valid_year_from_columns(rows[0] if rows else {}, year_columns)

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
                year = _validate_year(year, get_year_range("death"))
            except ValueError:
                return []
        else:
            year_columns = _discover_year_columns(DEATH_TABLE)
            sql = f"""
                SELECT {", ".join(year_columns)}
                FROM {DEATH_TABLE}
                WHERE {STATE_LEVEL_FILTER} AND state = 'US'
                  AND category = {{category:String}}
                  AND {DEATH_TOTAL_FILTER}
                LIMIT 1
            """
            rows = clickhouse_service.query(sql, {"category": category})
            year, _ = _latest_valid_year_from_columns(rows[0] if rows else {}, year_columns)
            if year is None:
                return []

        column = f"y{year}"
        sql = f"""
            SELECT area_name AS state, {column} AS value
            FROM {DEATH_TABLE}
            WHERE {STATE_LEVEL_FILTER} AND state != 'US'
              AND category = {{category:String}}
              AND {DEATH_TOTAL_FILTER}
              AND {_numeric_sql(column)} IS NOT NULL
            ORDER BY {_numeric_sql(column)} DESC
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

        sql = f"""
            SELECT avg AS value
            FROM {HOUSING_TABLE}
            WHERE {STATE_LEVEL_FILTER}
              AND area_name = {{state:String}}
              AND category = {{category:String}}
              AND year = {{year:Int32}}
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

        sql = f"""
            SELECT area_name AS state, avg AS value
            FROM {HOUSING_TABLE}
            WHERE {STATE_LEVEL_FILTER} AND state != 'US'
              AND category = {{category:String}}
              AND year = {{year:Int32}}
              AND avg IS NOT NULL AND avg != 'NA' AND avg != ''
            ORDER BY {_numeric_sql('avg')} DESC
            LIMIT {{top_n:UInt32}}
        """
        rows = clickhouse_service.query(sql, {"category": category, "year": year, "top_n": top_n})
        items = self._to_ranked_items(rows, year, category)

        if category == DEFAULT_HOUSING_CATEGORY:
            for item in items:
                item["median_home_price"] = item["value"]

        return items

    def _latest_housing_year(self, category: str, state: str | None) -> int | None:
        conditions = [
            STATE_LEVEL_FILTER,
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
            FROM {HOUSING_TABLE}
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
                year = _validate_year(year, get_year_range("insurance"))
            except ValueError as exc:
                return self._not_found("insurance", state, year, category, str(exc))

            sql = f"""
                SELECT y{year} AS value
                FROM {INSURANCE_TABLE}
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
            year_columns = _discover_year_columns(INSURANCE_TABLE)
            sql = f"""
                SELECT {", ".join(year_columns)}
                FROM {INSURANCE_TABLE}
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
            year, value = _latest_valid_year_from_columns(rows[0] if rows else {}, year_columns)

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
                year = _validate_year(year, get_year_range("insurance"))
            except ValueError:
                return []
        else:
            year_columns = _discover_year_columns(INSURANCE_TABLE)
            sql = f"""
                SELECT {", ".join(year_columns)}
                FROM {INSURANCE_TABLE}
                WHERE {STATE_LEVEL_FILTER} AND state = 'US'
                  AND coverage_category = {{category:String}}
                  AND parent_category = {{parent_category:String}}
                  AND {INSURANCE_TOTAL_FILTER}
                LIMIT 1
            """
            rows = clickhouse_service.query(
                sql, {"category": category, "parent_category": parent_category}
            )
            year, _ = _latest_valid_year_from_columns(rows[0] if rows else {}, year_columns)
            if year is None:
                return []

        column = f"y{year}"
        sql = f"""
            SELECT area_name AS state, {column} AS value
            FROM {INSURANCE_TABLE}
            WHERE {STATE_LEVEL_FILTER} AND state != 'US'
              AND coverage_category = {{category:String}}
              AND parent_category = {{parent_category:String}}
              AND {INSURANCE_TOTAL_FILTER}
              AND {_numeric_sql(column)} IS NOT NULL
            ORDER BY {_numeric_sql(column)} DESC
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
