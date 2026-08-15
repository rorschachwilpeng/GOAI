#!/usr/bin/env python3
"""Run the Customer Chat to AgentTeams Frontline bridge.

This process is a rehearsal adapter, not the formal T013 runner.  It never
creates a Project/Room or writes the five-marker Run Manifest.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from agentteams_transport import DockerAgentTeamsTransport, MatrixAdminClient
from linked_journey_bridge import EvidenceCollector, LinkedJourneyBridge, RoomMapping


DEFAULT_PROJECT_META = (
    Path(__file__).parents[1]
    / "runs"
    / "2026-08-14-project-room-migration"
    / "project-meta.json"
)


class HttpConversationProjection:
    def __init__(self, base_url: str, internal_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.internal_token = internal_token

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        internal: bool = False,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if internal:
            headers["Authorization"] = f"Bearer {self.internal_token}"
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=5) as response:
                result = json.loads(response.read())
        except HTTPError as error:
            raise RuntimeError(f"Conversation API rejected {method} {path}") from error
        if not isinstance(result, dict):
            raise RuntimeError("Conversation API returned an invalid response")
        return result

    def create(self, conversation_id: str, case_id: str, customer_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/internal/conversations",
            {
                "conversation_id": conversation_id,
                "case_id": case_id,
                "customer_id": customer_id,
            },
            internal=True,
        )

    def get(self, conversation_id: str, customer_id: str) -> dict[str, Any]:
        query = urlencode({"customer_id": customer_id})
        return self._request("GET", f"/conversations/{conversation_id}?{query}")

    def append_frontline_projection(
        self,
        conversation_id: str,
        customer_id: str,
        message_type: str,
        body: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/internal/conversations/{conversation_id}/frontline-messages",
            {
                "customer_id": customer_id,
                "message_type": message_type,
                "body": body,
            },
            internal=True,
        )


class CustomerBridgeRunner:
    def __init__(
        self,
        *,
        projection: HttpConversationProjection,
        bridge: LinkedJourneyBridge,
        customer_id: str,
        conversation_id: str,
    ) -> None:
        self.projection = projection
        self.bridge = bridge
        self.customer_id = customer_id
        self.conversation_id = conversation_id
        self.processed_message_ids: set[str] = set()

    def process_once(self) -> int:
        conversation = self.projection.get(self.conversation_id, self.customer_id)
        pending = [
            message
            for message in conversation.get("messages", [])
            if message.get("sender") == "CUSTOMER"
            and message.get("message_id") not in self.processed_message_ids
        ]
        for message in pending:
            self.bridge.forward_customer_message(message)
            self.processed_message_ids.add(str(message["message_id"]))
        return len(pending)

    def run_forever(self, interval_seconds: float = 1.0) -> None:
        while True:
            self.process_once()
            time.sleep(interval_seconds)


def build_runner(args: argparse.Namespace) -> tuple[CustomerBridgeRunner, HttpConversationProjection]:
    internal_token = os.environ.get("GOAI_INTERNAL_TOKEN")
    if not internal_token:
        raise SystemExit("GOAI_INTERNAL_TOKEN must be injected into the bridge process")
    mapping = RoomMapping.from_project_meta(args.project_meta, args.project_id)
    projection = HttpConversationProjection(args.base_url, internal_token)
    matrix = MatrixAdminClient(manager_container=args.manager_container)
    transport = DockerAgentTeamsTransport.from_runtime(
        matrix=matrix,
        project_room_id=mapping.project_room_id,
        manager_container=args.manager_container,
    )
    bridge = LinkedJourneyBridge(
        conversations=projection,  # HTTP adapter implements the same projection method.
        transport=transport,
        room_mapping=mapping,
        customer_id=args.customer_id,
        case_id=args.case_id,
        conversation_id=args.conversation_id,
        evidence=EvidenceCollector(),
    )
    return (
        CustomerBridgeRunner(
            projection=projection,
            bridge=bridge,
            customer_id=args.customer_id,
            conversation_id=args.conversation_id,
        ),
        projection,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:19090")
    parser.add_argument("--manager-container", default="agentteams-manager")
    parser.add_argument("--project-meta", type=Path, default=DEFAULT_PROJECT_META)
    parser.add_argument("--project-id", default="proj-goai-case-golden-001")
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--conversation-id", required=True)
    parser.add_argument("--init-conversation", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    runner, projection = build_runner(args)
    if args.init_conversation:
        projection.create(args.conversation_id, args.case_id, args.customer_id)
    if args.once:
        processed = runner.process_once()
        print(json.dumps({"processed_customer_messages": processed}))
        return
    try:
        runner.run_forever()
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
