# P3 Case recovery evidence

## Result

This deterministic Mock control-plane run records a successful Frontline information-request time window for synthetic `C001`.

| Snapshot | Case state | Project/Room behavior | Background work |
| --- | --- | --- | --- |
| [before timeout](case-before-timeout.json) | `AWAITING_CUSTOMER_INFO` | original binding created once | active |
| [closed](case-closed.json) | `CLOSED_INCOMPLETE` | original binding retained | stopped |
| [reopened](case-reopened.json) | `IDENTIFYING_ORDER` | same `case_id`, `project_id`, `project_room_id` | remains stopped until another request |

The successful request timestamp was `2026-08-14T09:02:00+08:00`; its deadline was `2026-08-15T09:02:00+08:00`. The recorded synthetic Matrix reply arrival was `2026-08-15T09:02:01+08:00`, so it was late and explicitly reopened the original Case. `reopened_count` is `1`, and the persisted Case store contains one Case only.

Unit tests also cover a reply one second before the deadline, exactly at the deadline, after the deadline while still waiting, and a post-`RESOLVED` customer objection. Both reopening paths reuse the existing Project Room.

## Truthfulness

- **已实现**：`CaseStore`'s timezone-aware deadline comparison, closure, stopped-background marker, and original-Case reopening invariants.
- **模拟执行**：timestamps and the Matrix arrival value are synthetic deterministic test inputs; this run did not wait 24 real hours or send a Matrix message.
- **方案设计 / 后续规划**：a production scheduler, durable Matrix-event ingest, and automatic same-issue matching are outside this Mock control-plane run.

No credentials, hidden reasoning, or customer data outside the synthetic `C001` fixture is present.
