"""Tests for immutable, minimal Verification Packages."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from verification_package import (  # noqa: E402
    VerificationPackageError,
    freeze_verification_package,
    verify_package_hash,
)


def package_payload() -> dict:
    return {
        "package_id": "VP-001",
        "case_id": "CASE-001",
        "customer_id": "C001",
        "order_ref": "oref_001",
        "resolution_plan_snapshot": {"resolution_plan_id": "PLAN-001"},
        "expected_result": {"status": "REBOOKED"},
        "bdd_assertions": ["status is REBOOKED"],
        "evidence_refs": ["trace://CASE-001"],
        "package_version": "v0.1",
    }


class VerificationPackageTest(unittest.TestCase):
    def test_freeze_produces_a_verifiable_normalized_hash(self) -> None:
        frozen = freeze_verification_package(
            package_payload(), "2026-08-14T09:00:00+08:00"
        )
        self.assertEqual(frozen["frozen_at"], "2026-08-14T09:00:00+08:00")
        self.assertTrue(verify_package_hash(frozen))

    def test_rejects_forbidden_fields(self) -> None:
        for field in (
            "hidden_reasoning",
            "project_room_transcript",
            "execution_response",
        ):
            payload = package_payload()
            payload[field] = "not allowed"
            with self.assertRaises(VerificationPackageError):
                freeze_verification_package(payload, "2026-08-14T09:00:00+08:00")

    def test_rejects_forbidden_fields_nested_in_dicts_and_lists(self) -> None:
        for field in (
            "hidden_reasoning",
            "project_room_transcript",
            "execution_response",
        ):
            payload = package_payload()
            payload["resolution_plan_snapshot"][field] = "not allowed"
            with self.assertRaises(VerificationPackageError):
                freeze_verification_package(payload, "2026-08-14T09:00:00+08:00")

            payload = package_payload()
            payload["evidence_refs"] = [{field: "not allowed"}]
            with self.assertRaises(VerificationPackageError):
                freeze_verification_package(payload, "2026-08-14T09:00:00+08:00")

    def test_hash_verification_rejects_nested_forbidden_fields(self) -> None:
        frozen = freeze_verification_package(
            package_payload(), "2026-08-14T09:00:00+08:00"
        )
        frozen["resolution_plan_snapshot"]["hidden_reasoning"] = "not allowed"
        self.assertFalse(verify_package_hash(frozen))

    def test_tampering_with_a_business_field_invalidates_the_hash(self) -> None:
        frozen = freeze_verification_package(
            package_payload(), "2026-08-14T09:00:00+08:00"
        )
        tampered = copy.deepcopy(frozen)
        tampered["expected_result"]["status"] = "CONFIRMED"
        self.assertFalse(verify_package_hash(tampered))
