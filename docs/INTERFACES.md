# 鲸鱼娘接口清单

- 版本：v0.2
- 日期：2026-10-25
- 状态：基线；M2～M5A 为当前实现，M5B 及以后为草案
- 适用仓库：`Whale-girl`
- 关联文档：`docs/ARCHITECTURE.md`、`docs/DATA_MODEL.md`、`docs/CONFIGURATION.md`、`docs/ERROR_CODES.md`

## 1. 这份清单是什么

这不是函数说明书，而是**契约登记表**。

它只登记满足以下任一条件的接口：

- 跨模块边界。
- 跨进程或跨网络。
- 会被多个实现共享。
- 变更成本高，容易造成数据或行为不兼容。
- 涉及隐私、审计、预算或安全边界。

不登记私有函数、一次性脚本内部逻辑和纯实现细节。

每条接口必须说明：

- 谁提供、谁消费。
- 输入输出和错误。
- 幂等、顺序、并发和超时。
- 副作用和隐私边界。
- 对应测试。
- 稳定性和变更规则。

## 2. 稳定性分级

| 级别 | 含义 | 变更规则 |
|---|---|---|
| `stable` | 已验收、外部可见或跨模块长期依赖 | 优先兼容性新增；破坏性变更必须升版本、写迁移和 ADR |
| `internal` | 内部端口，允许调整 | 必须同步修改所有实现、契约测试和调用方 |
| `draft` | 规划或试验中 | 不能被稳定代码依赖；变更不保证兼容 |
| `deprecated` | 计划移除 | 必须给出替代接口、迁移窗口和移除版本 |

兼容性规则：

- 新增可选字段优先于修改旧字段。
- 不改变已有字段语义。
- 不把内部实现类型泄漏到稳定接口。
- 错误码只增不改语义；废弃错误码要保留映射。
- 数据库变更必须通过迁移，不直接改旧迁移。

## 3. 单一事实来源

| 内容 | 事实来源 |
|---|---|
| 内部 Python 类型 | `src/whale_girl/ports/` 中的 `Protocol` 和 `domain/` 中的 dataclass |
| 外部 HTTP 接口 | 未来的 OpenAPI 文件；当前为本文档草案 |
| 数据库结构 | `src/whale_girl/infrastructure/persistence/sqlite.py` 中的迁移 |
| 环境变量 | `src/whale_girl/bootstrap/config.py` 和 `.env.example` |
| 错误码 | `src/whale_girl/ports/llm.py`、`application/ai_guard.py` 和 `docs/ERROR_CODES.md` |
| 人设格式 | `config/persona.toml` 和 `bootstrap/persona.py` |

本文档只做索引和语义说明，不复制完整类型定义。类型变化以代码为准，但必须同步更新本文档。

## 4. 接口总表

### 4.1 当前实现

| ID | 名称 | 类型 | 状态 | 主要源文件 |
|---|---|---|---|---|
| `IF-DOM-001` | 领域消息与会话模型 | 内部模型 | stable | `domain/message.py`、`domain/conversation.py` |
| `IF-APP-001` | 入站消息处理用例 | 内部应用接口 | stable | `application/handle_message.py` |
| `IF-POL-001` | 回复策略 | 内部应用接口 | stable | `application/reply_policy.py` |
| `IF-REP-001` | 回复生成器 | 内部端口 | stable | `ports/reply_generator.py` |
| `IF-CTX-001` | 近期上下文存储 | 内部端口 | stable | `ports/context.py` |
| `IF-LIM-001` | AI 请求限流 | 内部端口 | stable | `ports/limiter.py` |
| `IF-MSG-001` | 消息仓储 | 内部端口 | stable | `ports/repositories.py` |
| `IF-SESS-001` | 会话记录与 turn | 数据边界 | internal | `infrastructure/persistence/sqlite.py`、`domain/turn.py` |
| `IF-LLM-001` | 模型调用 | 内部端口 | stable | `ports/llm.py` |
| `IF-PLAT-001` | OneBot 事件映射 | 平台边界 | stable | `infrastructure/connectors/qq/mapping.py` |
| `IF-PLAT-002` | QQ 出站发送 | 平台边界 | stable（当前实现） | `plugins/qq_gateway/__init__.py` |
| `IF-PER-001` | 人设加载 | 配置边界 | stable | `bootstrap/persona.py` |
| `IF-CFG-001` | 运行配置 | 配置边界 | stable | `bootstrap/config.py` |
| `IF-DB-001` | SQLite 结构与迁移 | 数据边界 | stable | `infrastructure/persistence/sqlite.py` |
| `IF-ERR-001` | 错误分类 | 内部契约 | stable（异常类型） | `ports/llm.py`、`application/ai_guard.py` |
| `IF-LOG-001` | 日志约定 | 运维契约 | internal | 各模块 logger |

