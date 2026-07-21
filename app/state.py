from typing import TypedDict, List, Dict, Any, Optional


class ConversationState(TypedDict):
    session_id: str
    user_query: str

    chat_history: List[Dict[str, str]]
    conversation_summary: str

    query_type: Optional[str]
    standalone_query: Optional[str]
    current_intent: Optional[Dict[str, Any]]
    intent_history: List[Dict[str, Any]]
    intent_confirmation_needed: bool
    intent_confirmation_question: Optional[str]
    pending_confirmation: bool
    pending_intent: Optional[Dict[str, Any]]
    confirmation_response: Optional[bool]

    tasks: List[Dict[str, Any]]
    response_mode: Optional[str]

    task_results: List[Dict[str, Any]]

    graph_needed: bool
    graph_type: Optional[str]
    graph_title: Optional[str]
    graph_reason: Optional[str]
    graph_spec: Optional[Dict[str, Any]]

    final_response: Optional[str]
    recommended_chart: Optional[Dict[str, Any]]

    clarification_needed: bool
    clarification_question: Optional[str]

    error: Optional[str]