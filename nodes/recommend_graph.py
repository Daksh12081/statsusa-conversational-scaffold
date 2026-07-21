from typing import Any


def recommend_graph(state: dict[str, Any]) -> dict[str, Any]:
    print("Recommending graph...")

    intent = state.get("current_intent", {}) or {}
    intent_type = intent.get("intent_type", "")
    metrics = intent.get("metrics", [])
    years = intent.get("years", [])
    task_results = state.get("task_results", [])

    graph_needed = False
    graph_type = None
    graph_title = None
    graph_reason = None

    if intent_type == "compare":
        graph_needed = True
        graph_type = "bar"
        graph_reason = "Comparing values across multiple categories."

    elif intent_type == "rank":
        graph_needed = True
        graph_type = "horizontal_bar"
        graph_reason = "Ranking values from highest to lowest."

    elif intent_type == "trend":
        graph_needed = True
        graph_type = "line"
        graph_reason = "Showing change over time."

    elif intent_type == "distribution":
        graph_needed = True
        graph_type = "pie"
        graph_reason = "Showing parts of a whole."

    elif intent_type == "relationship":
        graph_needed = True
        graph_type = "scatter"
        graph_reason = "Showing relationship between two variables."

    if graph_needed:
        metric = metrics[0] if metrics else "Metric"

        if years:
            graph_title = f"{metric.title()} ({years[-1]})"
        else:
            graph_title = metric.title()

        print(f"  Recommended: {graph_type}")

    else:
        print("  No graph recommended")

    return {
        "graph_needed": graph_needed,
        "graph_type": graph_type,
        "graph_title": graph_title,
        "graph_reason": graph_reason,
    }