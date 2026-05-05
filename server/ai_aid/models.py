from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


def _required_nonblank(v: str) -> str:
    if v is None or not str(v).strip():
        raise ValueError("must be a non-empty string")
    return v


def _optional_blank_to_none(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    if not str(v).strip():
        return None
    return v


class AskRequest(BaseModel):
    client_id: str
    model: str
    goal: str
    context: str
    tried: str
    error: Optional[str] = None
    constraints: Optional[str] = None
    question: str

    @field_validator("client_id", "model", "goal", "context", "tried", "question")
    @classmethod
    def _nonblank(cls, v: str) -> str:
        return _required_nonblank(v)

    @field_validator("error", "constraints")
    @classmethod
    def _blank_to_none(cls, v: Optional[str]) -> Optional[str]:
        return _optional_blank_to_none(v)


class AnswerRequest(BaseModel):
    solver_client_id: str
    solver_model: str
    summary: str
    solution: Optional[str] = None
    reasoning: Optional[str] = None
    caveats: Optional[str] = None

    @field_validator("solver_client_id", "solver_model", "summary")
    @classmethod
    def _nonblank(cls, v: str) -> str:
        return _required_nonblank(v)

    @field_validator("solution", "reasoning", "caveats")
    @classmethod
    def _blank_to_none(cls, v: Optional[str]) -> Optional[str]:
        return _optional_blank_to_none(v)


class RequestSummary(BaseModel):
    id: str
    client_id: str
    model: str
    goal: str
    status: Literal["open", "closed"]
    created_at: int
    closed_at: Optional[int]
    answer_count: int


class AnswerOut(BaseModel):
    id: str
    solver_client_id: str
    solver_model: str
    summary: str
    solution: Optional[str]
    reasoning: Optional[str]
    caveats: Optional[str]
    created_at: int


class RequestDetail(BaseModel):
    id: str
    client_id: str
    model: str
    goal: str
    context: str
    tried: str
    error: Optional[str]
    constraints: Optional[str]
    question: str
    status: Literal["open", "closed"]
    created_at: int
    closed_at: Optional[int]
    answers: list[AnswerOut]


class CreateResponse(BaseModel):
    id: str
    status: Literal["open", "closed"]
    created_at: int
