#!/usr/bin/env python3
"""Persistent HTTP wrapper for the deterministic GOAI Golden Path tools."""

from __future__ import annotations

import argparse
import copy
import hmac
import json
import os
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from conversation_store import ConversationError, ConversationStore

from golden_path import (
    ToolError,
    evaluate_rebooking,
    execute_rebooking,
    get_authorized_order,
    get_order_state,
    load_fixture,
    record_customer_confirmation,
    record_internal_decision,
    resolve_order_reference,
    validate_execution_authorization,
    verify_rebooking,
)


DEFAULT_FIXTURE = Path(__file__).parent / "fixtures" / "golden-case.json"
CUSTOMER_CHAT_DIR = Path(__file__).parents[1] / "customer-chat"
MAX_REQUEST_BODY_BYTES = 1024 * 1024


class RequestBodyError(ValueError):
    def __init__(self, status: HTTPStatus, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code


class InternalProjectionError(PermissionError):
    pass


class PersistentStore:
    """Process-local mutable store for the HTTP Golden Path spike."""

    def __init__(self, fixture_path: str | Path, internal_token: str):
        self.fixture_path = Path(fixture_path)
        self.internal_token = internal_token
        self.lock = threading.RLock()
        self.store = load_fixture(self.fixture_path)
        self.conversations = ConversationStore()

    def reset(self, execute_success_without_update: bool = False) -> None:
        self.store = load_fixture(self.fixture_path)
        self.store["fault_injection"]["execute_success_without_update"] = (
            execute_success_without_update
        )


def _error(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def _required_string(request: dict[str, Any], field: str) -> str:
    value = request.get(field)
    if not isinstance(value, str) or not value.strip():
        code = "MISSING_CUSTOMER_ID" if field == "customer_id" else "INVALID_REQUEST"
        raise ToolError(code, f"{field} is required")
    return value


def _required_object(request: dict[str, Any], field: str) -> dict[str, Any]:
    value = request.get(field)
    if not isinstance(value, dict):
        raise ToolError("INVALID_REQUEST", f"{field} must be a JSON object")
    return value


def make_handler(state: PersistentStore) -> type[BaseHTTPRequestHandler]:

    class RequestHandler(BaseHTTPRequestHandler):
        def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_static(self, filename: str, content_type: str) -> None:
            body = (CUSTOMER_CHAT_DIR / filename).read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _require_internal_frontline(self) -> None:
            authorization = self.headers.get("Authorization", "")
            expected = f"Bearer {state.internal_token}"
            if not hmac.compare_digest(authorization, expected):
                raise InternalProjectionError("Internal Frontline capability is required")

        def _read_request_body(self) -> bytes:
            transfer_encoding = self.headers.get("Transfer-Encoding")
            if transfer_encoding:
                encodings = [item.strip().lower() for item in transfer_encoding.split(",")]
                if encodings != ["chunked"]:
                    raise RequestBodyError(
                        HTTPStatus.BAD_REQUEST,
                        "UNSUPPORTED_TRANSFER_ENCODING",
                        "Only chunked transfer encoding is supported",
                    )
                return self._read_chunked_body()

            content_length_header = self.headers.get("Content-Length", "0")
            try:
                content_length = int(content_length_header)
            except ValueError as error:
                raise RequestBodyError(
                    HTTPStatus.BAD_REQUEST,
                    "INVALID_CONTENT_LENGTH",
                    "Content-Length must be a non-negative integer",
                ) from error
            if content_length < 0:
                raise RequestBodyError(
                    HTTPStatus.BAD_REQUEST,
                    "INVALID_CONTENT_LENGTH",
                    "Content-Length must be a non-negative integer",
                )
            if content_length > MAX_REQUEST_BODY_BYTES:
                raise RequestBodyError(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    "REQUEST_BODY_TOO_LARGE",
                    "Request body exceeds the 1 MiB limit",
                )
            body = self.rfile.read(content_length)
            if len(body) != content_length:
                raise RequestBodyError(
                    HTTPStatus.BAD_REQUEST,
                    "INCOMPLETE_REQUEST_BODY",
                    "Request body ended before Content-Length bytes were received",
                )
            return body

        def _read_chunked_body(self) -> bytes:
            chunks: list[bytes] = []
            total_size = 0
            while True:
                size_line = self.rfile.readline(8193)
                if not size_line or len(size_line) > 8192 or not size_line.endswith(b"\r\n"):
                    raise RequestBodyError(
                        HTTPStatus.BAD_REQUEST,
                        "INVALID_CHUNKED_BODY",
                        "Chunk size line is invalid",
                    )
                size_token = size_line[:-2].split(b";", 1)[0].strip()
                try:
                    chunk_size = int(size_token, 16)
                except ValueError as error:
                    raise RequestBodyError(
                        HTTPStatus.BAD_REQUEST,
                        "INVALID_CHUNKED_BODY",
                        "Chunk size must be hexadecimal",
                    ) from error
                if chunk_size < 0:
                    raise RequestBodyError(
                        HTTPStatus.BAD_REQUEST,
                        "INVALID_CHUNKED_BODY",
                        "Chunk size must be non-negative",
                    )

                if chunk_size == 0:
                    while True:
                        trailer_line = self.rfile.readline(8193)
                        if trailer_line == b"\r\n":
                            return b"".join(chunks)
                        if (
                            not trailer_line
                            or len(trailer_line) > 8192
                            or not trailer_line.endswith(b"\r\n")
                        ):
                            raise RequestBodyError(
                                HTTPStatus.BAD_REQUEST,
                                "INVALID_CHUNKED_BODY",
                                "Chunk trailer is invalid",
                            )

                total_size += chunk_size
                if total_size > MAX_REQUEST_BODY_BYTES:
                    raise RequestBodyError(
                        HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                        "REQUEST_BODY_TOO_LARGE",
                        "Request body exceeds the 1 MiB limit",
                    )
                chunk = self.rfile.read(chunk_size)
                if len(chunk) != chunk_size or self.rfile.read(2) != b"\r\n":
                    raise RequestBodyError(
                        HTTPStatus.BAD_REQUEST,
                        "INVALID_CHUNKED_BODY",
                        "Chunk data is incomplete or missing its terminator",
                    )
                chunks.append(chunk)

        def do_GET(self) -> None:  # noqa: N802
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self._send_static("index.html", "text/html; charset=utf-8")
                return
            if parsed.path == "/styles.css":
                self._send_static("styles.css", "text/css; charset=utf-8")
                return
            if parsed.path == "/app.js":
                self._send_static("app.js", "text/javascript; charset=utf-8")
                return
            if parsed.path == "/health":
                self._send_json(HTTPStatus.OK, {"status": "ok"})
                return
            if parsed.path.startswith("/conversations/"):
                conversation_id = parsed.path.removeprefix("/conversations/")
                try:
                    customer_id = parse_qs(parsed.query).get("customer_id", [""])[0]
                    projection = state.conversations.get(conversation_id, customer_id)
                    self._send_json(HTTPStatus.OK, projection)
                except ConversationError as error:
                    self._send_json(HTTPStatus.NOT_FOUND, _error("NOT_FOUND", str(error)))
                return
            self._send_json(HTTPStatus.NOT_FOUND, _error("NOT_FOUND", "Endpoint not found"))

        def do_POST(self) -> None:  # noqa: N802
            supported_paths = {
                "/reset",
                "/resolve-order-reference",
                "/get-authorized-order",
                "/evaluate-rebooking",
                "/record-customer-confirmation",
                "/record-internal-decision",
                "/validate-execution-authorization",
                "/execute-rebooking",
                "/get-order-state",
                "/verify-rebooking",
                "/internal/conversations",
            }
            is_message = self.path.startswith("/conversations/") and self.path.endswith("/messages")
            is_frontline_message = (
                self.path.startswith("/internal/conversations/")
                and self.path.endswith("/frontline-messages")
            )
            if self.path not in supported_paths and not is_message and not is_frontline_message:
                self._send_json(HTTPStatus.NOT_FOUND, _error("NOT_FOUND", "Endpoint not found"))
                return

            try:
                raw_body = self._read_request_body()
                request = json.loads(raw_body)
            except RequestBodyError as error:
                self._send_json(error.status, _error(error.code, str(error)))
                return
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    _error("INVALID_JSON", "Request body must be valid JSON"),
                )
                return

            if not isinstance(request, dict):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    _error("INVALID_REQUEST", "Request body must be a JSON object"),
                )
                return

            try:
                with state.lock:
                    result = self._dispatch(request)
            except ToolError as error:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    _error(error.code, str(error)),
                )
                return
            except ConversationError as error:
                self._send_json(HTTPStatus.BAD_REQUEST, _error("INVALID_CONVERSATION", str(error)))
                return
            except InternalProjectionError as error:
                self._send_json(HTTPStatus.FORBIDDEN, _error("FORBIDDEN", str(error)))
                return
            except (KeyError, TypeError) as error:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    _error("INVALID_REQUEST", f"Invalid request field: {error}"),
                )
                return

            self._send_json(HTTPStatus.OK, result)

        def _dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
            store = state.store
            if self.path == "/reset":
                fault = request.get("execute_success_without_update", False)
                if not isinstance(fault, bool):
                    raise ToolError(
                        "INVALID_REQUEST",
                        "execute_success_without_update must be a boolean",
                    )
                state.reset(fault)
                state.conversations.reset()
                return {"status": "reset"}

            if self.path == "/internal/conversations":
                self._require_internal_frontline()
                return state.conversations.create(
                    _required_string(request, "conversation_id"),
                    _required_string(request, "case_id"),
                    _required_string(request, "customer_id"),
                )
            if self.path.startswith("/conversations/") and self.path.endswith("/messages"):
                conversation_id = self.path.split("/")[2]
                if request.get("sender") != "CUSTOMER":
                    raise ToolError("INVALID_REQUEST", "Browser may only send CUSTOMER messages")
                return state.conversations.append_customer(
                    conversation_id,
                    _required_string(request, "customer_id"),
                    _required_string(request, "body"),
                )
            if (
                self.path.startswith("/internal/conversations/")
                and self.path.endswith("/frontline-messages")
            ):
                self._require_internal_frontline()
                conversation_id = self.path.split("/")[3]
                return state.conversations.append_frontline_projection(
                    conversation_id,
                    _required_string(request, "customer_id"),
                    _required_string(request, "message_type"),
                    _required_string(request, "body"),
                )

            if self.path == "/resolve-order-reference":
                customer_id = _required_string(request, "customer_id")
                clues = request.get("clues", {})
                if not isinstance(clues, dict):
                    raise ToolError("INVALID_CLUES", "clues must be a JSON object")
                return resolve_order_reference(store, customer_id, clues)

            if self.path == "/get-authorized-order":
                return get_authorized_order(
                    store,
                    _required_string(request, "customer_id"),
                    _required_string(request, "order_ref"),
                )

            if self.path == "/evaluate-rebooking":
                case_id = _required_string(request, "case_id")
                customer_id = _required_string(request, "customer_id")
                order_ref = _required_string(request, "order_ref")
                plan = _required_object(request, "resolution_plan")
                plan_id = _required_string(plan, "resolution_plan_id")
                existing_case = store["cases"].get(case_id)
                if existing_case and existing_case["customer_id"] != customer_id:
                    raise ToolError(
                        "CASE_CUSTOMER_CONFLICT",
                        "Case is already bound to a different customer",
                    )
                existing_plan = store["resolution_plans"].get(plan_id)
                if existing_plan and existing_plan != plan:
                    raise ToolError(
                        "RESOLUTION_PLAN_CONFLICT",
                        "Resolution plan ID is already bound to different content",
                    )
                store["cases"].setdefault(
                    case_id,
                    {
                        "case_id": case_id,
                        "customer_id": customer_id,
                        "case_state": "RESOLVING",
                        "resolution_mode": None,
                    },
                )
                result = evaluate_rebooking(store, customer_id, order_ref, plan)
                store["resolution_plans"][plan_id] = copy.deepcopy(plan)
                return result

            if self.path == "/record-customer-confirmation":
                return record_customer_confirmation(
                    store,
                    _required_string(request, "case_id"),
                    _required_string(request, "resolution_plan_id"),
                    _required_string(request, "risk_decision_id"),
                    _required_string(request, "message_event_id"),
                )

            if self.path == "/record-internal-decision":
                return record_internal_decision(
                    store,
                    _required_string(request, "case_id"),
                    _required_string(request, "resolution_plan_id"),
                    _required_string(request, "risk_decision_id"),
                    _required_string(request, "decision"),
                    _required_string(request, "message_event_id"),
                    _required_string(request, "operator_id"),
                )

            if self.path == "/execute-rebooking":
                return execute_rebooking(
                    store,
                    _required_string(request, "case_id"),
                    _required_string(request, "resolution_plan_id"),
                    _required_string(request, "risk_decision_id"),
                    _required_string(request, "idempotency_key"),
                )

            if self.path == "/validate-execution-authorization":
                return validate_execution_authorization(
                    store,
                    _required_string(request, "case_id"),
                    _required_string(request, "resolution_plan_id"),
                    _required_string(request, "risk_decision_id"),
                )

            if self.path == "/get-order-state":
                return get_order_state(
                    store,
                    _required_string(request, "customer_id"),
                    _required_string(request, "order_ref"),
                )

            if self.path == "/verify-rebooking":
                customer_id = _required_string(request, "customer_id")
                plan_id = _required_string(request, "resolution_plan_id")
                plan = store["resolution_plans"].get(plan_id)
                if not plan:
                    raise ToolError("NOT_FOUND", "Resolution plan does not exist")
                return verify_rebooking(
                    store,
                    customer_id,
                    plan,
                    _required_string(request, "idempotency_key"),
                )

            raise ToolError("NOT_FOUND", "Endpoint not found")

        def log_message(self, format: str, *args: Any) -> None:
            return

    return RequestHandler


def create_server(
    host: str = "0.0.0.0",
    port: int = 19090,
    fixture_path: str | Path = DEFAULT_FIXTURE,
    internal_token: str | None = None,
) -> ThreadingHTTPServer:
    token = internal_token or secrets.token_urlsafe(32)
    state = PersistentStore(fixture_path, token)
    server = ThreadingHTTPServer((host, port), make_handler(state))
    server.store_state = state
    server.internal_token = token
    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=19090)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args()

    server = create_server(
        args.host,
        args.port,
        args.fixture,
        internal_token=os.environ.get("GOAI_INTERNAL_TOKEN"),
    )
    print(f"GOAI mock API listening on http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
