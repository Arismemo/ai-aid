import pytest
from pydantic import ValidationError

from ai_aid.models import (
    AskRequest, AnswerRequest, RequestSummary, RequestDetail, AnswerOut,
)


def _ask_payload(**overrides):
    base = {
        "client_id": "alice",
        "model": "haiku-4.5",
        "goal": "g",
        "context": "c",
        "tried": "t",
        "error": None,
        "constraints": None,
        "question": "q",
    }
    base.update(overrides)
    return base


def test_ask_accepts_valid():
    m = AskRequest(**_ask_payload())
    assert m.client_id == "alice"
    assert m.error is None


def test_ask_rejects_empty_string_required():
    with pytest.raises(ValidationError):
        AskRequest(**_ask_payload(goal=""))


def test_ask_rejects_whitespace_only_required():
    with pytest.raises(ValidationError):
        AskRequest(**_ask_payload(question="   "))


def test_ask_optional_fields_can_be_empty_string_treated_as_none():
    m = AskRequest(**_ask_payload(error="", constraints="  "))
    assert m.error is None
    assert m.constraints is None


def test_ask_rejects_missing_required_field():
    payload = _ask_payload()
    del payload["client_id"]
    with pytest.raises(ValidationError):
        AskRequest(**payload)


def test_answer_requires_summary():
    with pytest.raises(ValidationError):
        AnswerRequest(
            solver_client_id="bob",
            solver_model="m",
            summary="",
            solution=None,
            reasoning=None,
            caveats=None,
        )


def test_answer_optional_fields_default_none():
    a = AnswerRequest(
        solver_client_id="bob", solver_model="m", summary="ok"
    )
    assert a.solution is None
    assert a.reasoning is None
    assert a.caveats is None


def test_request_summary_serializes_with_answer_count():
    s = RequestSummary(
        id="x", client_id="alice", model="haiku-4.5", goal="g",
        status="open", created_at=1, closed_at=None, answer_count=2,
    )
    assert s.model_dump()["answer_count"] == 2
