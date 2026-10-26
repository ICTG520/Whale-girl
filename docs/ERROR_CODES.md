# 鲸鱼娘错误码与失败行为

- 版本：v0.2
- 日期：2026-10-25
- 状态：当前异常类型和 M5A 持久化语义已实现；统一大写错误码仍为草案
- 关联文档：`docs/INTERFACES.md`、`docs/ARCHITECTURE.md`、`docs/CONFIGURATION.md`

## 1. 当前错误处理路径

当前没有统一的持久化错误码表，错误以 Python 异常和日志类别表达。

```text
DeepSeekProvider
-> ports/llm.py 异常
-> AIReplyGenerator 捕获
-> 固定回复或沉默
-> plugins/qq_gateway 捕获未预期异常并记录日志
```

当前特点：

- 模型错误在生成器内部消化，不向 QQ 发送错误详情。
- 限流命中返回 `None`，不回退固定回复。
- 插件捕获所有未预期异常，避免单条消息打断事件循环。
- 没有 audit trace、HTTP 错误响应或错误码数据库字段。

## 2. 当前异常类型

来源：`src/whale_girl/ports/llm.py`

| 异常 | 含义 | 当前用户可见行为 |
|---|---|---|
| `LLMConfigurationError` | 缺少 Key 或供应商配置 | 私聊按配置回退；群聊默认沉默 |
| `LLMTimeoutError` | 请求超时 | 私聊按配置回退；群聊默认沉默 |
| `LLMAuthenticationError` | Key 被拒绝 | 私聊按配置回退；群聊默认沉默 |
| `LLMRateLimitError` | 供应商限流 | 私聊按配置回退；群聊默认沉默 |
| `LLMConnectionError` | 无法连接供应商 | 私聊按配置回退；群聊默认沉默 |
| `LLMProviderError` | 供应商错误或无效响应 | 私聊按配置回退；群聊默认沉默 |
| `LLMEmptyResponseError` | 空候选或空文本 | 私聊按配置回退；群聊默认沉默 |

## 3. 当前限流原因

来源：`src/whale_girl/application/ai_guard.py`

| 原因 | 含义 | 行为 |
|---|---|---|
| `conversation_cooldown` | 同一会话冷却中 | 返回 `None`，不调用模型 |
| `minute_limit` | 全局每分钟调用上限 | 返回 `None`，不调用模型 |
| `daily_limit` | 全局每日调用上限 | 返回 `None`，不调用模型 |

说明：

- `cooldown_seconds=0` 表示关闭冷却。
- `max_calls_per_minute=0` 表示不限制每分钟调用。
- `max_calls_per_day=0` 表示不限制每日调用。
- 当前本机 `.env` 将三者都设为 `0`，因此当前运行实例不会触发这三类限流；错误码仍保留，供重新启用限制时使用。
- 限流命中时不会回退固定回复，避免绕过限制刷屏。
- 当前计数器在进程内存，重启清零。

## 4. 当前回退原因

来源：`src/whale_girl/application/reply_generators.py`

| 原因 | 含义 | 行为 |
|---|---|---|
| `empty_context` | SQLite 中尚未重建出任何上下文 | 按配置回退或沉默 |
| `llm_error` | 模型调用抛出 `LLMError` | 按配置回退或沉默 |
| `unexpected_error` | 未预期异常 | 按配置回退或沉默 |

注意：

- 用户消息在模型调用前已经写入 SQLite；模型失败不会删除它。
- 回退固定回复只有在平台发送成功后才写入 outbound 消息，并在下一轮上下文出现。
- 发送失败时 turn 标记为 `failed`，不写 outbound，避免把未送达内容当作历史。

## 5. 统一错误码草案

M5 计划使用稳定的大写错误码。当前代码尚未实现这些常量，不能作为稳定依赖。

### 5.1 模型与配置

| 错误码 | 当前映射 | 可重试 | 默认行为 | 审计级别 |
|---|---|---|---|---|
| `LLM_CONFIGURATION` | `LLMConfigurationError` | 否 | 私聊回退/群聊沉默 | error |
| `LLM_AUTHENTICATION` | `LLMAuthenticationError` | 否 | 私聊回退/群聊沉默 | error |
| `LLM_TIMEOUT` | `LLMTimeoutError` | 由客户端配置决定 | 私聊回退/群聊沉默 | warning |
| `LLM_RATE_LIMIT` | `LLMRateLimitError` | 由客户端配置决定 | 私聊回退/群聊沉默 | warning |
| `LLM_CONNECTION` | `LLMConnectionError` | 由客户端配置决定 | 私聊回退/群聊沉默 | warning |
| `LLM_PROVIDER_ERROR` | `LLMProviderError` | 否（应用层不额外重试） | 私聊回退/群聊沉默 | error |
| `LLM_EMPTY_RESPONSE` | `LLMEmptyResponseError` | 否 | 私聊回退/群聊沉默 | warning |
| `CONFIG_INVALID` | `ValueError` / 解析错误 | 否 | 启动失败 | fatal |
| `PERSONA_INVALID` | `PersonaConfigError` | 否 | 启动失败 | fatal |

说明：

