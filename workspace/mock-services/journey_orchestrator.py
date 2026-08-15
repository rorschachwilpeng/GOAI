"""Deterministic automatic steps for the linked-journey rehearsal."""

from __future__ import annotations

from typing import Any

from linked_journey import LinkedJourney
from linked_journey_bridge import LinkedJourneyBridge


class JourneyOrchestrator:
    """Advance only the two non-human events in the linked Demo journey."""

    def __init__(self, journey: LinkedJourney, bridge: LinkedJourneyBridge) -> None:
        if journey.case_id != bridge.case_id:
            raise ValueError("Journey and bridge must belong to the same Case")
        self.journey = journey
        self.bridge = bridge

    def advance_second_exception(
        self,
        exception_id: str,
        occurred_at: str,
    ) -> dict[str, Any]:
        case = self.journey.recur_supplier_exception(exception_id, occurred_at)
        matrix_event_id = self.bridge.publish_automatic_event(
            {
                "event_type": "SUPPLIER_EXCEPTION_RECURRED",
                "business_event_id": f"{self.journey.case_id}-INCIDENT-2",
                "case_id": self.journey.case_id,
                "incident_sequence": case["incident_sequence"],
                "state": case["case_state"],
                "sender_agent": "MANAGER",
                "receiver": "RESOLUTION",
                "conclusion": "A second synthetic supplier exception was accepted.",
                "next_action": "Prepare the second replacement plan.",
                "evidence_ref": f"supplier-exception://{exception_id}",
                "occurred_at": occurred_at,
            }
        )
        return {"case": case, "matrix_event_id": matrix_event_id}

    def simulate_customer_confirmation_timeout(
        self,
        occurred_at: str,
    ) -> dict[str, Any]:
        case = self.journey.timeout_customer_confirmation(occurred_at)
        matrix_event_id = self.bridge.publish_automatic_event(
            {
                "event_type": "CUSTOMER_CONFIRMATION_TIMEOUT",
                "business_event_id": f"{self.journey.case_id}-CONFIRMATION-TIMEOUT",
                "case_id": self.journey.case_id,
                "incident_sequence": case["incident_sequence"],
                "state": case["case_state"],
                "sender_agent": "MANAGER",
                "receiver": "FRONTLINE",
                "conclusion": "The deterministic customer confirmation deadline elapsed.",
                "next_action": "Wait for a late reply on the same Case.",
                "evidence_ref": f"case-timer://{self.journey.case_id}",
                "occurred_at": occurred_at,
            }
        )
        return {"case": case, "matrix_event_id": matrix_event_id}

