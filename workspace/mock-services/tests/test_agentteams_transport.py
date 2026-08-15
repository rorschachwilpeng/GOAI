from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentteams_transport import (  # noqa: E402
    DockerAgentTeamsTransport,
    MATRIX_BRIDGE_SCRIPT,
    MatrixAdminClient,
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

    def test_manager_mention_is_matrix_metadata_not_business_payload(self):
        calls: list[dict] = []
        body = '{"event_type":"TASK_BINDING"}'

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
                        "body": body,
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
        self.assertEqual(copaw_command[-1], body)

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


if __name__ == "__main__":
    unittest.main()
