---
name: identify-hotel-order
description: Safely identify a hotel order from an authenticated customer ID and customer-supplied clues. Use when a hotel-support case must determine whether no order, multiple orders, or one authorized order matches without exposing candidate details.
assign_when: Assign to the Frontline Agent for customer dialogue, safe order identification, information gaps, and customer confirmation recording.
---

# Identify Hotel Order

## Required input

- A trusted `customer_id` supplied by the authenticated session.
- A `clues` object containing only information the customer has supplied, such as `hotel_name` and `check_in_date`.

Never infer, replace, or broaden `customer_id` from the conversation.

## Workflow

1. Normalize only the supplied clues. Do not invent missing values.
2. Call the authorized Tool exactly once:

```bash
mcporter call mcp-goai-frontline.resolve_order_reference \
  --args '{"customer_id":"<trusted_customer_id>","clues":{}}'
```

3. Preserve the Tool result exactly:
   - `NONE`: report that no authorized order matched and list `missing_fields` if present.
   - `MULTIPLE`: report only `candidate_count` and `missing_fields`; ask the customer for those fields.
   - `UNIQUE`: return only the opaque `order_ref`, `ownership_verified`, and `matched_fields`.
4. Publish an `ORDER_LINKED` handoff to the Case Project Room only after a
   `UNIQUE` result. Include `case_id`, trusted `customer_id`, opaque
   `order_ref`, ownership result, matched fields, and allowed next action for
   the Resolution Agent. Do not add guessed order facts.
   This is the single permitted cross-Room business handoff: use
   `/opt/venv/standard/bin/copaw chats list --agent-id default --channel matrix`
   to find the already-assigned Case Project Room session, then use
   `copaw channels send` for that session with an explicit Resolution mention.
   Do not use `copaw channels list`, guess a Room, or read credentials.
5. When the Resolution Agent publishes a current plan requiring customer
   confirmation, obtain the customer's explicit message event and call
   `mcp-goai-frontline.record_customer_confirmation`. Publish the confirmation
   record to the Case Project Room.

## Safety rules

- Never reveal order IDs, hotel names, dates, or other candidate details for `NONE` or `MULTIPLE`.
- Never use an order that belongs to another customer.
- You may call mcp-goai-frontline.record_customer_confirmation only to bind an
  explicit customer message to the current Case, plan, and risk decision. This
  is a support-system record, not an order business write.
- Never write order state, call the order-execution Tool, or call any
  Resolution or Verification Surface.
- Do not investigate supply evidence or make rebooking plans.
- If the Tool fails, publish its error to the Case Project Room; do not fabricate a match.