- “由客户端配置决定”指 `AsyncOpenAI` 按 `AI_MAX_RETRIES` 自行处理底层重试；应用层不额外重试。
- 任何情况下都不记录 Key、完整请求体或聊天正文。

### 5.2 限流与预算

| 错误码 | 当前映射 | 可重试 | 默认行为 | 审计级别 |
|---|---|---|---|---|
| `THROTTLE_COOLDOWN` | `conversation_cooldown` | 否 | 沉默 | info |
| `THROTTLE_MINUTE` | `minute_limit` | 否 | 沉默 | info |
| `THROTTLE_DAILY` | `daily_limit` | 否 | 沉默 | info |
| `QUOTA_EXHAUSTED` | 尚无 | 否 | 群聊沉默；私聊可选提示 | warning |
| `BUDGET_UNAVAILABLE` | 尚无 | 视策略 | 降级为不阻断或保守阻断 | warning |

规则：

- `QUOTA_EXHAUSTED` 禁止自动重试。
- 限流和预算耗尽都不应回退成固定回复来绕过限制。
- 预算耗尽是否给私聊提示由配置决定；群聊默认沉默。

### 5.3 上下文、记忆与审计

| 错误码 | 含义 | 可重试 | 默认行为 | 审计级别 |
|---|---|---|---|---|
| `CONTEXT_TOO_LARGE` | 组装后仍超过输入预算 | 否 | 降级裁剪或跳过调用 | warning |
| `SUMMARY_FAILED` | 摘要生成失败 | 可有限重试 | 使用近期原文 | warning |
| `MEMORY_RETRIEVAL_FAILED` | 记忆检索失败 | 可有限重试 | 返回空记忆 | warning |
| `MEMORY_EXTRACTION_FAILED` | 记忆提取失败 | 可后台重试 | 不影响回复 | warning |
| `AUDIT_WRITE_FAILED` | 审计写入失败 | 可丢弃 | 不影响回复 | warning |
| `SEND_FAILED` | 平台发送失败 | 当前不自动重试 | turn=failed；不写 outbound | error |
| `POLICY_BLOCKED` | 策略明确拒绝 | 否 | 沉默或固定提示 | info |
| `INTERNAL_ERROR` | 未分类内部异常 | 否 | 记录堆栈摘要，不向用户暴露 | error |

## 6. 重试策略

| 场景 | 应用层重试 | 说明 |
|---|---|---|
| 模型超时 | 不额外重试 | 底层 OpenAI 客户端可配置重试 |
| 模型限流 | 不额外重试 | 避免放大供应商限流 |
| 模型 5xx | 不额外重试 | 由客户端配置决定 |
| 模型空回复 | 不重试 | 直接回退或沉默 |
| 配置/鉴权错误 | 不重试 | 需要人工修复 |
| `QUOTA_EXHAUSTED` | 不重试 | 硬预算边界 |
| 摘要失败 | 后台有限重试 | 不阻塞回复 |
| 记忆提取失败 | 后台有限重试 | 不影响回复 |
| 审计写入失败 | 不重试 | 丢弃低优先级 span，保留错误 |
| 发送失败 | 当前不自动重试 | 后续按平台幂等能力设计 |

## 7. 用户可见行为矩阵

| 场景 | 私聊 | 群聊 |
|---|---|---|
| 非白名单 | 观察入库，不回复 | 非白名单群不入库、不回复 |
| 普通群消息 | 不适用 | 入库并观察，不调用模型 |
| @ / 唤醒词 | 不适用 | 调用模型 |
| 冷却中 | 不调用模型 | 不调用模型，沉默 |
| 分钟/日限流 | 不调用模型 | 不调用模型，沉默 |
| 模型失败 | 按 `AI_FALLBACK_TO_FIXED` | 按 `AI_GROUP_FALLBACK_TO_FIXED`，默认沉默 |
| 预算耗尽 | 可选简短提示 | 默认沉默 |
| 重复消息 | 忽略 | 忽略 |
| 机器人自己的消息 | 忽略 | 忽略 |
| 未预期异常 | 插件记录日志 | 插件记录日志 |

## 8. 日志与审计规则

当前日志：

- 使用标准库 `logging`。
- 记录错误类别，不记录异常消息中的敏感内容。
- 不记录消息正文、完整提示词、回复正文、Key、Token。
- 插件记录 `Failed to process QQ message` 和堆栈。

M5 审计：

- 每条 trace 至少记录：trace_id、session_id、状态、错误码、耗时。
- 错误请求 100% 记录；成功请求按采样率。
- 审计写入失败不影响回复。
- 审计默认只保存元数据和上下文清单，不保存正文。
- 错误码是审计和状态接口的稳定字段。

## 9. 错误码治理

- 新增错误码必须更新本文档。
- 错误码只增不改语义。
- 废弃错误码要保留映射和移除版本。
- 不允许在业务代码中直接写自由文本错误码。
- 错误码不得包含用户输入、群号、QQ 号或密钥。
- 错误码用于审计和状态聚合，不直接暴露给 QQ 用户。

## 10. 版本记录

- v0.1（2026-10-24）：记录当前异常、限流原因、回退原因，并建立 M5 统一错误码草案。
- v0.2（2026-10-25）：更新 M5A 的上下文重建、固定回复和发送失败语义。
