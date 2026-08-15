from __future__ import annotations

import json
import socket
import sys
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from serve_http import create_server  # noqa: E402


FIXTURE = SERVICE_DIR / "fixtures" / "golden-case.json"


class HttpApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_server("127.0.0.1", 0, FIXTURE)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self) -> None:
        status, response = self.post_json({}, "/reset")
        self.assertEqual(status, 200)
        self.assertEqual(response, {"status": "reset"})

    def get_json(self, path: str) -> tuple[int, dict]:
        with urlopen(f"{self.base_url}{path}", timeout=2) as response:
            return response.status, json.loads(response.read())

    def post_json(
        self,
        payload: object,
        path: str = "/resolve-order-reference",
    ) -> tuple[int, dict]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def prepare_rebooking(self, price_difference_cny: int = 180) -> tuple[dict, dict]:
        status, match = self.post_json(
            {
                "customer_id": "C001",
                "clues": {
                    "hotel_name": "上海虹桥海湾花园酒店",
                    "check_in_date": "2026-08-15",
                },
            }
        )
        self.assertEqual(status, 200)
        status, context = self.post_json(
            {"customer_id": "C001", "order_ref": match["order_ref"]},
            "/get-authorized-order",
        )
        self.assertEqual(status, 200)
        order = context["order"]
        alternative = context["eligible_rebooking_options"][0]
        exception = context["supplier_exceptions"][0]
        plan = {
            "resolution_plan_id": "PLAN-HTTP-001",
            "order_ref": match["order_ref"],
            "order_id": order["order_id"],
            "action": "REBOOK",
            "diagnosis": exception["summary"],
            "evidence_ids": [exception["exception_id"]],
            "replacement_hotel_id": alternative["hotel_id"],
            "replacement_hotel_name": alternative["hotel_name"],
            "check_in_date": alternative["check_in_date"],
            "check_out_date": alternative["check_out_date"],
            "price_difference_cny": price_difference_cny,
            "previous_confirmation_number": order["confirmation_number"],
            "expected_current_status": "CONFIRMED",
            "expected_target_status": "REBOOKED",
        }
        status, risk = self.post_json(
            {
                "case_id": "CASE-HTTP-001",
                "customer_id": "C001",
                "order_ref": match["order_ref"],
                "resolution_plan": plan,
            },
            "/evaluate-rebooking",
        )
        self.assertEqual(status, 200)
        return plan, risk

    def confirm_plan(self, plan: dict, risk: dict) -> dict:
        status, confirmation = self.post_json(
            {
                "case_id": "CASE-HTTP-001",
                "resolution_plan_id": plan["resolution_plan_id"],
                "risk_decision_id": risk["risk_decision_id"],
                "message_event_id": "MSG-HTTP-003",
            },
            "/record-customer-confirmation",
        )
        self.assertEqual(status, 200)
        return confirmation

    def raw_request(self, request: bytes) -> tuple[int, dict]:
        with socket.create_connection(("127.0.0.1", self.server.server_port), timeout=2) as sock:
            sock.sendall(request)
            response_parts = []
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                response_parts.append(data)
        response = b"".join(response_parts)
        headers, body = response.split(b"\r\n\r\n", 1)
        status = int(headers.split(b"\r\n", 1)[0].split()[1])
        return status, json.loads(body)

    def test_health(self):
        status, response = self.get_json("/health")
        self.assertEqual(status, 200)
        self.assertEqual(response, {"status": "ok"})

    def test_multiple_returns_only_count_and_missing_fields(self):
        status, response = self.post_json({"customer_id": "C001", "clues": {}})
        self.assertEqual(status, 200)
        self.assertEqual(
            response,
            {
                "status": "MULTIPLE",
                "candidate_count": 2,
                "missing_fields": ["hotel_name", "check_in_date"],
                "candidates": [],
            },
        )
        serialized = json.dumps(response)
        self.assertNotIn("H-C001-001", serialized)
        self.assertNotIn("H-C002-001", serialized)

    def test_unique_returns_opaque_reference(self):
        status, response = self.post_json(
            {
                "customer_id": "C001",
                "clues": {
                    "hotel_name": "上海虹桥海湾花园酒店",
                    "check_in_date": "2026-08-15",
                },
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(response["status"], "UNIQUE")
        self.assertTrue(response["ownership_verified"])
        self.assertTrue(response["order_ref"].startswith("oref_"))
        serialized = json.dumps(response)
        self.assertNotIn("H-C001-001", serialized)
        self.assertNotIn("H-C002-001", serialized)

    def test_authorized_order_rejects_cross_customer_access(self):
        status, match = self.post_json(
            {
                "customer_id": "C001",
                "clues": {
                    "hotel_name": "上海虹桥海湾花园酒店",
                    "check_in_date": "2026-08-15",
                },
            }
        )
        self.assertEqual(status, 200)
        status, response = self.post_json(
            {"customer_id": "C002", "order_ref": match["order_ref"]},
            "/get-authorized-order",
        )
        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "ORDER_ACCESS_DENIED")

    def test_full_http_write_read_and_verify_path(self):
        plan, risk = self.prepare_rebooking()
        self.assertEqual(risk["decision"], "REQUIRE_CUSTOMER_CONFIRMATION")
        confirmation = self.confirm_plan(plan, risk)
        self.assertTrue(confirmation["confirmed"])

        execution_request = {
            "case_id": "CASE-HTTP-001",
            "resolution_plan_id": plan["resolution_plan_id"],
            "risk_decision_id": risk["risk_decision_id"],
            "idempotency_key": "CASE-HTTP-001-REBOOK",
        }
        status, execution = self.post_json(execution_request, "/execute-rebooking")
        self.assertEqual(status, 200)
        self.assertEqual(execution["reported_status"], "SUCCESS")
        self.assertFalse(execution["idempotent_replay"])

        status, replay = self.post_json(execution_request, "/execute-rebooking")
        self.assertEqual(status, 200)
        self.assertTrue(replay["idempotent_replay"])

        status, order = self.post_json(
            {"customer_id": "C001", "order_ref": plan["order_ref"]},
            "/get-order-state",
        )
        self.assertEqual(status, 200)
        self.assertEqual(order["status"], "REBOOKED")
        self.assertEqual(order["hotel_id"], "HTL-SHA-HARBOR")

        status, verification = self.post_json(
            {
                "customer_id": "C001",
                "resolution_plan_id": plan["resolution_plan_id"],
                "idempotency_key": "CASE-HTTP-001-REBOOK",
            },
            "/verify-rebooking",
        )
        self.assertEqual(status, 200)
        self.assertEqual(verification["verification_status"], "PASSED")

    def test_execute_without_confirmation_is_blocked(self):
        plan, risk = self.prepare_rebooking()
        status, response = self.post_json(
            {
                "case_id": "CASE-HTTP-001",
                "resolution_plan_id": plan["resolution_plan_id"],
                "risk_decision_id": risk["risk_decision_id"],
                "idempotency_key": "NO-CONFIRMATION",
            },
            "/execute-rebooking",
        )
        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "CUSTOMER_CONFIRMATION_REQUIRED")

    def test_validate_execution_authorization_with_confirmation(self):
        plan, risk = self.prepare_rebooking()
        self.confirm_plan(plan, risk)
        status, response = self.post_json(
            {
                "case_id": "CASE-HTTP-001",
                "resolution_plan_id": plan["resolution_plan_id"],
                "risk_decision_id": risk["risk_decision_id"],
            },
            "/validate-execution-authorization",
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            response,
            {
                "authorized": True,
                "risk_decision_id": risk["risk_decision_id"],
            },
        )

    def test_validate_execution_authorization_without_confirmation_is_blocked(self):
        plan, risk = self.prepare_rebooking()
        status, response = self.post_json(
            {
                "case_id": "CASE-HTTP-001",
                "resolution_plan_id": plan["resolution_plan_id"],
                "risk_decision_id": risk["risk_decision_id"],
            },
            "/validate-execution-authorization",
        )
        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "CUSTOMER_CONFIRMATION_REQUIRED")

    def test_800_cny_risk_requires_internal_approval(self):
        plan, risk = self.prepare_rebooking(800)
        self.assertEqual(risk["decision"], "REQUIRE_INTERNAL_APPROVAL")
        status, response = self.post_json(
            {
                "case_id": "CASE-HTTP-001",
                "resolution_plan_id": plan["resolution_plan_id"],
                "risk_decision_id": risk["risk_decision_id"],
                "idempotency_key": "NEEDS-APPROVAL",
            },
            "/execute-rebooking",
        )
        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "HIGH_RISK_EXECUTION_NOT_ENABLED")

    def test_approved_high_risk_decision_is_authorized_but_execution_stays_disabled(self):
        plan, risk = self.prepare_rebooking(800)
        status, decision = self.post_json(
            {
                "case_id": "CASE-HTTP-001",
                "resolution_plan_id": plan["resolution_plan_id"],
                "risk_decision_id": risk["risk_decision_id"],
                "decision": "APPROVE",
                "message_event_id": "MSG-OPS-APPROVE",
                "operator_id": "hotel-operations-001",
            },
            "/record-internal-decision",
        )
        self.assertEqual(status, 200)
        self.assertEqual(decision["decision"], "APPROVE")
        self.assertTrue(decision["recorded_at"])
        status, authorization = self.post_json(
            {
                "case_id": "CASE-HTTP-001",
                "resolution_plan_id": plan["resolution_plan_id"],
                "risk_decision_id": risk["risk_decision_id"],
            },
            "/validate-execution-authorization",
        )
        self.assertEqual(status, 200)
        self.assertEqual(authorization["authorized"], True)
        self.assertEqual(authorization["execution_enabled"], False)
        status, response = self.post_json(
            {
                "case_id": "CASE-HTTP-001",
                "resolution_plan_id": plan["resolution_plan_id"],
                "risk_decision_id": risk["risk_decision_id"],
                "idempotency_key": "HIGH-RISK-HTTP",
            },
            "/execute-rebooking",
        )
        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "HIGH_RISK_EXECUTION_NOT_ENABLED")
        status, order = self.post_json(
            {"customer_id": "C001", "order_ref": plan["order_ref"]},
            "/get-order-state",
        )
        self.assertEqual(status, 200)
        self.assertEqual(order["status"], "CONFIRMED")

    def test_rejected_internal_decision_blocks_authorization(self):
        plan, risk = self.prepare_rebooking(800)
        status, decision = self.post_json(
            {
                "case_id": "CASE-HTTP-001",
                "resolution_plan_id": plan["resolution_plan_id"],
                "risk_decision_id": risk["risk_decision_id"],
                "decision": "REJECT",
                "message_event_id": "MSG-OPS-REJECT",
                "operator_id": "hotel-operations-001",
            },
            "/record-internal-decision",
        )
        self.assertEqual(status, 200)
        self.assertEqual(decision["decision"], "REJECT")
        status, response = self.post_json(
            {
                "case_id": "CASE-HTTP-001",
                "resolution_plan_id": plan["resolution_plan_id"],
                "risk_decision_id": risk["risk_decision_id"],
            },
            "/validate-execution-authorization",
        )
        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "INTERNAL_APPROVAL_REJECTED")

    def test_idempotency_key_conflict_is_blocked(self):
        plan, risk = self.prepare_rebooking()
        self.confirm_plan(plan, risk)
        request = {
            "case_id": "CASE-HTTP-001",
            "resolution_plan_id": plan["resolution_plan_id"],
            "risk_decision_id": risk["risk_decision_id"],
            "idempotency_key": "SHARED-HTTP-KEY",
        }
        status, _ = self.post_json(request, "/execute-rebooking")
        self.assertEqual(status, 200)
        conflicting_request = dict(request, case_id="CASE-HTTP-OTHER")
        status, response = self.post_json(conflicting_request, "/execute-rebooking")
        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "IDEMPOTENCY_KEY_CONFLICT")

    def test_false_success_is_detected_through_http(self):
        status, response = self.post_json(
            {"execute_success_without_update": True},
            "/reset",
        )
        self.assertEqual(status, 200)
        self.assertEqual(response, {"status": "reset"})
        plan, risk = self.prepare_rebooking()
        self.confirm_plan(plan, risk)
        status, execution = self.post_json(
            {
                "case_id": "CASE-HTTP-001",
                "resolution_plan_id": plan["resolution_plan_id"],
                "risk_decision_id": risk["risk_decision_id"],
                "idempotency_key": "FALSE-SUCCESS-HTTP",
            },
            "/execute-rebooking",
        )
        self.assertEqual(status, 200)
        self.assertEqual(execution["reported_status"], "SUCCESS")
        status, verification = self.post_json(
            {
                "customer_id": "C001",
                "resolution_plan_id": plan["resolution_plan_id"],
                "idempotency_key": "FALSE-SUCCESS-HTTP",
            },
            "/verify-rebooking",
        )
        self.assertEqual(status, 200)
        self.assertEqual(verification["verification_status"], "FAILED")
        self.assertIn("order_status_matches", verification["differences"])

    def test_missing_customer_id_returns_structured_error(self):
        status, response = self.post_json({"clues": {}})
        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "MISSING_CUSTOMER_ID")
        self.assertIn("message", response["error"])

    def test_invalid_json_returns_structured_error(self):
        request = Request(
            f"{self.base_url}/resolve-order-reference",
            data=b"{not-json",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=2)
        response = json.loads(caught.exception.read())
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(response["error"]["code"], "INVALID_JSON")

    def test_chunked_request_returns_multiple(self):
        body = json.dumps({"customer_id": "C001", "clues": {}}).encode("utf-8")
        chunks = (body[:11], body[11:])
        request = (
            b"POST /resolve-order-reference HTTP/1.1\r\n"
            + f"Host: 127.0.0.1:{self.server.server_port}\r\n".encode()
            + b"Content-Type: application/json\r\n"
            + b"Transfer-Encoding: chunked\r\n"
            + b"Connection: close\r\n\r\n"
            + b"".join(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n" for chunk in chunks)
            + b"0\r\n\r\n"
        )
        status, response = self.raw_request(request)
        self.assertEqual(status, 200)
        self.assertEqual(response["status"], "MULTIPLE")
        self.assertEqual(response["candidate_count"], 2)
        serialized = json.dumps(response)
        self.assertNotIn("H-C001-001", serialized)
        self.assertNotIn("H-C002-001", serialized)

    def test_malformed_chunk_returns_structured_error(self):
        request = (
            b"POST /resolve-order-reference HTTP/1.1\r\n"
            + f"Host: 127.0.0.1:{self.server.server_port}\r\n".encode()
            + b"Transfer-Encoding: chunked\r\n"
            + b"Connection: close\r\n\r\n"
            + b"NOT-HEX\r\n{}\r\n0\r\n\r\n"
        )
        status, response = self.raw_request(request)
        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "INVALID_CHUNKED_BODY")

    def test_unsupported_transfer_encoding_returns_structured_error(self):
        request = (
            b"POST /resolve-order-reference HTTP/1.1\r\n"
            + f"Host: 127.0.0.1:{self.server.server_port}\r\n".encode()
            + b"Transfer-Encoding: gzip\r\n"
            + b"Connection: close\r\n\r\n"
        )
        status, response = self.raw_request(request)
        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "UNSUPPORTED_TRANSFER_ENCODING")

    def test_content_length_above_limit_returns_413(self):
        request = (
            b"POST /resolve-order-reference HTTP/1.1\r\n"
            + f"Host: 127.0.0.1:{self.server.server_port}\r\n".encode()
            + b"Content-Length: 1048577\r\n"
            + b"Connection: close\r\n\r\n"
        )
        status, response = self.raw_request(request)
        self.assertEqual(status, 413)
        self.assertEqual(response["error"]["code"], "REQUEST_BODY_TOO_LARGE")


if __name__ == "__main__":
    unittest.main()