### 4.2 M5 草案

以下接口尚未实现，不能作为稳定代码依赖。

| ID | 名称 | 类型 | 状态 |
|---|---|---|---|
| `IF-CTX-002` | 上下文组装器 | 内部端口 | draft |
| `IF-CTX-003` | 摘要压缩 | 内部端口 | draft |
| `IF-MEM-001` | 长期记忆存储与检索 | 内部端口 | draft |
| `IF-AUD-001` | 调用审计 | 内部端口 | draft |
| `IF-BUD-001` | token 预算 | 内部端口 | draft |
| `IF-OBS-001` | 运行状态与健康检查 | 外部 HTTP / 内部端口 | draft |
| `IF-PLAT-003` | 通用平台连接器 | 内部端口 | draft |
| `IF-REL-001` | 中转站契约 | 外部 HTTP | draft |
| `IF-TOOL-001` | 工具与 Skill 注册 | 内部端口 | draft |
| `IF-ADMIN-001` | 管理后台 API | 外部 HTTP | draft |

## 5. 当前接口详情

### IF-DOM-001 领域消息与会话模型

- 类型：内部领域模型
- 状态：`stable`
- 源文件：`src/whale_girl/domain/message.py`、`account.py`、`conversation.py`、`identity.py`、`persona.py`
- 消费者：插件、应用层、端口、基础设施
- 关键类型：
  - `ConversationType`：`group`、`private`
  - `MessagePart`：`type` + `data`
  - `InboundMessage`
   - `StoredMessage`
  - `OutboundReply`
   - `MessageOrigin`：`inbound` / `outbound` / `system`
   - `Turn`、`TurnTrigger`、`TurnStatus`
  - `PlatformAccount`
  - `Conversation`
  - `AgentIdentity`
  - `PersonaVersion`
- `InboundMessage` 字段：
  - `platform`、`account_id`
  - `conversation_type`、`conversation_id`
  - `message_id`
  - `sender_id`、`sender_name`
  - `timestamp`
  - `parts`
  - `is_to_me`、`is_self`
  - `reply_to_message_id`
  - `raw_event`（`repr=False`、`compare=False`）
- `InboundMessage.text`：只拼接 `type == "text"` 的片段。
- `StoredMessage`：持久化后的消息，包含内部 `id`、`origin`、`turn_id` 和 `conversation_ref_id`。
- `OutboundReply`：平台、账户、会话、文本、可选回复目标和 `turn_id`。
- 不变量：
  - 领域模型不包含 NoneBot、OpenAI、SQLite、HTTP SDK 类型。
  - 时间戳应为带时区的时间。
   - 消息持久化唯一性由 `(platform, account_id, message_id)` 保证。
   - 消息顺序和上下文水位使用内部 `id`，不使用平台 `message_id`。
- 测试：`tests/test_qq_mapping.py`、`tests/test_persona_and_context.py`、`tests/test_message_pipeline.py`
- 备注：`PlatformAccount` 不强制执行“每个平台一个账户”，唯一性由应用策略和部署约束保证。

### IF-APP-001 入站消息处理用例

