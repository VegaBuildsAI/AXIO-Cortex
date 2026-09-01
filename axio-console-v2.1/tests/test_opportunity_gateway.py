import json

import pytest

from harness.opportunity_gateway import (
    OpportunityGatewayClient,
    OpportunityGatewayError,
    build_opportunity_payload,
    source_task_id,
    submit_sales_intake,
)


def valid_result(**overrides):
    value = {
        "lead": {"name": "Ada Example", "email": "ada@example.com", "company": "Example Co"},
        "requirement": "Automate revenue recognition review.",
        "conversation_summary": "Qualified inquiry from a finance team.",
        "matched_service_ids": ["revenue-automation"],
        "confidence": 0.85,
        "consent_to_contact": True,
    }
    value.update(overrides)
    return json.dumps(value)


def test_payload_requires_explicit_consent():
    with pytest.raises(OpportunityGatewayError, match="consent_to_contact"):
        build_opportunity_payload(valid_result(consent_to_contact=False), task_id="t-1")


def test_payload_does_not_invent_missing_lead_fields():
    with pytest.raises(OpportunityGatewayError, match="valid lead"):
        build_opportunity_payload(valid_result(lead={"name": "Ada Example"}), task_id="t-1")


def test_source_task_id_is_stable_and_does_not_include_task_text():
    first = source_task_id("same task")
    assert first == source_task_id("same task")
    assert "same task" not in first


def test_client_rejects_non_https_gateway():
    with pytest.raises(ValueError, match="HTTPS"):
        OpportunityGatewayClient("http://localhost:8787", "secret")


def test_submit_creates_internal_draft_without_exposing_token(monkeypatch):
    test_token = "unit-test-token"

    class FakeResponse:
        ok = True
        status_code = 201

        @staticmethod
        def json():
            return {
                "id": "draft-123",
                "status": "DRAFT_PENDING_REVIEW",
                "approval": {"required": True},
                "delivery": {"status": "pending", "destination": "axiostaging@proton.me"},
            }

    seen = {}

    def fake_post(url, **kwargs):
        seen.update(url=url, kwargs=kwargs)
        return FakeResponse()

    monkeypatch.setattr("harness.opportunity_gateway.requests.post", fake_post)
    result = submit_sales_intake(
        valid_result(),
        client=OpportunityGatewayClient("https://gateway.example", test_token),
        task_id="t-1",
    )
    assert json.loads(result)["draft_id"] == "draft-123"
    assert seen["kwargs"]["headers"]["Authorization"] == f"Bearer {test_token}"
    assert test_token not in result
