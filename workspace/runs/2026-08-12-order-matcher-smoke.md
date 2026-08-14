# Order Matcher Smoke Run

- 时间：2026-08-12 21:49–21:54（Asia/Shanghai）
- Task ID：`task-20260812-135040`
- 入口：Element 中的 `Manager: default` 私聊
- 编排：AgentTeams Manager → Matrix Worker Room → `order-matcher`
- Worker：`order-matcher`，`copaw`，`kimi-k2.6`
- Skill：`identify-hotel-order`
- MCP Tool：`mcp-goai-order.resolve_order_reference`

## 输入

```json
{
  "customer_id": "C001",
  "clues": {}
}
```

## Worker 原始结果

```json
{
  "status": "MULTIPLE",
  "candidate_count": 2,
  "missing_fields": [
    "hotel_name",
    "check_in_date"
  ],
  "candidates": []
}
```

## 验收

- [x] Manager 创建 finite task，并写入 `spec.md` 与 `meta.json`。
- [x] Manager 在 Worker 专属 Matrix Room 中 @mention 并分派任务。
- [x] Worker 读取 Skill 并调用已授权 MCP Tool。
- [x] Tool 返回 `MULTIPLE` 与缺失字段，没有返回候选订单详情。
- [x] Worker @mention Manager，并在 Room 中返回结构化结果。
- [x] Manager 在 Admin DM 中汇总结果。

## 已知问题

1. Worker 的 `taskflow ack/submit` 缺少 `project_id`，但不影响本次 Tool 调用和结果回传。
2. Manager 最终自然语言摘要丢失了两个 `missing_fields` 的显示；Worker 原始 JSON 完整，后续应要求 Manager 原样嵌入结构化结果。