- 类型：内部应用接口
- 状态：`stable`
- 源文件：`src/whale_girl/application/handle_message.py`
- 方法：`HandleInboundMessage.execute(message: InboundMessage) -> OutboundReply | None`
- 消费者：`plugins/qq_gateway`
- 行为：
  1. `is_self=True` 直接返回 `None`，不保存。
  2. `ReplyPolicy.should_reply()` 判断是否触发。
  3. 非白名单群直接返回 `None`，不保存。
  4. `MessageRepository.save_inbound()` 去重；重复消息返回 `None`。
  5. 群聊普通消息只入库，不创建 turn、不调用生成器。
  6. 私聊未触发时只入库，不创建 turn。
  7. 触发回复时创建 `pending` turn。
  8. 选择固定回复、私聊 AI 或群聊 AI 生成器。
  9. 生成成功后 turn 为 `generated`；空回复或限流为 `suppressed`；异常为 `failed`。
  10. 返回带 `turn_id` 的 `OutboundReply` 或 `None`；不负责发送。
- 副作用：
  - 写入入站消息。
  - 可能创建和更新 turn。
  - 可能调用模型并记录限流用量。
- 错误：
  - 本用例不捕获仓储等未预期异常；由插件统一捕获。
  - 模型错误由生成器内部转成回退或沉默。
- 幂等：依赖仓储唯一键；同一 `message_id` 不会重复处理。
- 发送回写：
  - `record_sent(reply, platform_message_id)`：写 outbound 消息并把 turn 更新为 `sent`。
  - `record_failed(reply)`：只把 turn 更新为 `failed`，不写 outbound。
- 测试：`tests/test_message_pipeline.py`
- 备注：当前直接依赖 `bootstrap.config.Settings`，是已知分层偏差。

### IF-POL-001 回复策略

- 类型：内部应用接口
- 状态：`stable`
- 源文件：`src/whale_girl/application/reply_policy.py`
- 方法：`ReplyPolicy.should_reply(message: InboundMessage) -> bool`
- 规则：
  - `is_self=True` 或 `REPLY_ENABLED=false`：不回复。
  - 私聊：发送者在 `QQ_FRIEND_WHITELIST` 中才回复。
  - 群聊：群在 `QQ_GROUP_WHITELIST` 中，并且 `is_to_me=True` 或文本命中唤醒词。
  - 唤醒词使用 `casefold()` 后做子串匹配，不是正则。
- 副作用：无。
- 测试：`tests/test_message_pipeline.py`
- 备注：群白名单检查在用例层还会重复一次，用于决定是否持久化。

### IF-REP-001 回复生成器

- 类型：内部端口
- 状态：`stable`
- 源文件：`src/whale_girl/ports/reply_generator.py`
- 方法：
  - `ReplyGenerator.generate(message) -> str | None`
- 当前实现：
  - `FixedReplyGenerator`：固定骨架回复。
  - `AIReplyGenerator`：上下文 + 人设 + 模型 + 限流 + 回退。
- 契约：
  - 返回文本或 `None`；不负责发送。
  - AI 生成器只读取上下文，不自行写入或观察消息。
  - 入站消息由用例在生成前持久化；出站回复由发送成功后的回写逻辑持久化。
  - 失败是否回退固定回复由配置决定。
- 当前行为细节：
  - 上下文从 SQLite 重建；当前消息已落库，自然位于末尾。
  - 被限流的消息仍保留在 SQLite，后续触发时会出现在上下文中。
  - 回退固定回复只有发送成功后才写入上下文。
  - 空文本、空回复和异常分别有不同内部原因。
- 测试：`tests/test_ai_reply.py`、`tests/test_message_pipeline.py`

### IF-CTX-001 近期上下文存储

- 类型：内部端口
- 状态：`stable`（当前生产实现为 SQLite 重建）
- 源文件：`src/whale_girl/ports/context.py`、`infrastructure/persistence/sqlite_context.py`
- 关键类型：
  - `ConversationKey(platform, account_id, conversation_type, conversation_id)`
  - `ContextMessage(role, content)`，角色为 `user` / `assistant`
- 方法：
  - `load(key, max_messages, max_chars) -> list[ContextMessage]`
