"""Customer-safe conversation projection for the local Chat Facade.

The public browser path may only append customer messages.  Frontline output
uses :meth:`append_frontline_projection`, an internal application method, so
the browser cannot select or forge the ``FRONTLINE`` sender.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class ConversationError(ValueError):
    pass


class ConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[str, dict[str, Any]] = {}

    def create(self, conversation_id: str, case_id: str, customer_id: str) -> dict[str, Any]:
        self._require_identifier(conversation_id, "conversation_id")
        self._require_identifier(case_id, "case_id")
        self._require_identifier(customer_id, "customer_id")
        if conversation_id in self._conversations:
            raise ConversationError("Conversation already exists")
        item = {
            "conversation_id": conversation_id,
            "case_id": case_id,
            "customer_id": customer_id,
            "messages": [],
        }
        self._conversations[conversation_id] = item
        return self._customer_projection(item)

    def append_customer(self, conversation_id: str, customer_id: str, body: str) -> dict[str, str]:
        conversation = self._get_owned(conversation_id, customer_id)
        return self._append(conversation, "CUSTOMER", "TEXT", body)

    def append_frontline_projection(
        self,
        conversation_id: str,
        customer_id: str,
        message_type: str,
        body: str,
    ) -> dict[str, str]:
        """Append a customer-visible Frontline message from trusted code only."""

        conversation = self._get_owned(conversation_id, customer_id)
        if message_type not in {"TEXT", "PLAN", "STATUS", "RESULT"}:
            raise ConversationError("Invalid customer-visible message")
        return self._append(conversation, "FRONTLINE", message_type, body)

    def get(self, conversation_id: str, customer_id: str) -> dict[str, Any]:
        return self._customer_projection(self._get_owned(conversation_id, customer_id))

    def reset(self) -> None:
        self._conversations.clear()

    @staticmethod
    def _require_identifier(value: str, field: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ConversationError(f"{field} is required")

    def _get_owned(self, conversation_id: str, customer_id: str) -> dict[str, Any]:
        self._require_identifier(conversation_id, "conversation_id")
        self._require_identifier(customer_id, "customer_id")
        conversation = self._conversations.get(conversation_id)
        if not conversation or conversation["customer_id"] != customer_id:
            # Deliberately do not reveal whether the conversation exists.
            raise ConversationError("Conversation not found")
        return conversation

    @staticmethod
    def _append(
        conversation: dict[str, Any],
        sender: str,
        message_type: str,
        body: str,
    ) -> dict[str, str]:
        if not isinstance(body, str) or not body.strip():
            raise ConversationError("body is required")
        message = {
            "message_id": f"MSG-{len(conversation['messages']) + 1}",
            "conversation_id": conversation["conversation_id"],
            "case_id": conversation["case_id"],
            "sender": sender,
            "message_type": message_type,
            "body": body,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        conversation["messages"].append(message)
        return dict(message)

    @staticmethod
    def _customer_projection(conversation: dict[str, Any]) -> dict[str, Any]:
        return {
            "conversation_id": conversation["conversation_id"],
            "case_id": conversation["case_id"],
            "messages": [dict(message) for message in conversation["messages"]],
        }
