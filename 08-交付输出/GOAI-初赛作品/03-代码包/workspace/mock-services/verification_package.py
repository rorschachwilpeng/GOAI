"""Freeze minimal Verification Package payloads with a tamper-evident hash."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


FORBIDDEN_FIELDS = {"hidden_reasoning", "project_room_transcript", "execution_response"}


class VerificationPackageError(ValueError):
    pass


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _contains_forbidden_field(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(FORBIDDEN_FIELDS.intersection(value)) or any(
            _contains_forbidden_field(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_field(item) for item in value)
    return False


def freeze_verification_package(payload: dict[str, Any], frozen_at: str) -> dict[str, Any]:
    if _contains_forbidden_field(payload) or "sha256" in payload:
        raise VerificationPackageError("Verification Package contains forbidden fields")
    frozen = copy.deepcopy(payload)
    frozen["frozen_at"] = frozen_at
    frozen["sha256"] = hashlib.sha256(_canonical(frozen)).hexdigest()
    return frozen


def verify_package_hash(package: dict[str, Any]) -> bool:
    if _contains_forbidden_field(package) or not isinstance(package.get("sha256"), str):
        return False
    payload = copy.deepcopy(package)
    received_hash = payload.pop("sha256")
    return hashlib.sha256(_canonical(payload)).hexdigest() == received_hash
