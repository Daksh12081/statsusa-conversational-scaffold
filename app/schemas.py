from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class QueryAnalysis(BaseModel):
    query_type: Literal[
        "simple",
        "follow_up",
        "multi_intent",
        "complex",
        "clarification",
    ]

    standalone_query: Optional[str] = None
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


class StructuredIntent(BaseModel):
    intent_type: Literal[
        "retrieve",
        "compare",
        "rank",
        "trend",
        "combine",
        "clarify",
    ]

    domains: List[Literal["insurance", "housing", "death"]] = Field(
        default_factory=list
    )
    metrics: List[str] = Field(default_factory=list)
    geographies: List[str] = Field(default_factory=list)
    years: List[int] = Field(default_factory=list)

    visualization_requested: bool = False
    requested_chart_type: Optional[str] = None

    confirmed: bool = False


class Task(BaseModel):
    task_id: str
    domain: Literal["insurance", "housing", "death"]
    query: str
    depends_on: List[str] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    tasks: List[Task] = Field(default_factory=list)
    response_mode: Optional[
        Literal["single", "separate", "combine", "compare"]
    ] = "single"