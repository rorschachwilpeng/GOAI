# GOAI Specs

`specs/` 是 GOAI 项目的正式功能规格入口，按 [GitHub Spec Kit](https://github.com/github/spec-kit) 的 Spec-Driven Development 结构管理。

## 目录格式

```text
specs/
├── README.md
└── NNN-short-name/
    ├── spec.md
    ├── plan.md
    ├── research.md
    ├── data-model.md
    ├── quickstart.md
    ├── contracts/
    └── tasks.md
```

只有 `spec.md` 是新功能的必需起点。其他文件在 Spec 确认后，根据实际实现需要逐步创建，不为了填充目录而提前生成。

## 工作流

```text
spec.md → 用户确认 → plan.md → 用户确认 → tasks.md → 实现 → 按 Spec 验证
```

- Spec 聚焦需求和验收，不预设技术方案。
- Plan 记录技术实现和结构决策。
- Tasks 是从已确认 Spec 和 Plan 派生的执行清单。
- 需求变更先改 Spec，再同步其他产物。

## Spec 索引

| 编号 | 功能 | 状态 | 入口 |
|---|---|---|---|
| 001 | 酒店供应异常自主改订最小闭环 | Spec Approved；Plan Approved；Tasks Ready | [`spec.md`](./001-autonomous-customer-service-loop/spec.md) · [`plan.md`](./001-autonomous-customer-service-loop/plan.md) · [`tasks.md`](./001-autonomous-customer-service-loop/tasks.md) |
