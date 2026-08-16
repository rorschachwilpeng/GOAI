"""Credential-safe local Matrix transport for the AgentTeams rehearsal.

All Matrix credentials remain inside the existing Manager container.  The host
process receives only selected message fields and event identifiers.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from typing import Any, Callable

from linked_journey_bridge import AgentReply, BridgeError


class AgentTeamsTransportError(RuntimeError):
    pass


MATRIX_BRIDGE_SCRIPT = r"""
set -euo pipefail
source /opt/agentteams/scripts/lib/agentteams-env.sh
if [ -f /data/agentteams-secrets.env ]; then
  source /data/agentteams-secrets.env
fi
payload=$(cat)
action=$(printf '%s' "$payload" | jq -r '.action')
as_user=$(printf '%s' "$payload" | jq -r '.as_user // "admin"')
if [ "$as_user" = manager ]; then
  login_user=manager
  login_password=${AGENTTEAMS_MANAGER_PASSWORD}
else
  login_user=${AGENTTEAMS_ADMIN_USER}
  login_password=${AGENTTEAMS_ADMIN_PASSWORD}
fi
login_payload=$(jq -cn --arg user "$login_user" --arg password "$login_password" \
  '{type:"m.login.password",identifier:{type:"m.id.user",user:$user},password:$password}')
token=$(curl -fsS -X POST "${AGENTTEAMS_MATRIX_URL}/_matrix/client/v3/login" \
  -H 'Content-Type: application/json' \
  -d "$login_payload" \
  | jq -r '.access_token // empty')
test -n "$token"
room_id=$(printf '%s' "$payload" | jq -r '.room_id')
room_encoded=$(printf '%s' "$room_id" | jq -sRr @uri)

if [ "$action" = send ]; then
  txn_id=$(printf '%s' "$payload" | jq -r '.txn_id')
  content=$(printf '%s' "$payload" | jq -c '.content')
  curl -fsS -X PUT \
    "${AGENTTEAMS_MATRIX_URL}/_matrix/client/v3/rooms/${room_encoded}/send/m.room.message/${txn_id}" \
    -H "Authorization: Bearer ${token}" \
    -H 'Content-Type: application/json' \
    -d "$content" | jq '{event_id}'
elif [ "$action" = messages ]; then
  limit=$(printf '%s' "$payload" | jq -r '.limit')
  curl -fsS -G \
    "${AGENTTEAMS_MATRIX_URL}/_matrix/client/v3/rooms/${room_encoded}/messages" \
    -H "Authorization: Bearer ${token}" \
    --data-urlencode 'dir=b' \
    --data-urlencode "limit=${limit}" \
    | jq '{events: [.chunk[] | select(.type == "m.room.message") | {
        event_id,
        sender,
        origin_server_ts,
        body: (.content.body // "")
      }]}'
else
  exit 64
fi
"""


WORKER_MATRIX_SEND_SCRIPT = r"""
set -euo pipefail
payload=$(cat)
worker_name=$(printf '%s' "$payload" | jq -r '.worker_name')
room_id=$(printf '%s' "$payload" | jq -r '.room_id')
body=$(printf '%s' "$payload" | jq -r '.body')
txn_id=$(printf '%s' "$payload" | jq -r '.txn_id')
config="/root/.copaw-worker/${worker_name}/openclaw.json"
test -f "$config"
token=$(jq -r '.channels.matrix.accessToken // empty' "$config")
homeserver=$(jq -r '.channels.matrix.homeserver // empty' "$config")
test -n "$token"
test -n "$homeserver"
room_encoded=$(printf '%s' "$room_id" | jq -sRr @uri)
content=$(jq -cn --arg body "$body" '{msgtype:"m.text",body:$body}')
curl -fsS -X PUT \
  "${homeserver}/_matrix/client/v3/rooms/${room_encoded}/send/m.room.message/${txn_id}" \
  -H "Authorization: Bearer ${token}" \
  -H 'Content-Type: application/json' \
  -d "$content" | jq '{event_id}'