- 当前实现语义：
  - 按 `ConversationKey` 隔离。
  - 从 `messages` 按内部 `id` 取最近 N 条并重建上下文。
  - `inbound` 映射为 `user`，`is_self/outbound` 映射为 `assistant`。
  - `system` 消息跳过。
  - `load()` 先按 `max_messages` 取尾部，再按 `max_chars` 从后向前选择。
  - 单条超长消息且尚未选中任何内容时，保留尾部 `remaining` 个字符。
  - 返回顺序为时间正序。
- 当前限制：
  - 没有 token 预算。
  - 没有摘要、长期记忆、会话状态。
- 测试：`tests/test_persona_and_context.py`、`tests/test_ai_reply.py`
- M5B 方向：在近期原文之外增加状态卡、摘要和长期记忆。

### IF-LIM-001 AI 请求限流

- 类型：内部端口
- 状态：`stable`
- 源文件：`src/whale_girl/ports/limiter.py`、`application/ai_guard.py`
- 关键类型：
  - `AIRequestContext(platform, account_id, conversation_type, conversation_id, sender_id)`
  - `LimitDecision(allowed, reason)`
  - `AIUsageSnapshot(day, calls_today, input_tokens_today, output_tokens_today)`
- 方法：
  - `begin(request) -> LimitDecision`
  - `record_usage(request, input_tokens, output_tokens)`
  - `snapshot -> AIUsageSnapshot`
- 当前实现 `AIRequestGuard`：
  - 每会话冷却：`conversation_cooldown`
  - 全局每分钟调用上限：`minute_limit`
  - 全局每日调用上限：`daily_limit`
  - `cooldown_seconds=0` 表示关闭冷却。
  - `max_calls_per_minute=0` 表示不限制每分钟调用。
  - `max_calls_per_day=0` 表示不限制每日调用。
  - 当前本机 `.env` 将冷却、分钟和每日限制都设为 `0`，但仍保留调用和 token 计数。
  - 日切使用本地 `date.today()`。
  - 计数器在进程内存，重启清零。
- 语义：
  - `begin()` 是准入并记账调用次数；被拒绝时不增加调用次数。
  - `record_usage()` 在模型返回后累加 token。
  - 限流命中时生成器返回 `None`，不回退固定回复。
- 测试：`tests/test_ai_guard.py`、`tests/test_ai_reply.py`
- M5 方向：保留为 `ReplyThrottle`，与 `IF-BUD-001` 的 token 预算分离。

### IF-MSG-001 消息仓储

- 类型：内部端口
- 状态：`stable`
- 源文件：`src/whale_girl/ports/repositories.py`
- 实现：
  - `SQLiteMessageRepository`
  - `InMemoryMessageRepository`（测试/骨架）
- 方法：
  - `initialize()`
  - `save_inbound(message) -> StoredMessage | None`
  - `save(message) -> bool`
  - `create_turn(message, trigger_type, persona_version) -> Turn`
  - `mark_turn_generated(turn_id)`
  - `mark_turn_suppressed(turn_id)`
  - `mark_turn_failed(turn_id)`
  - `save_outbound(reply, platform_message_id, agent_name) -> StoredMessage`
  - `list_for_conversation(platform, account_id, conversation_type, external_id)`
  - `list_recent(platform?, account_id?, conversation_type?, external_id?, limit=50)`
- 语义：
  - `save_inbound()` 返回 `None` 表示 `(platform, account_id, message_id)` 已存在。
  - `save()` 是兼容包装，返回布尔值。
  - `create_turn()` 同时把入站消息回填 `turn_id`。
  - `save_outbound()` 只在发送成功后调用，写入 `origin=outbound`、`is_self=1`；无平台 ID 时使用 `local:<uuid>`。
  - `list_for_conversation()` 和 `list_recent()` 按内部 `id` 正序返回 `StoredMessage`。
  - `list_recent()` 先取最新 N 条，再反转；`limit` 被限制在 1..500。
  - 过滤条件均可选。
