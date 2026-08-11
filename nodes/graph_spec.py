from typing import Any


def _extract_row(item: dict[str, Any]) -> dict[str, Any] | None:
    if "uninsured_rate" in item:
        return {"State": item.get("state"), "Value": item["uninsured_rate"], "Metric": "Uninsured Rate"}

    if "median_home_price" in item:
        return {"State": item.get("state"), "Value": item["median_home_price"], "Metric": "Median Home Price"}

    if "death_rate" in item:
        return {"State": item.get("state"), "Value": item["death_rate"], "Metric": "Death Rate"}

    if "value" in item:
        return {"State": item.get("state"), "Value": item["value"], "Metric": item.get("metric", "Value")}

    return None


def build_graph_spec(state: dict[str, Any]) -> dict[str, Any]:
    print("Building graph specification...")

    if not state.get("graph_needed"):
        print("  No graph specification required")
        return {"graph_spec": None}

    graph_type = state.get("graph_type")
    graph_title = state.get("graph_title")
    task_results = state.get("task_results", [])

    data = []

    for task in task_results:
        result = task.get("result", {})

        if "items" in result:
            for item in result["items"]:
                row = _extract_row(item)
                if row:
                    data.append(row)

        elif result.get("found"):
            row = _extract_row(result)
            if row:
                data.append(row)

    graph_spec = {
        "type": graph_type,
        "title": graph_title,
        "x": "State",
        "y": "Value",
        "data": data,
    }

    print(f"  Built graph spec with {len(data)} data point(s)")

    return {"graph_spec": graph_spec}