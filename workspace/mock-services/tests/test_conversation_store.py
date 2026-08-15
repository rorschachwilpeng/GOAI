from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conversation_store import ConversationError, ConversationStore


class ConversationStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = ConversationStore()
        self.store.create("conv-1", "CASE-1", "C001")

    def test_customer_projection_whitelists_messages_and_preserves_case(self):
        self.store.append_customer("conv-1", "C001", "请帮我处理")
        self.store.append_frontline_projection(
            "conv-1",
            "C001",
            "STATUS",
            "正在处理",
        )

        result = self.store.get("conv-1", "C001")

        self.assertEqual(result["case_id"], "CASE-1")
        self.assertEqual(
            [item["sender"] for item in result["messages"]],
            ["CUSTOMER", "FRONTLINE"],
        )
        self.assertEqual(
            set(result),
            {"conversation_id", "case_id", "messages"},
        )
        self.assertNotIn("customer_id", result)

    def test_cross_customer_read_is_rejected_without_disclosure(self):
        with self.assertRaisesRegex(ConversationError, "Conversation not found"):
            self.store.get("conv-1", "C002")

    def test_cross_customer_customer_write_is_rejected(self):
        with self.assertRaisesRegex(ConversationError, "Conversation not found"):
            self.store.append_customer("conv-1", "C002", "跨客户写入")
        self.assertEqual(self.store.get("conv-1", "C001")["messages"], [])

    def test_cross_customer_frontline_projection_is_rejected(self):
        with self.assertRaisesRegex(ConversationError, "Conversation not found"):
            self.store.append_frontline_projection(
                "conv-1",
                "C002",
                "STATUS",
                "错误的客户投影",
            )

    def test_reset_removes_customer_projection(self):
        self.store.append_customer("conv-1", "C001", "需要清理")

        self.store.reset()

        with self.assertRaisesRegex(ConversationError, "Conversation not found"):
            self.store.get("conv-1", "C001")

    def test_customer_body_is_stored_as_text_not_interpreted(self):
        body = '<img src=x onerror="alert(1)"><script>alert(2)</script>'

        message = self.store.append_customer("conv-1", "C001", body)

        self.assertEqual(message["body"], body)
        projection = self.store.get("conv-1", "C001")
        self.assertEqual(projection["messages"][0]["body"], body)


if __name__ == "__main__":
    unittest.main()