- 当前限制：
  - 没有摘要、记忆、审计或用量接口。
  - 没有删除和归档接口。
- 测试：`tests/test_sqlite_repository.py`
- 备注：M5A 已复用 `messages` 保存出站回复，并增加 `agent_sessions` / `turns`。

### IF-SESS-001 会话记录与 turn

- 类型：数据边界
- 状态：`internal`
- 源文件：`src/whale_girl/infrastructure/persistence/sqlite.py`、`domain/turn.py`
- 表：`agent_sessions`、`turns`
- 语义：
  - 一个 `conversations` 对应一个 `agent_sessions`。
  - 一次触发的入站消息对应一个 turn。
  - turn 状态为 `pending`、`generated`、`suppressed`、`sent`、`failed`。
  - 发送成功才关联 `outbound_message_id`。
  - `state_json` 当前为空，M5B 再定义状态卡结构。
- 测试：`tests/test_message_pipeline.py`、`tests/test_sqlite_repository.py`

### IF-LLM-001 模型调用

- 类型：内部端口
- 状态：`stable`
- 源文件：`src/whale_girl/ports/llm.py`
- 实现：`infrastructure/llm/deepseek.py`
- 方法：`LLMProvider.generate(request: LLMRequest) -> LLMResult`
- 输入：
  - `system_prompt`
  - `messages: tuple[LLMMessage, ...]`
  - `max_output_tokens`
  - `temperature`
  - `timeout_seconds`
- 输出：
  - `text`
  - `model`
  - `input_tokens`
  - `output_tokens`
  - `latency_ms`
- 当前 DeepSeek 实现：
  - 使用 `AsyncOpenAI`，`base_url` 指向 DeepSeek。
  - 把 system prompt 作为第一条 system message。
  - 调用 `chat.completions.create`，不启用流式、不启用工具调用。
  - `max_retries` 传给 OpenAI 客户端，由客户端处理底层重试。
  - 捕获超时、鉴权、限流、连接、HTTP 状态和未知异常，映射为端口错误。
  - 日志只记录异常类别，不记录 Key 或消息正文。
- 错误：见 `IF-ERR-001`。
- 测试：`tests/test_deepseek_provider.py`
- 备注：供应商 SDK 类型不得进入应用层。

### IF-PLAT-001 OneBot 事件映射

- 类型：平台边界
- 状态：`stable`
- 源文件：`src/whale_girl/infrastructure/connectors/qq/mapping.py`
- 方法：`event_to_inbound(event: MessageEvent) -> InboundMessage`
- 支持：
  - `GroupMessageEvent` -> `ConversationType.GROUP`，`conversation_id = group_id`
  - `PrivateMessageEvent` -> `ConversationType.PRIVATE`，`conversation_id = user_id`
  - 其他 `MessageEvent` 子类 -> `TypeError`
- 字段映射：
  - `platform = "qq"`
  - `account_id = self_id`
  - `message_id = event.message_id`
  - `sender_id = user_id`
  - `sender_name = card / nickname / user_id`
  - `timestamp = event.time` 转 UTC
  - `parts` 来自 OneBot message segments
  - `is_to_me = event.is_tome()`
  - `is_self = user_id == self_id`
  - `reply_to_message_id` 来自 `event.reply`
  - `raw_event = event.model_dump(mode="json")`
- 当前插件只监听 `on_message`，不处理 notice、request、meta_event。
- 测试：`tests/test_qq_mapping.py`
- 隐私：`raw_event` 可能包含消息正文和平台元数据，只允许本地持久化，不写入审计正文。

### IF-PLAT-002 QQ 出站发送

- 类型：平台边界
- 状态：`stable`（当前实现）
- 源文件：`plugins/qq_gateway/__init__.py`
- 当前路径：`bot.send(event, reply.text)`
- 语义：
  - 每个 `OutboundReply` 发送一条文本消息。
  - 发送成功时提取平台 `message_id`，调用 `record_sent()` 写入 outbound 消息并把 turn 更新为 `sent`。
  - 平台不返回 ID 时使用 `local:<uuid>`。
  - 发送异常时调用 `record_failed()`，turn 变为 `failed`，不写 outbound。
  - 回写失败只记录日志，不回滚已经发送到 QQ 的消息。