"""


def _json_object_from_body(body: str) -> dict[str, Any]:
    candidate = body.strip()
    first_line, separator, remainder = candidate.partition("\n")
    if not separator:
        first_line, separator, remainder = candidate.partition(r"\n")
    mention = first_line.removeprefix("$")
    if separator and mention.startswith("@") and ":" in mention:
        candidate = remainder.strip()
    if candidate.startswith("```json") and candidate.endswith("```"):
        candidate = candidate[7:-3].strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise BridgeError("Agent response must contain one JSON object only") from error
    if not isinstance(payload, dict):
        raise BridgeError("Agent response must be a JSON object")
    return payload


class MatrixAdminClient:
    def __init__(
        self,
        *,
        manager_container: str = "agentteams-manager",
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.manager_container = manager_container
        self.command_runner = command_runner

    def _call(self, payload: dict[str, Any]) -> dict[str, Any]:
        completed = self.command_runner(
            [
                "docker",
                "exec",
                "-i",
                self.manager_container,
                "bash",
                "-lc",
                MATRIX_BRIDGE_SCRIPT,
            ],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        if completed.returncode != 0:
            raise AgentTeamsTransportError("Local Matrix bridge request failed")
        try:
            response = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise AgentTeamsTransportError("Local Matrix bridge returned invalid JSON") from error
        if not isinstance(response, dict):
            raise AgentTeamsTransportError("Local Matrix bridge returned an invalid response")
        return response

    def _send(
        self,
        room_id: str,
        body: str,
        as_user: str,
        mentions: list[str] | None = None,
    ) -> str:
        if as_user == "manager":
            return self._send_manager_copaw(room_id, body, mentions)
        content: dict[str, Any] = {"msgtype": "m.text", "body": body}
        if mentions:
            content["m.mentions"] = {"user_ids": mentions}
        response = self._call(
            {
                "action": "send",
                "as_user": as_user,
                "room_id": room_id,
                "txn_id": f"goai-{uuid.uuid4().hex}",
                "content": content,
            }
        )
        event_id = response.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise AgentTeamsTransportError("Matrix send did not return an event ID")
        return event_id

    def _send_manager_copaw(
        self,
        room_id: str,
        body: str,
        mentions: list[str] | None,
        *,
        prefix_mention: bool = True,
    ) -> str:
        if not mentions or len(mentions) != 1:
            raise AgentTeamsTransportError(
                "Manager Project event requires one target Agent mention"
            )
        message_body = f"{mentions[0]}\n{body}" if prefix_mention else body
        started_ms = int(time.time() * 1000) - 1000
        completed = self.command_runner(
            [
                "docker",
                "exec",
                self.manager_container,
                "copaw",
                "channels",
                "send",
                "--agent-id",
                "default",
                "--channel",
                "matrix",
                "--target-session",
                room_id,
                "--target-user",
                mentions[0],
                "--text",
                message_body,
            ],
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        if completed.returncode != 0:
            raise AgentTeamsTransportError("Manager CoPaw send failed")
        event = self.wait_for_message(
            room_id=room_id,
            sender="@manager:matrix-local.agentteams.io:18080",
            after_ms=started_ms,
            predicate=lambda value: value in {message_body, f"${message_body}"},
            timeout_seconds=15,
        )
        return str(event["event_id"])

    def send_admin(self, room_id: str, body: str) -> str:
        return self._send(room_id, body, "admin")

    def send_manager(
        self,
        room_id: str,
        body: str,
        mentions: list[str] | None = None,
    ) -> str:
        return self._send(room_id, body, "manager", mentions)

    def send_manager_display(
        self,
        room_id: str,
        body: str,
        *,
        target_user: str,
    ) -> str:
        """Publish a Manager-authored display event without waking a Worker."""

        return self._send_manager_copaw(
            room_id,
            body,
            [target_user],
            prefix_mention=False,
        )

    def recent_messages(self, room_id: str, limit: int = 50) -> list[dict[str, Any]]:
        response = self._call(
            {"action": "messages", "room_id": room_id, "limit": limit}
        )
        events = response.get("events")
        if not isinstance(events, list):
            raise AgentTeamsTransportError("Matrix messages response is invalid")
        return [event for event in events if isinstance(event, dict)]

    def wait_for_message(
        self,
        *,
        room_id: str,
        sender: str,
        after_ms: int,
        predicate: Callable[[str], bool],
        timeout_seconds: float = 90.0,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            for event in self.recent_messages(room_id):
                if event.get("sender") != sender:
                    continue
                timestamp = event.get("origin_server_ts")
                if isinstance(timestamp, bool) or not isinstance(timestamp, int):
                    continue
                body = event.get("body")
                if timestamp >= after_ms and isinstance(body, str) and predicate(body):
                    return event
            time.sleep(1)
        raise AgentTeamsTransportError("Timed out waiting for the expected Matrix event")


class DockerAgentTeamsTransport:
    """Route the customer bridge through existing AgentTeams Worker Rooms."""

    def __init__(
        self,
        *,
        matrix: MatrixAdminClient,
        frontline_room_id: str,
        resolution_room_id: str,
        verification_room_id: str,
        project_room_id: str,
        frontline_matrix_id: str = "@frontline:matrix-local.agentteams.io:18080",
        resolution_matrix_id: str = "@resolution:matrix-local.agentteams.io:18080",
        verification_matrix_id: str = "@verification:matrix-local.agentteams.io:18080",
        ensure_ready: Callable[[str], None] | None = None,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.matrix = matrix
        self.frontline_room_id = frontline_room_id
        self.resolution_room_id = resolution_room_id
        self.verification_room_id = verification_room_id
        self.project_room_id = project_room_id
        self.frontline_matrix_id = frontline_matrix_id
        self.resolution_matrix_id = resolution_matrix_id
        self.verification_matrix_id = verification_matrix_id
        self._ensure_ready = ensure_ready or (lambda _worker: None)
        self.command_runner = command_runner

    @classmethod
    def from_runtime(
        cls,
        *,
        matrix: MatrixAdminClient,
        project_room_id: str,
        manager_container: str = "agentteams-manager",
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> "DockerAgentTeamsTransport":
        lifecycle_script = (
            "/opt/agentteams/agent/skills/worker-management/scripts/"
            "lifecycle-worker.sh"
        )

        def ensure_ready(worker_name: str) -> None:
            completed = command_runner(
                [
                    "docker",
                    "exec",
                    manager_container,
                    "bash",
                    lifecycle_script,
                    "--action",
                    "ensure-ready",
                    "--worker",
                    worker_name,
                ],
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            if completed.returncode != 0:
                raise AgentTeamsTransportError(
                    f"Could not wake required Worker: {worker_name}"
                )

        for name in ("frontline", "resolution", "verification"):
            ensure_ready(name)
        completed = command_runner(
            ["docker", "exec", manager_container, "agt", "get", "workers", "-o", "json"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            raise AgentTeamsTransportError("Could not read AgentTeams Worker state")
        try:
            workers = json.loads(completed.stdout).get("workers", [])
        except (AttributeError, json.JSONDecodeError) as error:
            raise AgentTeamsTransportError("AgentTeams Worker state is invalid") from error
        by_name = {
            worker.get("name"): worker
            for worker in workers
            if isinstance(worker, dict) and isinstance(worker.get("name"), str)
        }
        required = {}
        for name in ("frontline", "resolution", "verification"):
            worker = by_name.get(name)
            if not worker or worker.get("phase") not in {"Running", "Sleeping"}:
                raise AgentTeamsTransportError(f"Required Worker is not ready: {name}")
            room_id = worker.get("roomID")
            matrix_id = worker.get("matrixUserID")
            if not isinstance(room_id, str) or not isinstance(matrix_id, str):
                raise AgentTeamsTransportError(f"Worker routing is incomplete: {name}")
            required[name] = (room_id, matrix_id)
        return cls(
            matrix=matrix,
            frontline_room_id=required["frontline"][0],
            resolution_room_id=required["resolution"][0],
            verification_room_id=required["verification"][0],
            project_room_id=project_room_id,
            frontline_matrix_id=required["frontline"][1],
            resolution_matrix_id=required["resolution"][1],
            verification_matrix_id=required["verification"][1],
            ensure_ready=ensure_ready,
            command_runner=command_runner,
        )

    def _send_worker_display(
        self,
        *,
        worker_name: str,
        sender_matrix_id: str,
        body: str,
    ) -> dict[str, Any]:
        """Publish one exact Project display event through a Worker channel."""

        self._ensure_ready(worker_name)
        started_ms = int(time.time() * 1000) - 1000
        completed = self.command_runner(
            [
                "docker",
                "exec",
                "-i",
                f"agentteams-worker-{worker_name}",
                "bash",
                "-lc",
                WORKER_MATRIX_SEND_SCRIPT,
            ],
            input=json.dumps(
                {
                    "worker_name": worker_name,
                    "room_id": self.project_room_id,
                    "body": body,
                    "txn_id": f"goai-{uuid.uuid4().hex}",
                },
                ensure_ascii=False,
            ),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        if completed.returncode != 0:
            raise AgentTeamsTransportError(
                f"Could not publish {worker_name} Project display event"
            )
        event = self.matrix.wait_for_message(
            room_id=self.project_room_id,
            sender=sender_matrix_id,
            after_ms=started_ms,
            predicate=lambda value: value in {body, f"${body}"},
            timeout_seconds=15,
        )
        return {
            "matrix_event_id": str(event["event_id"]),
            "payload": _json_object_from_body(str(event["body"])),
        }

    def request_frontline(self, envelope: dict[str, Any]) -> AgentReply:
        self._ensure_ready("frontline")
        started_ms = int(time.time() * 1000) - 1000
        requested_reply = {
            "event_type": "CUSTOMER_SAFE_REPLY",
            "case_id": envelope["case_id"],
            "conversation_id": envelope["conversation_id"],
            "message_type": "STATUS",
            "body": "<one customer-safe sentence>",
        }
        prompt = (
            f"{self.frontline_matrix_id} [GOAI CUSTOMER BRIDGE]\n"
            "Process this trusted synthetic Customer Chat event using your assigned Skill. "
            "Do not expose Tool details, internal policy, IDs, or reasoning.\n"
            f"trusted_event={json.dumps(envelope, ensure_ascii=False, separators=(',', ':'))}\n"
            "Reply in this Worker Room with exactly one JSON object and no Markdown: "
            f"{json.dumps(requested_reply, ensure_ascii=False, separators=(',', ':'))}"
        )
        self.matrix.send_admin(self.frontline_room_id, prompt)

        def is_customer_reply(body: str) -> bool:
            try:
                return _json_object_from_body(body).get("event_type") == "CUSTOMER_SAFE_REPLY"
            except BridgeError:
                return False

        event = self.matrix.wait_for_message(
            room_id=self.frontline_room_id,
            sender=self.frontline_matrix_id,
            after_ms=started_ms,
            predicate=is_customer_reply,
        )
        return AgentReply(
            matrix_event_id=str(event["event_id"]),
            payload=_json_object_from_body(str(event["body"])),
        )

    def request_frontline_project_handoff(
        self,
        event: dict[str, Any],
        *,
        timeout_seconds: float = 90.0,
    ) -> dict[str, Any]:
        """Ask Frontline to publish its own mentioned Project Room handoff."""

        if event.get("sender_agent") != "FRONTLINE":
            raise AgentTeamsTransportError("Project handoff must be authored by Frontline")
        body = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        return self._send_worker_display(
            worker_name="frontline",
            sender_matrix_id=self.frontline_matrix_id,
            body=body,
        )

    def request_resolution_project_update(
        self,
        event: dict[str, Any],
        *,
        source_event_id: str,
        timeout_seconds: float = 90.0,
    ) -> dict[str, Any]:
        if event.get("sender_agent") != "RESOLUTION":
            raise AgentTeamsTransportError("Project update must be authored by Resolution")
        self._ensure_ready("resolution")
        source = next(
            (
                item
                for item in self.matrix.recent_messages(self.project_room_id, limit=100)
                if item.get("event_id") == source_event_id
            ),
            None,
        )
        if source is None:
            raise AgentTeamsTransportError("Resolution display source event does not exist")
        try:
            source_payload = _json_object_from_body(str(source.get("body", "")))
        except BridgeError as error:
            raise AgentTeamsTransportError(
                "Resolution display source event is not structured"
            ) from error
        allowed_source = (
            source.get("sender") == self.frontline_matrix_id
            and source_payload.get("event_type") == "ORDER_LINKED"
        ) or (
            source.get("sender") == "@manager:matrix-local.agentteams.io:18080"
            and source_payload.get("event_type") == "SUPPLIER_EXCEPTION_RECURRED"
        )
        if not allowed_source or source_payload.get("case_id") != event.get("case_id"):
            raise AgentTeamsTransportError(
                "Resolution display source event is not authorized for this Case"
            )
        body = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        return self._send_worker_display(
            worker_name="resolution",
            sender_matrix_id=self.resolution_matrix_id,
            body=body,
        )

    def wait_resolution_project_update(
        self,
        event: dict[str, Any],
        *,
        source_event_id: str,
        timeout_seconds: float = 90.0,
    ) -> dict[str, Any]:
        """Consume Resolution's direct reply to a real Project Room handoff."""

        if event.get("sender_agent") != "RESOLUTION":
            raise AgentTeamsTransportError("Project update must be authored by Resolution")
        self._ensure_ready("resolution")
        source = next(
            (
                item
                for item in self.matrix.recent_messages(self.project_room_id, limit=100)
                if item.get("event_id") == source_event_id
            ),
            None,
        )
        if source is None or source.get("sender") not in {
            self.frontline_matrix_id,
            "@manager:matrix-local.agentteams.io:18080",
        }:
            raise AgentTeamsTransportError(
                "Resolution Project update requires a real Project Room source event"
            )
        def is_expected_resolution_event(body: str) -> bool:
            try:
                payload = _json_object_from_body(body)
            except BridgeError:
                return False
            return (
                payload.get("event_type") == event.get("event_type")
                and payload.get("case_id") == event.get("case_id")
            )

        matrix_event = self.matrix.wait_for_message(
            room_id=self.project_room_id,
            sender=self.resolution_matrix_id,
            after_ms=int(source.get("origin_server_ts", 0)),
            predicate=is_expected_resolution_event,
            timeout_seconds=timeout_seconds,
        )
        result = {
            "matrix_event_id": matrix_event["event_id"],
            "payload": _json_object_from_body(str(matrix_event["body"])),
        }
        payload = result["payload"]
        for field in (
            "event_type",
            "case_id",
            "incident_sequence",
            "state",
            "sender_agent",
            "receiver",
        ):
            if payload.get(field) != event.get(field):
                raise AgentTeamsTransportError(
                    f"Resolution Project update conflicts on {field}"
                )
        return result

    def request_operations_review(self, request: dict[str, Any]) -> dict[str, Any]:
        started_ms = int(time.time() * 1000) - 1000
        review = {"event_type": "P2_REVIEW_START", **request}
        prompt = (
            "[GOAI OPERATIONS REVIEW]\n"
            f"{json.dumps(review, ensure_ascii=False, separators=(',', ':'))}\n"
            "Hotel Operations: reply with exactly APPROVE or REJECT."
        )
        event_id = self.matrix.send_admin(self.resolution_room_id, prompt)
        return {"matrix_event_id": event_id, "after_ms": started_ms}

    def request_resolution_operations_summary(
        self,
        event: dict[str, Any],
        *,
        source_event_id: str,
        timeout_seconds: float = 90.0,
    ) -> dict[str, Any]:
        """Publish a Resolution summary grounded in its Operations Room."""

        if event.get("sender_agent") != "RESOLUTION":
            raise AgentTeamsTransportError(
                "Operations summary must be authored by Resolution"
            )
        self._ensure_ready("resolution")
        source = next(
            (
                item
                for item in self.matrix.recent_messages(self.resolution_room_id, limit=100)
                if item.get("event_id") == source_event_id
            ),
            None,
        )
        if (
            source is None
            or source.get("sender") != "@admin:matrix-local.agentteams.io:18080"
            or "[GOAI OPERATIONS DECISION]" not in str(source.get("body", ""))
            or str(event.get("case_id")) not in str(source.get("body", ""))
        ):
            raise AgentTeamsTransportError(
                "Operations summary source event is not authorized for this Case"
            )
        body = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        return self._send_worker_display(
            worker_name="resolution",
            sender_matrix_id=self.resolution_matrix_id,
            body=body,
        )

    def poll_operations_decision(self, after_ms: int) -> dict[str, Any] | None:
        candidates = sorted(
            self.matrix.recent_messages(self.resolution_room_id, limit=50),
            key=lambda item: int(item.get("origin_server_ts", 0)),
        )
        for event in candidates:
            if event.get("sender") != "@admin:matrix-local.agentteams.io:18080":
                continue
            if int(event.get("origin_server_ts", 0)) < after_ms:
                continue
            decision = str(event.get("body", "")).strip().upper()
            if decision in {"APPROVE", "REJECT"}:
                return {
                    "decision": decision,
                    "message_event_id": str(event["event_id"]),
                    "operator_id": "hotel-operations-demo",
                }
        return None

    def publish_project_event(self, event: dict[str, Any]) -> str:
        if event.get("sender_agent") != "MANAGER":
            raise AgentTeamsTransportError(
                "Frontline and Resolution must publish their own Project Room events"
            )
        target_by_receiver = {
            "FRONTLINE": self.frontline_matrix_id,
            "RESOLUTION": self.resolution_matrix_id,
        }
        target = target_by_receiver.get(str(event.get("receiver")))
        if target is None:
            raise AgentTeamsTransportError(
                "Manager Project event must target Frontline or Resolution"
            )
        return self.matrix.send_manager_display(
            self.project_room_id,
            json.dumps(event, ensure_ascii=False, separators=(",", ":")),
            target_user=target,
        )

    def bind_resolution_task(
        self,
        *,
        case_id: str,
        incident_sequence: int,
        source_event_id: str,
        occurred_at: str,
    ) -> str:
        """Publish a control-only task binding without repeating business payload."""

        self._ensure_ready("resolution")
        event = {
            "event_type": "TASK_BINDING",
            "business_event_id": f"{case_id}-RESOLUTION-BINDING-{incident_sequence}",
            "case_id": case_id,
            "incident_sequence": incident_sequence,
            "state": "RESOLVING",
            "sender_agent": "MANAGER",
            "receiver": "RESOLUTION",
            "conclusion": "Resolution is assigned to investigate the referenced Case event.",
            "next_action": (
                "Read the referenced event, use the assigned Skill and permitted Tools to "
                "investigate and evaluate risk, then publish exactly one RESOLUTION_PROPOSED "
                "JSON object matching the Skill display contract; do not publish an "
                "acknowledgement, reasoning, Markdown, or RESOLUTION_ACCEPTED event."
            ),
            "evidence_ref": f"matrix-event://{source_event_id}",
            "occurred_at": occurred_at,
        }
        return self.matrix.send_manager(
            self.project_room_id,
            json.dumps(event, ensure_ascii=False, separators=(",", ":")),
            mentions=[self.resolution_matrix_id],
        )

    def route_operations(self, decision: dict[str, Any]) -> str:
        prompt = (
            "[GOAI OPERATIONS DECISION]\n"
            f"{json.dumps(decision, ensure_ascii=False, separators=(',', ':'))}"
        )
        return self.matrix.send_admin(self.resolution_room_id, prompt)

    def route_verification(self, package: dict[str, Any]) -> str:
        self._ensure_ready("verification")
        prompt = (
            f"{self.verification_matrix_id} [GOAI VERIFICATION ROUTE]\n"
            f"{json.dumps(package, ensure_ascii=False, separators=(',', ':'))}"
        )
        return self.matrix.send_admin(self.verification_room_id, prompt)

    def request_verification(self, package: dict[str, Any]) -> AgentReply:
        """Route a frozen Package and consume the assigned Verification reply."""

        self._ensure_ready("verification")
        started_ms = int(time.time() * 1000) - 1000
        result_shape = {
            "event_type": "VERIFICATION_RESULT",
            "business_event_id": "<new business event id>",
            "case_id": package["case_id"],
            "incident_sequence": package["resolution_plan"]["incident_sequence"],
            "sender_agent": "VERIFICATION",
            "verification_result_id": "<new verification result id>",
            "verification_status": "<PASSED or FAILED>",
            "evidence_ref": "verification-result://<same verification result id>",
            "differences": [],
            "occurred_at": "<RFC3339 timestamp with timezone>",
        }
        prompt = (
            f"{self.verification_matrix_id} [GOAI INDEPENDENT VERIFICATION]\n"
            "Use only the frozen Package below and your read-only Verification Tool. "
            "Do not read or request the Project Room transcript. Reply in this dedicated "
            "Room with exactly one JSON object matching result_shape; no Markdown or reasoning. "
            "For FAILED, differences must contain the exact failed checks.\n"
            f"frozen_package={json.dumps(package, ensure_ascii=False, separators=(',', ':'))}\n"
            f"result_shape={json.dumps(result_shape, ensure_ascii=False, separators=(',', ':'))}"
        )
        self.matrix.send_admin(self.verification_room_id, prompt)

        def is_verification_result(body: str) -> bool:
            try:
                payload = _json_object_from_body(body)
            except BridgeError:
                return False
            return (
                payload.get("event_type") == "VERIFICATION_RESULT"
                and payload.get("case_id") == package.get("case_id")
            )

        event = self.matrix.wait_for_message(
            room_id=self.verification_room_id,
            sender=self.verification_matrix_id,
            after_ms=started_ms,
            predicate=is_verification_result,
            timeout_seconds=90,
        )
        return AgentReply(
            matrix_event_id=str(event["event_id"]),
            payload=_json_object_from_body(str(event["body"])),
            sender=str(event["sender"]),
        )

    def wait_project_event(
        self,
        *,
        sender_matrix_id: str,
        after_ms: int,
        case_id: str | None = None,
        timeout_seconds: float = 90.0,
    ) -> dict[str, Any]:
        event = self.matrix.wait_for_message(
            room_id=self.project_room_id,
            sender=sender_matrix_id,
            after_ms=after_ms,
            predicate=lambda body: _is_project_event(body, case_id=case_id),
            timeout_seconds=timeout_seconds,
        )
        return {
            "matrix_event_id": event["event_id"],
            "payload": _json_object_from_body(str(event["body"])),
        }


def _is_project_event(body: str, case_id: str | None = None) -> bool:
    try:
        payload = _json_object_from_body(body)
    except BridgeError:
        return False
    if not isinstance(payload.get("event_type"), str) or "case_id" not in payload:
        return False
    return case_id is None or payload.get("case_id") == case_id
