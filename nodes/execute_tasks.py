import re

from app.state import ConversationState
from services.data_service import CLICKHOUSE_DOMAINS, data_service


STATE_PATTERN = re.compile(
    r"(Texas|California|Florida|New York)",
    re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"(20\d{2})")
TOP_N_PATTERN = re.compile(r"top\s+(\d+)|five|four|three|two", re.IGNORECASE)

# insurance is still mock data and only exists for 2022; death and housing are
# backed by live ClickHouse and resolve their own latest year when none is
# given (see DataService), so they deliberately have no hardcoded default here.
DEFAULT_MOCK_YEAR = 2022


def extract_states(query: str) -> list[str]:
    matches = STATE_PATTERN.findall(query)
    return list(dict.fromkeys(match.title() for match in matches))


def extract_year(query: str) -> int | None:
    match = YEAR_PATTERN.search(query)
    if not match:
        return None

    return int(match.group(1))


def extract_top_n(query: str) -> int | None:
    match = TOP_N_PATTERN.search(query)
    if not match:
        return None

    if match.group(1):
        return int(match.group(1))

    word_to_number = {
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
    }
    return word_to_number.get(match.group(0).lower())


def get_dependency_results(
    depends_on: list[str],
    completed_results: dict[str, dict],
) -> list[dict]:
    dependency_results = []

    for dependency_id in depends_on:
        dependency = completed_results.get(dependency_id)
        if dependency:
            dependency_results.append(dependency)

    return dependency_results


def extract_states_from_dependencies(dependency_results: list[dict]) -> list[str]:
    states = []

    for dependency in dependency_results:
        result = dependency.get("result", {})

        if result.get("state"):
            states.append(result["state"])

        for item in result.get("items", []):
            if item.get("state"):
                states.append(item["state"])

    return list(dict.fromkeys(states))


def resolve_display_year(year: int | None, items: list[dict]) -> int | None:
    """Best-effort year to report when none was requested upfront.

    death/housing tasks may run with year=None and let DataService resolve
    the latest available year per item; if every returned item agrees on a
    year, surface that instead of leaving the result's year as None.
    """
    if year is not None:
        return year

    resolved_years = {item.get("year") for item in items if item.get("year") is not None}
    if len(resolved_years) == 1:
        return resolved_years.pop()

    return None


def execute_ranked_task(
    task_id: str,
    domain: str,
    query: str,
    year: int | None,
    top_n: int,
    intent: dict | None = None,
) -> dict:
    ranked_items = data_service.rank(
        domain=domain,
        year=year,
        top_n=top_n,
        query=query,
        intent=intent,
    )

    return {
        "task_id": task_id,
        "query": query,
        "result": {
            "found": bool(ranked_items),
            "domain": domain,
            "year": resolve_display_year(year, ranked_items),
            "items": ranked_items,
        },
    }


def execute_tasks(state: ConversationState) -> dict:
    results = []
    completed_results = {}
    intent = state.get("current_intent")

    for task in state.get("tasks", []):
        task_id = task["task_id"]
        domain = task["domain"]
        query = task["query"]
        depends_on = task.get("depends_on", [])

        dependency_results = get_dependency_results(depends_on, completed_results)
        states = extract_states(query)
        year = extract_year(query)
        top_n = extract_top_n(query)

        if not states and dependency_results:
            states = extract_states_from_dependencies(dependency_results)

        if year is None and dependency_results:
            for dependency in dependency_results:
                dependency_year = dependency.get("result", {}).get("year")
                if dependency_year is not None:
                    year = dependency_year
                    break

        if year is None and domain not in CLICKHOUSE_DOMAINS:
            year = DEFAULT_MOCK_YEAR

        if top_n is not None and not states:
            task_result = execute_ranked_task(
                task_id=task_id,
                domain=domain,
                query=query,
                year=year,
                top_n=top_n,
                intent=intent,
            )
            results.append(task_result)
            completed_results[task_id] = task_result
            continue

        if not states:
            task_result = {
                "task_id": task_id,
                "success": False,
                "message": "Unable to determine a state for the task.",
            }
            results.append(task_result)
            completed_results[task_id] = task_result
            continue

        data_items = [
            data_service.execute(
                domain=domain,
                state=state_name,
                year=year,
                query=query,
                intent=intent,
            )
            for state_name in states
        ]

        task_result = {
            "task_id": task_id,
            "query": query,
            "result": {
                "found": any(item.get("found") for item in data_items),
                "domain": domain,
                "year": resolve_display_year(year, data_items),
                "items": data_items,
            },
        }

        if len(data_items) == 1:
            task_result["result"] = data_items[0]

        results.append(task_result)
        completed_results[task_id] = task_result

    return {
        "task_results": results,
        "error": None,
    }