- 当前限制：
  - `OutboundReply` 的会话字段未用于发送路由。
  - 不支持主动消息、图片、卡片、合并转发或引用回复。
  - 没有发送幂等键或失败重试。
- 测试：当前通过真实 QQ 手工验证；自动化测试未覆盖真实发送。
- M5A 状态：发送成功回写 outbound 已实现。

### IF-PLAT-003 通用平台连接器

- 类型：内部端口
- 状态：`draft`
- 源文件：`src/whale_girl/ports/connector.py`
- 方法：
  - `start()`
  - `stop()`
  - `send(reply: OutboundReply)`
- 当前状态：已定义但未接入 NoneBot 发送路径。
- 目标语义：
  - 平台无关的发送边界。
  - 成功返回平台消息 ID 或确认结果。
  - 失败抛出结构化发送错误。
  - 不把平台 SDK 类型带入应用层。
- 备注：在第二个平台连接器出现前，不强制重写当前 QQ 发送路径。

### IF-PER-001 人设加载

- 类型：配置边界
- 状态：`stable`
- 源文件：`src/whale_girl/bootstrap/persona.py`
- 方法：`load_persona(path: Path) -> PersonaVersion`
- 输入：`config/persona.toml`
- 必填字段：
  - `version`：整数，>= 1
  - `name`：非空
  - `system_prompt`：非空
  - `active`：必须为 true（当前只允许一个 active 版本）
- 错误：`PersonaConfigError`
- 语义：
  - 启动时加载一次，不热更新。
  - 当前不保存历史版本，但审计规划会记录人设版本。
- 测试：`tests/test_persona_and_context.py`

### IF-CFG-001 运行配置

- 类型：配置边界
- 状态：`stable`
- 源文件：`src/whale_girl/bootstrap/config.py`
- 方法：`Settings.from_env(env: Mapping[str, str] | None = None) -> Settings`
- 语义：
  - `Settings` 是 frozen dataclass。
  - 空值通常回退默认值。
  - 列表支持 JSON 数组或逗号分隔。
  - 端口、整数、浮点、布尔和回复模式有校验。
  - `DEEPSEEK_API_KEY`、`ONEBOT_V11_ACCESS_TOKEN` 的 `repr` 被隐藏。
  - 启动后不热更新。
- 完整变量见 `docs/CONFIGURATION.md`。
- 测试：`tests/test_config.py`

### IF-DB-001 SQLite 结构与迁移

- 类型：数据边界
- 状态：`stable`
- 源文件：`src/whale_girl/infrastructure/persistence/sqlite.py`
- 当前迁移版本：2
- 表：`schema_migrations`、`conversations`、`messages`、`agent_sessions`、`turns`
- 语义：
  - `initialize()` 幂等。
  - 每个迁移在 `BEGIN IMMEDIATE` 中执行，失败回滚。
  - 初始化设置 WAL、`synchronous=NORMAL`、`busy_timeout`。
  - 每个连接设置 `foreign_keys=ON`。
  - 唯一键 `(platform, account_id, message_id)` 负责去重。
  - v1 -> v2 增量迁移保留已有消息并回填 `origin` / `conversation_ref_id`。
- 完整结构见 `docs/DATA_MODEL.md`。
- 测试：`tests/test_sqlite_repository.py`

### IF-ERR-001 错误分类

- 类型：内部契约
- 状态：`stable`（异常类型）；结构化错误码为 draft
- 源文件：`src/whale_girl/ports/llm.py`、`application/ai_guard.py`
- 当前异常：
  - `LLMConfigurationError`
  - `LLMTimeoutError`
  - `LLMAuthenticationError`
  - `LLMRateLimitError`
  - `LLMConnectionError`
  - `LLMProviderError`
  - `LLMEmptyResponseError`
- 当前限流原因：
  - `conversation_cooldown`
  - `minute_limit`
  - `daily_limit`
