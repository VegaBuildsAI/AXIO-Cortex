"""Private connector for the governed AXIO opportunity-draft gateway."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from core.config import AXIO_INTERNAL_TOKEN, AXIO_OPPORTUNITY_GATEWAY_URL


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_NAME = 200
MAX_EMAIL = 320
MAX_COMPANY = 200
MAX_REQUIREMENT = 4000
MAX_SUMMARY = 6000


class OpportunityGatewayError(RuntimeError):
    """A safe, user-actionable failure from validation or gateway delivery."""


def source_task_id(task: str) -> str:
    """Create a stable, non-PII id for retry-safe correlation."""
    digest = hashlib.sha256((task or "").encode("utf-8")).hexdigest()[:24]
    return f"sales-intake-{digest}"


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(
        r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE
    ).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise OpportunityGatewayError("sales-intake did not return a JSON object.")
    try:
        value = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise OpportunityGatewayError("sales-intake returned invalid JSON.") from exc
    if not isinstance(value, dict):
        raise OpportunityGatewayError("sales-intake JSON must be an object.")
    return value


def _bounded_text(value: object, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def build_opportunity_payload(
    model_result: str,
    *,
    task_id: str,
    source: str = "axio-code-sales-intake",
) -> dict[str, Any]:
    """Validate the model's structured result before any external side effect."""
    data = _extract_json(model_result)
    lead = data.get("lead")
    if not isinstance(lead, dict):
        raise OpportunityGatewayError("sales-intake JSON is missing lead details.")

    name = _bounded_text(lead.get("name"), MAX_NAME)
    email = _bounded_text(lead.get("email"), MAX_EMAIL)
    company = _bounded_text(lead.get("company"), MAX_COMPANY)
    requirement = _bounded_text(data.get("requirement"), MAX_REQUIREMENT)
    summary = _bounded_text(data.get("conversation_summary"), MAX_SUMMARY)
    if not name or not email or not EMAIL_RE.fullmatch(email):
        raise OpportunityGatewayError("sales-intake requires a valid lead name and email.")
    if not requirement and not summary:
        raise OpportunityGatewayError("sales-intake requires a requirement or summary.")
    if data.get("consent_to_contact") is not True:
        raise OpportunityGatewayError("explicit consent_to_contact=true is required.")

    matched = data.get("matched_service_ids", [])
    if not isinstance(matched, list):
        matched = []
    matched = [
        item.strip()[:100]
        for item in matched
        if isinstance(item, str) and item.strip()
    ][:3]

    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        confidence = None
    elif not 0 <= float(confidence) <= 1:
        raise OpportunityGatewayError("confidence must be between 0 and 1.")

    return {
        "source": source,
        "source_task_id": task_id[:100],
        "lead": {"name": name, "email": email, "company": company},
        "requirement": requirement,
        "conversation_summary": summary,
        "matched_service_ids": matched,
        "confidence": confidence,
        "consent_to_contact": True,
    }


@dataclass(frozen=True)
class OpportunityGatewayClient:
    base_url: str
    token: str
    timeout: tuple[float, float] = (5.0, 15.0)

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("AXIO_OPPORTUNITY_GATEWAY_URL must be an HTTPS URL.")
        if not self.token.strip():
            raise ValueError("AXIO_INTERNAL_TOKEN is not configured.")

    @classmethod
    def from_environment(cls) -> "OpportunityGatewayClient | None":
        if not AXIO_OPPORTUNITY_GATEWAY_URL and not AXIO_INTERNAL_TOKEN:
            return None
        if not AXIO_OPPORTUNITY_GATEWAY_URL or not AXIO_INTERNAL_TOKEN:
            raise OpportunityGatewayError(
                "Both AXIO_OPPORTUNITY_GATEWAY_URL and AXIO_INTERNAL_TOKEN are required."
            )
        return cls(AXIO_OPPORTUNITY_GATEWAY_URL, AXIO_INTERNAL_TOKEN)

    def create_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.post(
                f"{self.base_url}/internal/opportunities/draft",
                headers={"Authorization": f"Bearer {self.token}"},
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise OpportunityGatewayError("Could not reach the opportunity gateway.") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise OpportunityGatewayError(
                f"Opportunity gateway returned HTTP {response.status_code}."
            ) from exc
        if not response.ok:
            code = (
                body.get("error", {}).get("code", "gateway_error")
                if isinstance(body, dict)
                else "gateway_error"
            )
            raise OpportunityGatewayError(
                f"Opportunity gateway rejected the draft ({code}, HTTP {response.status_code})."
            )
        if not isinstance(body, dict) or not body.get("id"):
            raise OpportunityGatewayError("Opportunity gateway returned no draft id.")
        return body


def submit_sales_intake(
    model_result: str,
    *,
    client: OpportunityGatewayClient,
    task_id: str,
) -> str:
    payload = build_opportunity_payload(model_result, task_id=task_id)
    draft = client.create_draft(payload)
    delivery = draft.get("delivery") if isinstance(draft.get("delivery"), dict) else {}
    return json.dumps(
        {
            "disposition": "opportunity_draft_created",
            "draft_id": draft["id"],
            "status": draft.get("status"),
            "notification_status": delivery.get("status"),
            "internal_destination": delivery.get("destination"),
            "human_approval_required": bool(
                draft.get("approval", {}).get("required", True)
            ),
        },
        ensure_ascii=False,
    )
