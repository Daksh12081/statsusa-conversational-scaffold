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