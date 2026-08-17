import re

from app.state import ConversationState
from services.data_service import data_service, get_available_states, get_available_years


YEAR_PATTERN = re.compile(r"\b(\d{4})\b")
TOP_N_PATTERN = re.compile(r"top\s+(\d+)|five|four|three|two", re.IGNORECASE)

# Common shorthand for real states, validated against the dynamic ClickHouse
# state list before use -- the list itself stays the source of truth, this
# just lets users type abbreviations for names that are confirmed present.
STATE_ALIASES: dict[str, str] = {
    "ca": "California",
    "calif": "California",
    "tx": "Texas",
    "ny": "New York",
    "ny state": "New York",
    "fl": "Florida",
    "ma": "Massachusetts",
    "mass": "Massachusetts",
    "pa": "Pennsylvania",
    "il": "Illinois",
    "wa": "Washington",
    "va": "Virginia",
    "wv": "West Virginia",
    "nc": "North Carolina",
    "sc": "South Carolina",
    "nd": "North Dakota",
    "sd": "South Dakota",
    "dc": "District of Columbia",
    "d.c.": "District of Columbia",
    "washington dc": "District of Columbia",
}

# The national aggregate isn't a state ClickHouse returns from
# get_available_states (it's explicitly excluded there), so it's handled as
# its own fixed, always-available token rather than validated against the
# dynamic list.
NATIONAL_ALIASES: dict[str, str] = {
    "us": "US",
    "u.s.": "US",
    "usa": "US",
    "united states": "US",
}


def _boundary_pattern(text: str) -> re.Pattern:
    """Matches `text` as a standalone token, case-sensitively on whatever
    case was passed in. Uses alnum lookaround instead of \\b so patterns
    ending in punctuation (e.g. "d.c.") still require a real token boundary
    on both sides instead of silently failing to match at all.
    """
    escaped = re.escape(text)
    return re.compile(rf"(?<![a-zA-Z0-9]){escaped}(?![a-zA-Z0-9])")


def extract_states(query: str, domain: str) -> list[str]:
    available_states = get_available_states(domain)
    available_set = set(available_states)

    candidates: list[tuple[str, str]] = [(name, name) for name in available_states]

    for alias, canonical in STATE_ALIASES.items():
        if canonical in available_set:
            candidates.append((alias, canonical))

    for alias, canonical in NATIONAL_ALIASES.items():
        candidates.append((alias, canonical))

    if not candidates:
        return []

    query_lower = query.lower()
    ordered_candidates = sorted(candidates, key=lambda item: len(item[0]), reverse=True)

    claimed_spans: list[tuple[int, int]] = []
    found: list[tuple[int, str]] = []

    for surface_text, canonical_name in ordered_candidates:
        pattern = _boundary_pattern(surface_text.lower())
        for match in pattern.finditer(query_lower):
            start, end = match.span()
            if any(start < c_end and end > c_start for c_start, c_end in claimed_spans):
                continue
            claimed_spans.append((start, end))
            found.append((start, canonical_name))

    found.sort(key=lambda item: item[0])

    seen = set()
    result = []
    for _, canonical_name in found:
        if canonical_name not in seen:
            seen.add(canonical_name)
            result.append(canonical_name)

    return result


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

    death/housing/insurance tasks may run with year=None and let DataService
    resolve the latest available year per item; if every returned item agrees
    on a year, surface that instead of leaving the result's year as None.
    """
    if year is not None:
        return year

    resolved_years = {item.get("year") for item in items if item.get("year") is not None}
    if len(resolved_years) == 1:
        return resolved_years.pop()

    return None


def build_unavailable_year_result(task_id: str, domain: str, query: str, year: int) -> dict:
    return {
        "task_id": task_id,
        "query": query,
        "result": {
            "found": False,
            "domain": domain,
            "year": year,
            "message": f"No {domain} data is available for {year}.",
        },
    }


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
        states = extract_states(query, domain)
        year = extract_year(query)
        top_n = extract_top_n(query)

        if year is not None:
            available_years = get_available_years(domain)
            if available_years and year not in available_years:
                task_result = build_unavailable_year_result(task_id, domain, query, year)
                results.append(task_result)
                completed_results[task_id] = task_result
                continue

        if not states and dependency_results:
            states = extract_states_from_dependencies(dependency_results)

        if year is None and dependency_results:
            for dependency in dependency_results:
                dependency_year = dependency.get("result", {}).get("year")
                if dependency_year is not None:
                    year = dependency_year
                    break

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
