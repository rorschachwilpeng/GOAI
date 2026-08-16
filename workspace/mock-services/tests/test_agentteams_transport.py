from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentteams_transport import (  # noqa: E402
    AgentTeamsTransportError,
    DockerAgentTeamsTransport,
    MATRIX_BRIDGE_SCRIPT,
    MatrixAdminClient,
    WORKER_MATRIX_SEND_SCRIPT,
    _json_object_from_body,
)
from linked_journey_bridge import BridgeError  # noqa: E402


class AgentTeamsTransportTest(unittest.TestCase):
    def test_matrix_mention_prefix_is_removed_before_json_validation(self):
        payload = _json_object_from_body(
            r'$@resolution:example.test\n{"event_type":"ORDER_LINKED","case_id":"CASE-SMOKE-1"}'
        )
        self.assertEqual(payload["event_type"], "ORDER_LINKED")
        self.assertEqual(payload["case_id"], "CASE-SMOKE-1")

    def test_matrix_send_keeps_secret_values_out_of_host_command_and_payload(self):
        calls: list[dict] = []

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append({"command": command, **kwargs})
            return subprocess.CompletedProcess(command, 0, '{"event_id":"$matrix-smoke"}', "")

        client = MatrixAdminClient(command_runner=runner)
        event_id = client.send_admin("!smoke:example.test", "synthetic bridge ping")

        self.assertEqual(event_id, "$matrix-smoke")
        serialized = json.dumps(calls, default=str).lower()
        self.assertNotIn("sk-test-secret", serialized)
        self.assertNotIn("matrix-secret-value", serialized)
        self.assertIn("agentteams_admin_password", serialized)

    def test_matrix_login_payload_uses_jq_arguments_for_credentials(self):
        self.assertIn('--arg user "$login_user"', MATRIX_BRIDGE_SCRIPT)
        self.assertIn('--arg password "$login_password"', MATRIX_BRIDGE_SCRIPT)
        self.assertIn('-d "$login_payload"', MATRIX_BRIDGE_SCRIPT)
        self.assertNotIn('password:"${login_password}"', MATRIX_BRIDGE_SCRIPT)

    def test_worker_display_token_stays_inside_worker_container(self):
        self.assertIn("channels.matrix.accessToken", WORKER_MATRIX_SEND_SCRIPT)
        self.assertIn("Authorization: Bearer ${token}", WORKER_MATRIX_SEND_SCRIPT)
        self.assertNotIn("echo $token", WORKER_MATRIX_SEND_SCRIPT)

    def test_manager_mention_prefix_triggers_group_worker(self):
        calls: list[dict] = []
        body = '{"event_type":"TASK_BINDING"}'
        message_body = f"@resolution:example.test\n{body}"

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append({"command": command, **kwargs})
            if "copaw" in command:
                return subprocess.CompletedProcess(command, 0, "", "")
            response = {
                "events": [
                    {
                        "event_id": "$matrix-smoke",
                        "sender": "@manager:matrix-local.agentteams.io:18080",
                        "origin_server_ts": 9999999999999,
                        "body": message_body,
                    }
                ]
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(response), "")

        client = MatrixAdminClient(command_runner=runner)
        event_id = client.send_manager(
            "!smoke:example.test",
            body,
            mentions=["@resolution:example.test"],
        )

        self.assertEqual(event_id, "$matrix-smoke")
        copaw_command = next(call["command"] for call in calls if "copaw" in call["command"])
        self.assertIn("--target-user", copaw_command)
        self.assertIn("@resolution:example.test", copaw_command)
        self.assertEqual(copaw_command[-1], message_body)

    def test_manager_display_event_uses_matrix_without_peer_mention(self):
        calls: list[dict] = []
        body = '{"event_type":"VERIFICATION_SUMMARY"}'

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append({"command": command, **kwargs})
            if "copaw" in command:
                return subprocess.CompletedProcess(command, 0, "{}", "")
            response = {
                "events": [
                    {
                        "event_id": "$display",
                        "sender": "@manager:matrix-local.agentteams.io:18080",
                        "origin_server_ts": 9999999999999,
                        "body": body,
                    }
                ]
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(response), "")

        client = MatrixAdminClient(command_runner=runner)
        event_id = client.send_manager_display(
            "!project:example.test",
            body,
            target_user="@frontline:example.test",
        )

        self.assertEqual(event_id, "$display")
        copaw_command = next(call["command"] for call in calls if "copaw" in call["command"])
        self.assertIn("@frontline:example.test", copaw_command)
        self.assertEqual(copaw_command[-1], body)
        self.assertNotIn("@frontline", body)

    def test_runtime_mapping_accepts_running_or_idle_workers_after_wake(self):
        calls: list[list[str]] = []
        workers = {
            "workers": [
                {
                    "name": "frontline",
                    "phase": "Running",
                    "roomID": "!frontline:example.test",
                    "matrixUserID": "@frontline:example.test",
                },
                {
                    "name": "resolution",
                    "phase": "Sleeping",
                    "roomID": "!resolution:example.test",
                    "matrixUserID": "@resolution:example.test",
                },
                {
                    "name": "verification",
                    "phase": "Running",
                    "roomID": "!verification:example.test",
                    "matrixUserID": "@verification:example.test",
                },
            ]
        }

        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            stdout = json.dumps(workers) if "agt" in command else ""
            return subprocess.CompletedProcess(command, 0, stdout, "")

        transport = DockerAgentTeamsTransport.from_runtime(
            matrix=MatrixAdminClient(command_runner=runner),
            project_room_id="!project:example.test",
            command_runner=runner,
        )

        self.assertEqual(transport.frontline_room_id, "!frontline:example.test")
        self.assertEqual(transport.project_room_id, "!project:example.test")
        ensure_calls = [command for command in calls if "ensure-ready" in command]
        self.assertEqual(len(ensure_calls), 3)

        transport._ensure_ready("frontline")
        self.assertEqual(len([command for command in calls if "ensure-ready" in command]), 4)

    def test_customer_safe_json_parser_rejects_surrounding_reasoning(self):
        payload = _json_object_from_body(
            '```json\n{"event_type":"CUSTOMER_SAFE_REPLY"}\n```'
        )
        self.assertEqual(payload["event_type"], "CUSTOMER_SAFE_REPLY")

        with self.assertRaisesRegex(BridgeError, "one JSON object"):
            _json_object_from_body(
                '先说明内部步骤\n{"event_type":"CUSTOMER_SAFE_REPLY"}'
            )

    def test_verification_request_waits_for_assigned_worker_reply(self):
        calls: list[dict] = []
        result = {
            "event_type": "VERIFICATION_RESULT",
            "business_event_id": "BUS-SMOKE-VERIFY",
            "case_id": "CASE-SMOKE-VERIFY-001",
            "incident_sequence": 1,
            "sender_agent": "VERIFICATION",
            "verification_result_id": "VR-SMOKE-VERIFY",
            "verification_status": "PASSED",
            "evidence_ref": "verification-result://VR-SMOKE-VERIFY",
            "differences": [],
            "occurred_at": "2026-08-15T12:00:00+08:00",
        }

        class FakeMatrix:
            def send_admin(self, room_id: str, body: str) -> str:
                calls.append({"method": "send", "room_id": room_id, "body": body})
                return "$smoke-verification-request"

            def wait_for_message(self, **kwargs: object) -> dict:
                calls.append({"method": "wait", **kwargs})
                self_test.assertEqual(kwargs["room_id"], "!verification:example.test")
                self_test.assertEqual(kwargs["sender"], "@verification:example.test")
                self_test.assertTrue(kwargs["predicate"](json.dumps(result)))
                return {
                    "event_id": "$smoke-verification-reply",
                    "sender": "@verification:example.test",
                    "body": json.dumps(result),
                }

        self_test = self
        transport = DockerAgentTeamsTransport(
            matrix=FakeMatrix(),
            frontline_room_id="!frontline:example.test",
            resolution_room_id="!resolution:example.test",
            verification_room_id="!verification:example.test",
            project_room_id="!project:example.test",
            verification_matrix_id="@verification:example.test",
        )

        reply = transport.request_verification(
            {
                "case_id": "CASE-SMOKE-VERIFY-001",
                "resolution_plan": {"incident_sequence": 1},
            }
        )

        self.assertEqual(reply.matrix_event_id, "$smoke-verification-reply")
        self.assertEqual(reply.sender, "@verification:example.test")
        self.assertEqual(reply.payload["verification_status"], "PASSED")
        self.assertEqual(calls[0]["room_id"], "!verification:example.test")
        self.assertNotIn("!project:example.test", json.dumps(calls, default=str))

    def test_operations_review_is_human_notice_without_worker_mention(self):
        sent: list[dict] = []

        class FakeMatrix:
            def send_admin(self, room_id: str, body: str) -> str:
                sent.append({"room_id": room_id, "body": body})
                return "$operations-review"

        transport = DockerAgentTeamsTransport(
            matrix=FakeMatrix(),
            frontline_room_id="!frontline:example.test",
            resolution_room_id="!resolution:example.test",
            verification_room_id="!verification:example.test",
            project_room_id="!project:example.test",
            resolution_matrix_id="@resolution:example.test",
        )

        result = transport.request_operations_review(
            {
                "case_id": "CASE-OPS-1",
                "incident_sequence": 2,
                "price_difference_cny": 800,
                "decision_required": "APPROVE | REJECT",
            }
        )

        self.assertEqual(result["matrix_event_id"], "$operations-review")
        self.assertEqual(sent[0]["room_id"], "!resolution:example.test")
        self.assertIn('"event_type":"P2_REVIEW_START"', sent[0]["body"])
        self.assertNotIn("@resolution:example.test", sent[0]["body"])

    def test_operations_decision_record_does_not_wake_resolution(self):
        sent: list[str] = []

        class FakeMatrix:
            def send_admin(self, room_id: str, body: str) -> str:
                sent.append(body)
                return "$operations-decision"

        transport = DockerAgentTeamsTransport(
            matrix=FakeMatrix(),
            frontline_room_id="!frontline:example.test",
            resolution_room_id="!resolution:example.test",
            verification_room_id="!verification:example.test",
            project_room_id="!project:example.test",
            resolution_matrix_id="@resolution:example.test",
        )

        event_id = transport.route_operations(
            {"case_id": "CASE-OPS-1", "decision": "APPROVE"}
        )

        self.assertEqual(event_id, "$operations-decision")
        self.assertIn("[GOAI OPERATIONS DECISION]", sent[0])
        self.assertNotIn("@resolution:example.test", sent[0])

    def test_resolution_project_update_consumes_direct_project_reply(self):
        expected = {
            "event_type": "RESOLUTION_PROPOSED",
            "case_id": "CASE-SMOKE-DIRECT-001",
            "incident_sequence": 1,
            "state": "AWAITING_CUSTOMER_CONFIRMATION",
            "sender_agent": "RESOLUTION",
            "receiver": "FRONTLINE",
        }

        class FakeMatrix:
            def recent_messages(self, room_id: str, limit: int = 50) -> list[dict]:
                self_test.assertEqual(room_id, "!project:example.test")
                return [
                    {
                        "event_id": "$frontline-source",
                        "sender": "@frontline:example.test",
                        "origin_server_ts": 1000,
                        "body": "source",
                    }
                ]

            def wait_for_message(self, **kwargs: object) -> dict:
                self_test.assertEqual(kwargs["room_id"], "!project:example.test")
                self_test.assertEqual(kwargs["sender"], "@resolution:example.test")
                self_test.assertEqual(kwargs["after_ms"], 1000)
                body = json.dumps(expected)
                self_test.assertTrue(kwargs["predicate"](body))
                return {
                    "event_id": "$resolution-reply",
                    "sender": "@resolution:example.test",
                    "origin_server_ts": 1001,
                    "body": body,
                }

        self_test = self
        transport = DockerAgentTeamsTransport(
            matrix=FakeMatrix(),
            frontline_room_id="!frontline:example.test",
            resolution_room_id="!resolution:example.test",
            verification_room_id="!verification:example.test",
            project_room_id="!project:example.test",
            frontline_matrix_id="@frontline:example.test",
            resolution_matrix_id="@resolution:example.test",
        )

        result = transport.wait_resolution_project_update(
            expected,
            source_event_id="$frontline-source",
        )

        self.assertEqual(result["matrix_event_id"], "$resolution-reply")
        self.assertEqual(result["payload"]["event_type"], "RESOLUTION_PROPOSED")

    def test_resolution_display_request_validates_source_before_routing(self):
        expected = {
            "event_type": "RESOLUTION_PROPOSED",
            "case_id": "CASE-SMOKE-DISPLAY-001",
            "sender_agent": "RESOLUTION",
        }
        prompts: list[str] = []
        sent_bodies: list[str] = []

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            prompts.append(" ".join(command))
            sent_bodies.append(json.loads(kwargs["input"])["body"])
            return subprocess.CompletedProcess(command, 0, '{"event_id":"$proposal"}', "")

        class FakeMatrix:
            def recent_messages(self, room_id: str, limit: int = 50) -> list[dict]:
                return [
                    {
                        "event_id": "$frontline-source",
                        "sender": "@frontline:example.test",
                        "origin_server_ts": 1000,
                        "body": json.dumps(
                            {
                                "event_type": "ORDER_LINKED",
                                "case_id": expected["case_id"],
                            }
                        ),
                    }
                ]

            def wait_for_message(self, **kwargs: object) -> dict:
                body = sent_bodies[-1]
                self_test.assertTrue(kwargs["predicate"](body))
                return {"event_id": "$proposal", "body": body}

        self_test = self
        transport = DockerAgentTeamsTransport(
            matrix=FakeMatrix(),
            frontline_room_id="!frontline:example.test",
            resolution_room_id="!resolution:example.test",
            verification_room_id="!verification:example.test",
            project_room_id="!project:example.test",
            frontline_matrix_id="@frontline:example.test",
            resolution_matrix_id="@resolution:example.test",
            command_runner=runner,
        )

        result = transport.request_resolution_project_update(
            expected,
            source_event_id="$frontline-source",
        )

        self.assertEqual(result["matrix_event_id"], "$proposal")
        self.assertIn("agentteams-worker-resolution", prompts[0])
        self.assertNotIn("@frontline:example.test", sent_bodies[0])

    def test_resolution_display_request_rejects_wrong_source_type(self):
        class FakeMatrix:
            def recent_messages(self, room_id: str, limit: int = 50) -> list[dict]:
                return [
                    {
                        "event_id": "$bad-source",
                        "sender": "@manager:matrix-local.agentteams.io:18080",
                        "body": json.dumps(
                            {"event_type": "ORDER_LINKED", "case_id": "CASE-1"}
                        ),
                    }
                ]

        transport = DockerAgentTeamsTransport(
            matrix=FakeMatrix(),
            frontline_room_id="!frontline:example.test",
            resolution_room_id="!resolution:example.test",
            verification_room_id="!verification:example.test",
            project_room_id="!project:example.test",
        )

        with self.assertRaisesRegex(
            AgentTeamsTransportError,
            "not authorized",
        ):
            transport.request_resolution_project_update(
                {
                    "event_type": "RESOLUTION_PROPOSED",
                    "case_id": "CASE-1",
                    "sender_agent": "RESOLUTION",
                },
                source_event_id="$bad-source",
            )

    def test_resolution_project_update_ignores_acknowledgement_event(self):
        expected = {
            "event_type": "RESOLUTION_PROPOSED",
            "case_id": "CASE-SMOKE-DIRECT-002",
            "incident_sequence": 1,
            "state": "AWAITING_CUSTOMER_CONFIRMATION",
            "sender_agent": "RESOLUTION",
            "receiver": "FRONTLINE",
        }

        class FakeMatrix:
            def recent_messages(self, room_id: str, limit: int = 50) -> list[dict]:
                return [
                    {
                        "event_id": "$frontline-source",
                        "sender": "@frontline:example.test",
                        "origin_server_ts": 1000,
                        "body": "source",
                    }
                ]

            def wait_for_message(self, **kwargs: object) -> dict:
                predicate = kwargs["predicate"]
                acknowledgement = json.dumps(
                    {
                        "event_type": "RESOLUTION_ACCEPTED",
                        "case_id": expected["case_id"],
                    }
                )
                self_test.assertFalse(predicate(acknowledgement))
                body = json.dumps(expected)
                self_test.assertTrue(predicate(body))
                return {
                    "event_id": "$resolution-proposal",
                    "sender": "@resolution:example.test",
                    "origin_server_ts": 1002,
                    "body": body,
                }

        self_test = self
        transport = DockerAgentTeamsTransport(
            matrix=FakeMatrix(),
            frontline_room_id="!frontline:example.test",
            resolution_room_id="!resolution:example.test",
            verification_room_id="!verification:example.test",
            project_room_id="!project:example.test",
            frontline_matrix_id="@frontline:example.test",
            resolution_matrix_id="@resolution:example.test",
        )

        result = transport.wait_resolution_project_update(
            expected,
            source_event_id="$frontline-source",
        )

        self.assertEqual(result["matrix_event_id"], "$resolution-proposal")


if __name__ == "__main__":
    unittest.main()
