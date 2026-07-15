from app.graph import graph


SESSION_ID = "demo-session"


def create_initial_state() -> dict:
    return {
        "session_id": SESSION_ID,
        "user_query": "",
        "chat_history": [],
        "query_type": None,
        "standalone_query": None,
        "tasks": [],
        "response_mode": None,
        "task_results": [],
        "final_response": None,
        "clarification_needed": False,
        "clarification_question": None,
        "error": None,
    }


def reset_turn_fields(state: dict, user_query: str) -> dict:
    return {
        **state,
        "session_id": SESSION_ID,
        "user_query": user_query,
        "query_type": None,
        "standalone_query": None,
        "tasks": [],
        "response_mode": None,
        "task_results": [],
        "final_response": None,
        "clarification_needed": False,
        "clarification_question": None,
        "error": None,
    }


def build_assistant_history_message(result: dict) -> str:
    if result.get("final_response"):
        return result["final_response"]

    tasks = result.get("tasks", [])
    if tasks:
        return f"Planned tasks: {tasks}"

    return "The request was analysed, but no response or tasks were produced."



def get_thread_state(config: dict) -> dict:
    snapshot = graph.get_state(config)

    if snapshot.values:
        return dict(snapshot.values)

    return create_initial_state()


def print_node_update(node_name: str, node_update: dict) -> None:
    if node_name == "analyze_query":
        query_type = node_update.get("query_type")
        print("Analyzing query...")
        print(f"  Detected type: {query_type}")
        return

    if node_name == "clarification":
        question = node_update.get("final_response")
        print("Preparing clarification...")
        print(f"  Question: {question}")
        return

    if node_name == "resolve_context":
        standalone_query = node_update.get("standalone_query")
        print("Resolving conversation context...")
        print(f"  Standalone query: {standalone_query}")
        return

    if node_name == "create_task_plan":
        tasks = node_update.get("tasks", [])
        response_mode = node_update.get("response_mode")
        print("Planning tasks...")
        print(f"  Created {len(tasks)} task(s)")

        for task in tasks:
            task_id = task.get("task_id")
            domain = task.get("domain")
            query = task.get("query")
            depends_on = task.get("depends_on", [])

            print(f"  - {task_id}: {domain} | {query}")
            if depends_on:
                print(f"    Depends on: {', '.join(depends_on)}")

        print(f"  Response mode: {response_mode}")
        return

    if node_name == "execute_tasks":
        task_results = node_update.get("task_results", [])
        print("Executing tasks...")
        print(f"  Completed {len(task_results)} task(s)")

        for task_result in task_results:
            task_id = task_result.get("task_id")
            success = task_result.get("success", True)

            if not success:
                print(f"  - {task_id}: failed")
                print(f"    {task_result.get('message')}")
                continue

            result = task_result.get("result", {})
            print(f"  - {task_id}: completed")

            if result.get("state"):
                print(
                    f"    Retrieved {result.get('domain')} data for "
                    f"{result.get('state')} ({result.get('year')})"
                )
            elif result.get("items"):
                print(f"    Retrieved {len(result['items'])} result item(s)")
        return

    if node_name == "generate_response":
        final_response = node_update.get("final_response")
        print("Generating response...")
        print(f"  Final answer: {final_response}")
        return

    print(f"Completed {node_name}...")


if __name__ == "__main__":
    config = {
        "configurable": {
            "thread_id": SESSION_ID,
        }
    }

    print("StatsUSA conversational scaffold")
    print("Type 'exit' or 'quit' to stop.\n")

    while True:
        user_query = input("You: ").strip()

        if user_query.lower() in {"exit", "quit"}:
            print("Conversation ended.")
            break

        if not user_query:
            continue

        previous_state = get_thread_state(config)
        turn_state = reset_turn_fields(previous_state, user_query)

        print()
        for update in graph.stream(
            turn_state,
            config=config,
            stream_mode="updates",
        ):
            for node_name, node_update in update.items():
                print_node_update(node_name, node_update)

        result = get_thread_state(config)

        print("\n===== GRAPH OUTPUT =====")
        print(f"Query Type: {result.get('query_type')}")
        print(f"Standalone Query: {result.get('standalone_query')}")
        print(f"Tasks: {result.get('tasks')}")
        print(f"Task Results: {result.get('task_results')}")
        print(f"Response Mode: {result.get('response_mode')}")
        print(f"Clarification Needed: {result.get('clarification_needed')}")
        print(f"Clarification Question: {result.get('clarification_question')}")
        print(f"Final Response: {result.get('final_response')}\n")

        assistant_message = build_assistant_history_message(result)
        updated_history = result.get("chat_history", []).copy()
        updated_history.append({"role": "user", "content": user_query})
        updated_history.append({"role": "assistant", "content": assistant_message})

        graph.update_state(
            config,
            {
                "chat_history": updated_history,
            },
        )