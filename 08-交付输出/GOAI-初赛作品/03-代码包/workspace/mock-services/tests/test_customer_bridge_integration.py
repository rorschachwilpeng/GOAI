from __future__ import annotations

import json
import sys
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from linked_journey_bridge import AgentReply, EvidenceCollector, LinkedJourneyBridge, RoomMapping
from run_customer_bridge import CustomerBridgeRunner, HttpConversationProjection
from serve_http import create_server


FIXTURE = SERVICE_DIR / "fixtures" / "golden-case.json"


class FakeFrontlineTransport:
    def __init__(self) -> None:
        self.envelopes: list[dict] = []

    def request_frontline(self, envelope: dict) -> AgentReply:
        self.envelopes.append(envelope)
        return AgentReply(
            "$matrix-frontline-integration-smoke",
            {
                "event_type": "CUSTOMER_SAFE_REPLY",
                "case_id": "CASE-SMOKE-BRIDGE-001",
                "conversation_id": "conversation-smoke-bridge-001",
                "message_type": "STATUS",
                "body": "已收到您的测试请求，正在核对。",
            },
        )

    def publish_project_event(self, event: dict) -> str:
        raise AssertionError(f"unexpected project event: {event}")

    def route_operations(self, decision: dict) -> str:
        raise AssertionError(f"unexpected operations route: {decision}")

    def route_verification(self, package: dict) -> str:
        raise AssertionError(f"unexpected verification route: {package}")


class CustomerBridgeIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_server(
            "127.0.0.1",
            0,
            FIXTURE,
            internal_token="integration-smoke-token",
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self) -> None:
        self.projection = HttpConversationProjection(
            self.base_url,
            "integration-smoke-token",
        )
        self.projection.create(
            "conversation-smoke-bridge-001",
            "CASE-SMOKE-BRIDGE-001",
            "C001",
        )

    def tearDown(self) -> None:
        request = Request(
            f"{self.base_url}/reset",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2):
            pass

    def test_customer_http_message_reaches_frontline_and_safe_reply_returns(self):
        payload = {
            "sender": "CUSTOMER",
            "customer_id": "C001",
            "body": "这是一条合成联动测试消息。",
        }
        request = Request(
            f"{self.base_url}/conversations/conversation-smoke-bridge-001/messages",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 200)

        transport = FakeFrontlineTransport()
        bridge = LinkedJourneyBridge(
            conversations=self.projection,
            transport=transport,
            room_mapping=RoomMapping(
                "proj-goai-case-golden-001",
                "!smoke-project:example.test",
                ("frontline", "resolution"),
            ),
            customer_id="C001",
            case_id="CASE-SMOKE-BRIDGE-001",
            conversation_id="conversation-smoke-bridge-001",
            evidence=EvidenceCollector(),
        )
        runner = CustomerBridgeRunner(
            projection=self.projection,
            bridge=bridge,
            customer_id="C001",
            conversation_id="conversation-smoke-bridge-001",
        )

        self.assertEqual(runner.process_once(), 1)
        conversation = self.projection.get("conversation-smoke-bridge-001", "C001")

        self.assertEqual(
            [message["sender"] for message in conversation["messages"]],
            ["CUSTOMER", "FRONTLINE"],
        )
        self.assertEqual(len(transport.envelopes), 1)
        serialized = json.dumps(conversation, ensure_ascii=False).lower()
        self.assertNotIn("mcp", serialized)
        self.assertNotIn("order_ref", serialized)
        self.assertNotIn("risk_decision", serialized)


if __name__ == "__main__":
    unittest.main()
