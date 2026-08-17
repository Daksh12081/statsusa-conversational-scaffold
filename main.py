import logging

from app.graph import graph
from nodes.summarize_memory import summarize_memory
print("✅ Imported graph")

logger = logging.getLogger(__name__)


SESSION_ID = "demo-session"
MAX_HISTORY_TURNS = 10
MAX_HISTORY_MESSAGES = MAX_HISTORY_TURNS * 2


def create_initial_state() -> dict:
    return {
        "session_id": SESSION_ID,
        "user_query": "",
        "chat_history": [],
        "conversation_summary": "",
        "query_type": None,
        "standalone_query": None,
        "current_intent": None,
        "intent_history": [],
        "intent_confirmation_needed": False,
        "intent_confirmation_question": None,
        "pending_confirmation": False,
        "pending_intent": None,
        "confirmation_response": None,
        "tasks": [],
        "response_mode": None,
        "task_results": [],
        "final_response": None,
        "recommended_chart": None,
        "clarification_needed": False,
        "clarification_question": None,
        "error": None,
    }


def reset_turn_fields(state: dict, user_query: str) -> dict:
    return {
        **state,
        "session_id": SESSION_ID,
        "user_query": user_query,
        "conversation_summary": state.get("conversation_summary", ""),
        "query_type": None,
        "standalone_query": None,
        "current_intent": None,
        "intent_confirmation_needed": False,
        "intent_confirmation_question": None,
        "pending_confirmation": False,
        "pending_intent": None,
        "confirmation_response": None,
        "tasks": [],
        "response_mode": None,
        "task_results": [],
        "final_response": None,
        "recommended_chart": None,
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



def parse_confirmation_response(user_query: str) -> bool | None:
    normalized = user_query.strip().lower()

    if normalized in {"yes", "y", "correct", "confirm", "confirmed", "proceed"}:
        return True

    if normalized in {"no", "n", "incorrect", "change", "cancel"}:
        return False

    return None

# Cap the chat history to the max allowed messages
def cap_chat_history(chat_history: list[dict]) -> list[dict]:
    return chat_history[-MAX_HISTORY_MESSAGES:]


def should_summarize(chat_history: list[dict]) -> bool:
    return len(chat_history) > MAX_HISTORY_MESSAGES


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

    if node_name == "extract_intent":
        intent = node_update.get("current_intent")
        confirmation_needed = node_update.get("intent_confirmation_needed")
        print("Extracting structured intent...")
        print(f"  Intent: {intent}")
        print(f"  Confirmation needed: {confirmation_needed}")
        return

    if node_name == "confirm_intent":
        question = node_update.get("final_response")
        print("Confirming interpreted intent...")
        print(f"  Question: {question}")
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
                if result.get("metric") and result.get("value") is not None:
                    print(f"    {result.get('metric')}: {result.get('value')}")
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
    print("✅ Starting main")
    config = {
        "configurable": {
            "thread_id": SESSION_ID,
        }
    }

    print("StatsUSA conversational scaffold")
    print("Type 'exit' or 'quit' to stop.\n")

    print("✅ Entering chat loop")
    while True:
        user_query = input("You: ").strip()

        if user_query.lower() in {"exit", "quit"}:
            print("Conversation ended.")
            break

        if not user_query:
            continue

        previous_state = get_thread_state(config)

        if previous_state.get("pending_confirmation"):
            confirmation = parse_confirmation_response(user_query)

            if confirmation is None:
                print("Please answer with 'yes' or 'no'.\n")
                continue

            if confirmation is False:
                rejection_message = "Okay. Please restate or correct your request."
                print(f"Assistant: {rejection_message}\n")

                graph.update_state(
                    config,
                    {
                        "pending_confirmation": False,
                        "pending_intent": None,
                        "confirmation_response": False,
                        "intent_confirmation_needed": False,
                        "intent_confirmation_question": None,
                    },
                )
                continue

            original_query = (
                previous_state.get("standalone_query")
                or previous_state.get("user_query")
            )

            turn_state = reset_turn_fields(previous_state, original_query)
            turn_state.update(
                {
                    "current_intent": previous_state.get("pending_intent"),
                    "pending_intent": previous_state.get("pending_intent"),
                    "pending_confirmation": False,
                    "confirmation_response": True,
                }
            )
        else:
            turn_state = reset_turn_fields(previous_state, user_query)

        print()
        try:
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
            print(f"Graph Spec: {result.get('graph_spec')}")
            print(f"Clarification Needed: {result.get('clarification_needed')}")
            print(f"Clarification Question: {result.get('clarification_question')}")
            print(f"Final Response: {result.get('final_response')}\n")

            assistant_message = build_assistant_history_message(result)
            updated_history = result.get("chat_history", []).copy()
            updated_history.append({"role": "user", "content": user_query})
            updated_history.append({"role": "assistant", "content": assistant_message})

            needs_summary = should_summarize(updated_history)

            if needs_summary:
                summary_update = summarize_memory(
                    {
                        "chat_history": updated_history,
                        "conversation_summary": result.get("conversation_summary", ""),
                    }
                )

                if summary_update.get("conversation_summary"):
                    result["conversation_summary"] = summary_update["conversation_summary"]

            updated_history = cap_chat_history(updated_history)

            graph.update_state(
                config,
                {
                    "chat_history": updated_history,
                    "conversation_summary": result.get("conversation_summary", ""),
                },
            )
        except Exception as exc:
            logger.error("Unexpected error while processing turn: %s", exc, exc_info=True)
            print(f"Assistant: Something went wrong processing that request. Please try again.\n")