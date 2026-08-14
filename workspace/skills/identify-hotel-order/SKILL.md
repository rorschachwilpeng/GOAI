---
name: identify-hotel-order
description: Safely identify a hotel order from an authenticated customer ID and customer-supplied clues. Use when a hotel-support case must determine whether no order, multiple orders, or one authorized order matches without exposing candidate details.
assign_when: Assign to an order-matching worker that handles hotel booking identification, information gaps, and safe customer follow-up.
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
mcporter call mcp-goai-order.resolve_order_reference \
  --args '{"customer_id":"<trusted_customer_id>","clues":{}}'
```

3. Preserve the Tool result exactly:
   - `NONE`: report that no authorized order matched and list `missing_fields` if present.
   - `MULTIPLE`: report only `candidate_count` and `missing_fields`; ask the customer for those fields.
   - `UNIQUE`: return only the opaque `order_ref`, `ownership_verified`, and `matched_fields`.
4. Return structured JSON to the Manager. Do not add guessed order facts.

## Safety rules

- Never reveal order IDs, hotel names, dates, or other candidate details for `NONE` or `MULTIPLE`.
- Never use an order that belongs to another customer.
- Never call a write Tool or change an order.
- If the Tool fails, return its error to the Manager; do not fabricate a match.