- 当前回退原因：
  - `empty_text`
  - `llm_error`
  - `unexpected_error`
- 完整错误码、重试和用户可见行为见 `docs/ERROR_CODES.md`。

### IF-LOG-001 日志约定

- 类型：运维契约
- 状态：`internal`
- 当前使用标准库 `logging`。
- 主要 logger：
  - `whale_girl.qq_gateway`
  - `whale_girl.application.handle_message`
  - `whale_girl.application.reply_generators`
  - `whale_girl.bootstrap.container`
  - `whale_girl.infrastructure.llm.deepseek`
- 当前记录：
  - 会话类型、账号、会话 ID、发送者、消息 ID、是否 @。
  - 模型、token、耗时。
  - 错误类别。
- 当前不记录：
  - 消息正文。
  - 完整提示词。
  - 模型回复正文。
  - API Key、OneBot Token、Cookie。
- M5 方向：结构化 JSON 日志、trace_id、session_id、统一字段。

## 6. M5 草案接口

以下接口尚未实现。实现前必须先在 `docs/ARCHITECTURE.md` 和 ADR 中确认边界。

### IF-SESS-001 会话状态存储

- 方法草案：
  - `get_or_create(key) -> AgentSession`
  - `update_state(session_id, state) -> None`
  - `touch(session_id, at) -> None`
- 职责：
  - 保存会话状态卡。
  - 记录最近用户/机器人消息时间。
  - 记录摘要 watermark。
- 约束：
  - 按 `(platform, account_id, conversation_type, external_id)` 唯一。
  - 状态卡是投影，可从消息和摘要重建。
  - 不保存他人隐私到全局状态。

### IF-CTX-002 上下文组装器

- 方法草案：
  - `assemble(session, current_message, trigger_reason) -> ContextBundle`
- `ContextBundle` 草案字段：
  - `messages`
  - `manifest`（消息 ID、摘要 ID、记忆 ID）
  - `estimated_tokens`
  - `compaction_needed`
  - `degraded`
- 组装顺序：
  1. 固定指令
  2. 会话状态卡
  3. 历史摘要
  4. 长期记忆
  5. 近期原文
  6. 当前消息
- 约束：
  - 固定指令、当前消息不裁剪。
  - 超预算按记忆、摘要、近期原文顺序裁剪。
  - 结果必须可解释、可审计。

### IF-CTX-003 摘要压缩

- 方法草案：
  - `compact(session_id, range) -> SummaryResult`
- 职责：
  - 保留最近 8～12 轮原文。
  - 把更旧内容压缩为结构化摘要。
  - 更新 `last_summarized_message_id`。
- 约束：
  - 幂等键：`session_id + from_message_id + to_message_id + summary_version`。
  - 单会话压缩锁。
  - 失败不推进 watermark，不删除原文。
  - 额度不足时跳过压缩。

### IF-MEM-001 长期记忆

- 方法草案：
  - `upsert(candidate) -> MemoryItem`
  - `search(scope, query, limit) -> list[MemoryItem]`
  - `list(scope) -> list[MemoryItem]`
  - `delete(memory_id) -> None`
- 作用域：
  - `agent`
  - `contact`
  - `group`
  - `platform_account`
- 约束：
  - 每条记忆必须有来源消息 ID。
  - 默认按会话隔离。
  - 全局记忆不保存他人隐私。
  - 第一版使用 FTS5，不引入向量库。
  - 记忆注入必须标注“不是系统指令”。

### IF-AUD-001 调用审计

- 方法草案：
  - `start_trace(...) -> TraceContext`
  - `start_span(...) -> SpanContext`
  - `finish(...) -> None`
  - `record_event(...) -> None`
- 结构：
  - `trace`：一条入站消息或一次主动任务。
  - `span`：ingress、context、memory、llm、send、compact、extract、budget。
- 默认字段：
  - trace_id、span_id、parent_span_id、turn_id、session_id
  - 平台、账号、会话类型、模型、人设版本
  - 状态、错误码、耗时、重试次数
  - 输入/输出/缓存/推理 token
  - 上下文清单
  - 中转站 request_id、预算快照
