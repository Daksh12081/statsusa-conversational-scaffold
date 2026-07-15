from typing import TypedDict, List, Dict, Any, Optional


class ConversationState(TypedDict):
    session_id: str
    user_query: str

    chat_history: List[Dict[str, str]]

    query_type: Optional[str]
    standalone_query: Optional[str]

    tasks: List[Dict[str, Any]]
    response_mode: Optional[str]

    task_results: List[Dict[str, Any]]

    final_response: Optional[str]

    clarification_needed: bool
    clarification_question: Optional[str]

    error: Optional[str]