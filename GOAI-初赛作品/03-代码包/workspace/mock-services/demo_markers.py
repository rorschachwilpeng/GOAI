"""Ordered, credential-free linked-journey marker manifests."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


MARKERS = (
    "DEMO_START",
    "SCENE_1_END",
    "SCENE_2_END",
    "TIMEOUT_SIMULATED",
    "DEMO_END",
)
MANIFEST_FIELDS = {
    "run_id",
    "case_id",
    "project_room_id",
    "conversation_id",
    "incident_count",
    "execution_count",
    "verification_count",
    "final_case_state",
    "markers",
}
MARKER_FIELDS = {
    "marker",
    "occurred_at",
    "matrix_event_id",
    "business_event_id",
}


class MarkerError(ValueError):
    pass


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarkerError(f"{field} is required")
    return value


def _validate_timestamp(value: Any) -> None:
    timestamp = _required_string(value, "occurred_at")
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise MarkerError("occurred_at must be an RFC3339 timestamp") from error


def validate_manifest(manifest: dict[str, Any]) -> bool:
    """Validate a generated or loaded manifest against the T012 contract."""

    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_FIELDS:
        raise MarkerError("Manifest fields are incomplete or unexpected")

    for field in (
        "run_id",
        "case_id",
        "project_room_id",
        "conversation_id",
        "final_case_state",
    ):
        _required_string(manifest[field], field)

    for field in ("incident_count", "execution_count", "verification_count"):
        value = manifest[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise MarkerError(f"{field} must be a non-negative integer")

    marker_items = manifest["markers"]
    if not isinstance(marker_items, list) or len(marker_items) != len(MARKERS):
        raise MarkerError("Manifest marker set is incomplete")

    seen_matrix_events: set[str] = set()
    seen_business_events: set[str] = set()
    for expected_marker, item in zip(MARKERS, marker_items, strict=True):
        if not isinstance(item, dict) or set(item) != MARKER_FIELDS:
            raise MarkerError("Marker fields are incomplete or unexpected")
        if item["marker"] != expected_marker:
            raise MarkerError("Marker is out of order or duplicated")
        _validate_timestamp(item["occurred_at"])
        matrix_event_id = _required_string(item["matrix_event_id"], "matrix_event_id")
        business_event_id = _required_string(
            item["business_event_id"],
            "business_event_id",
        )
        if matrix_event_id in seen_matrix_events or business_event_id in seen_business_events:
            raise MarkerError("Marker references must be unique")
        seen_matrix_events.add(matrix_event_id)
        seen_business_events.add(business_event_id)

    return True


class DemoMarkers:
    def __init__(
        self,
        run_id: str,
        case_id: str,
        project_room_id: str,
        conversation_id: str,
    ) -> None:
        self.run_id = _required_string(run_id, "run_id")
        self.case_id = _required_string(case_id, "case_id")
        self.project_room_id = _required_string(project_room_id, "project_room_id")
        self.conversation_id = _required_string(conversation_id, "conversation_id")
        self.items: list[dict[str, str]] = []

    def record(
        self,
        marker: str,
        matrix_event_id: str,
        business_event_id: str,
        occurred_at: str | None = None,
    ) -> dict[str, str]:
        expected = MARKERS[len(self.items)] if len(self.items) < len(MARKERS) else None
        if marker != expected:
            raise MarkerError("Marker is out of order or duplicated")

        item = {
            "marker": marker,
            "occurred_at": occurred_at or datetime.now(timezone.utc).isoformat(),
            "matrix_event_id": _required_string(matrix_event_id, "matrix_event_id"),
            "business_event_id": _required_string(business_event_id, "business_event_id"),
        }
        _validate_timestamp(item["occurred_at"])
        if any(
            existing["matrix_event_id"] == item["matrix_event_id"]
            or existing["business_event_id"] == item["business_event_id"]
            for existing in self.items
        ):
            raise MarkerError("Marker references must be unique")

        self.items.append(item)
        return dict(item)

    def manifest(
        self,
        incident_count: int,
        execution_count: int,
        verification_count: int,
        final_case_state: str,
    ) -> dict[str, Any]:
        manifest = {
            "run_id": self.run_id,
            "case_id": self.case_id,
            "project_room_id": self.project_room_id,
            "conversation_id": self.conversation_id,
            "incident_count": incident_count,
            "execution_count": execution_count,
            "verification_count": verification_count,
            "final_case_state": final_case_state,
            "markers": deepcopy(self.items),
        }
        validate_manifest(manifest)
        return manifest
