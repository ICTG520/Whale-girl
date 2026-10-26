# 架构决策记录（ADR）

本目录记录难以回滚、影响多个模块或改变外部契约的决策。

## 状态

- `Proposed`：已提出，等待确认。
- `Accepted`：已采纳，当前实现或后续实现应遵守。
- `Superseded`：已被新 ADR 取代。
- `Deprecated`：保留但不再推荐。

## 模板

```markdown
# ADR-XXXX 标题

- 状态：Proposed / Accepted / Superseded
- 日期：YYYY-MM-DD
- 决策者：
- 关联接口：

## 背景

为什么需要做这个决定，当前约束是什么。

## 决策

明确选择什么，不选择什么。

## 后果

正面影响、负面影响、运维成本、迁移成本、隐私影响。

## 替代方案

考虑过但没有选择的方案，以及原因。

## 迁移与验收

如何落地、如何验证、如何回滚。
```

## 索引

- `0001-modular-monolith.md`：模块化单体 + 端口/适配器。
- `0002-sqlite-source-of-truth.md`：SQLite 作为当前消息事实来源。
- `0003-single-persona-and-isolation.md`：单一人设、单平台单账户、会话隔离。
- `0004-throttle-vs-budget.md`：回复限流与 token 预算分离（M5D）。
- `0005-audit-metadata-only.md`：审计默认只记录元数据（M5C）。
- `0006-outbound-persistence-and-rebuild.md`：出站回复持久化与上下文重建（M5A，Accepted）。
- `0007-layered-context-and-compaction.md`：分层上下文与摘要压缩（M5B）。
