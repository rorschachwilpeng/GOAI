# P3 Case recovery runbook

## Scope

This runbook describes the deterministic P3 control-plane behavior for a Frontline customer-information request. It does not create a new Project or Room.

1. When Frontline has successfully sent a minimal information request, Manager records `CUSTOMER_INFO_REQUESTED` with its timezone-aware server send time. `CaseStore` stores `reply_deadline_at = sent_at + 24h` and marks waiting background work active.
2. A customer reply is evaluated with its Matrix `origin_server_ts`, supplied as `matrix_arrival_at`, rather than when a consumer processes it. An arrival at or before the deadline returns the existing Case to `IDENTIFYING_ORDER`.
3. When no valid reply exists at the deadline, Manager records `CUSTOMER_INFO_TIMEOUT`; the Case becomes `CLOSED_INCOMPLETE` and the waiting background-work flag becomes false.
4. A later reply from the same customer for the matched original Case is recorded as `CASE_REOPENED`. It reuses the existing `case_id`, `project_id`, and `project_room_id`, increments `reopened_count`, and enters `IDENTIFYING_ORDER`.
5. A customer objection after `RESOLVED` uses the same `CASE_REOPENED` path. No timeout or late reply creates a replacement Case or Project Room.

## Boundaries

- Matrix arrival timestamps must include a timezone.
- `CUSTOMER_INFO_RECEIVED` after the deadline cannot resume a stopped Case directly; it must use the explicit re-open transition.
- The P3 run uses only synthetic timestamps and data. It does not claim an actual 24-hour wait or a production scheduler.
