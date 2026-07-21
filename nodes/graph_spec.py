from typing import Any


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
                row = {"State": item.get("state")}

                if "uninsured_rate" in item:
                    row["Value"] = item["uninsured_rate"]
                    row["Metric"] = "Uninsured Rate"

                elif "median_home_price" in item:
                    row["Value"] = item["median_home_price"]
                    row["Metric"] = "Median Home Price"

                elif "death_rate" in item:
                    row["Value"] = item["death_rate"]
                    row["Metric"] = "Death Rate"

                data.append(row)

        elif result.get("found"):
            row = {"State": result.get("state")}

            if "uninsured_rate" in result:
                row["Value"] = result["uninsured_rate"]
                row["Metric"] = "Uninsured Rate"

            elif "median_home_price" in result:
                row["Value"] = result["median_home_price"]
                row["Metric"] = "Median Home Price"

            elif "death_rate" in result:
                row["Value"] = result["death_rate"]
                row["Metric"] = "Death Rate"

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