- 默认不记录：
  - 消息正文
  - 提示词
  - 回复正文
  - Key、Token、Cookie
- 写入：
  - 异步、有界队列。
  - 失败不影响回复。
  - 成功请求可采样，错误请求全量。

### IF-BUD-001 token 预算

- 方法草案：
  - `get_snapshot() -> BudgetSnapshot`
  - `check(estimated_tokens) -> BudgetDecision`
  - `record_usage(usage) -> None`
- `BudgetSnapshot` 草案：
  - `limit`、`used`、`remaining`
  - `reset_at`
  - `source`、`fresh`、`hard_limit`
- 当前阶段：
  - 先提供本地空实现/本地记账。
  - 不立即硬切断 token 用量。
  - 后续由中转站作为权威来源。
- 约束：
  - `QUOTA_EXHAUSTED` 禁止自动重试。
  - 与回复冷却/频率限制分离。
  - `request_id` 幂等，避免重试重复计数。

### IF-OBS-001 运行状态与健康检查

- 计划接口：
  - `GET /healthz`
  - `GET /status`
- `/healthz`：进程存活、instance_id、版本。
- `/status`：OneBot 连接、数据库健康、今日消息/调用/token、限流/预算拒绝、最近成功/失败、模型、人设版本、预算快照。
- 约束：
  - 默认只绑定 `127.0.0.1`。
  - 不返回密钥、Token、Cookie、聊天正文。
  - JSON 带 `schema_version`。
  - 优先复用 NoneBot FastAPI driver；不支持时再用独立只读端口。

### IF-REL-001 中转站契约

- 计划接口：
  - `GET /v1/budget`
  - `POST /v1/usage`
  - `GET /v1/health`
- 约束：
  - 中转站是硬预算的最终裁决者。
  - 本地预检查不能保证多实例不超。
  - 通过 `request_id` 对账。
  - 业务层只依赖 `BudgetProvider`，不直接解析供应商响应头。

### IF-TOOL-001 工具与 Skill 注册

- 方法草案：
  - `register(tool)`
  - `list_tools(scope)`
  - `invoke(name, arguments, context) -> ToolResult`
- 每个工具必须有：
  - 名称、描述、输入 schema、输出 schema
  - 权限范围
  - 超时
  - 是否允许联网/写操作
  - 审计字段
- 约束：
  - 外部内容不能覆盖系统指令。
  - 高风险工具需要显式权限或人工确认。
  - 所有调用进入审计。

### IF-ADMIN-001 管理后台 API

- 计划能力：
  - 人设版本读取/修改/回滚
  - 配置读取/修改
  - 记忆查看/纠正/删除
  - 会话状态查看
  - 用量和状态查看
- 约束：
  - 认证、权限、操作审计。
  - 不直接操作 NoneBot 事件循环。
  - 第一版只绑定本机。
  - 不在 M5 实现。

## 7. 变更流程

任何接口变更按以下顺序：

1. 判断是否跨边界、是否稳定接口。
2. 更新 `docs/INTERFACES.md` 对应条目。
3. 修改代码和契约测试。
4. 如果涉及数据表，更新 `docs/DATA_MODEL.md` 和迁移。
5. 如果涉及配置，更新 `docs/CONFIGURATION.md` 和 `.env.example`。
6. 如果涉及错误语义，更新 `docs/ERROR_CODES.md`。
7. 如果是难以回滚的决策，新增 ADR。
8. 在变更记录中写明兼容性和迁移路径。

Code Review 只检查四个核心问题：

- 是否跨了模块边界？
- 是否改变了已有契约？
- 是否保持向后兼容？
- 是否有测试、降级和回滚方案？

## 8. 版本记录

- v0.1（2026-10-24）：建立接口清单，登记 M2～M4 当前接口、M5 草案接口、稳定性分级和变更流程。
- v0.2（2026-10-25）：登记 M5A 的消息、上下文、turn、会话和 SQLite v2 契约。
