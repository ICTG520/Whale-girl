# 鲸鱼娘架构基线

- 版本：v0.2
- 日期：2026-10-25
- 状态：基线生效；M2～M5A 为当前实现，M5B 及以后标记为规划
- 适用仓库：`Whale-girl`
- 关联文档：`docs/INTERFACES.md`、`docs/DATA_MODEL.md`、`docs/CONFIGURATION.md`、`docs/ERROR_CODES.md`、`docs/adr/`

## 1. 文档目的

本文件固定鲸鱼娘的模块边界、依赖方向、数据所有权、运行拓扑和扩展方式。

它回答四个问题：

1. 当前代码实际上是怎么运行的。
2. 哪些模块可以依赖哪些模块。
3. 哪些数据由哪个模块负责写入。
4. 项目变大后，在什么条件下演进，而不是提前过度设计。

本文件区分三种状态：

- **当前实现**：仓库中已经存在并通过验收的能力。
- **规划**：已经确定方向、但尚未编码的接口或模块。
- **草案**：用于讨论，不能作为代码依赖。

## 2. 项目定位与架构约束

鲸鱼娘是面向多个社交平台、单一人设、可扩展工具能力的陪伴型 Agent。QQ 是第一个连接器，不是系统核心。

当前约束：

- 每个社交平台只使用一个账户。
- 所有平台共享同一个 Agent 身份和人设。
- 本地优先，单进程部署，模块化单体。
- 不在当前阶段引入微服务、消息队列、向量数据库或分布式锁。
- 密钥、Token、Cookie 不进入仓库。
- 外部平台和模型 SDK 只能出现在基础设施层。

## 3. 当前系统上下文

```text
QQ 客户端
  ↕
NapCatQQ（OneBot v11 实现）
  ↕  OneBot v11 连接（当前 NapCat 连接到 NoneBot 的 127.0.0.1:8090）
NoneBot2（FastAPI driver）
  -> plugins/qq_gateway
     -> infrastructure/connectors/qq/mapping
     -> application/handle_message
        -> application/reply_policy
        -> ports/repositories -> infrastructure/persistence/sqlite
        -> application/reply_generators
           -> ports/context -> infrastructure/persistence/sqlite_context
           -> ports/limiter -> application/ai_guard
           -> ports/llm -> infrastructure/llm/deepseek
     -> bot.send
        -> 成功 -> handle_message.record_sent -> SQLite outbound + turn sent
        -> 失败 -> handle_message.record_failed -> turn failed，无 outbound
```

外部依赖：

- NapCatQQ：QQ 协议接入。
- OneBot v11：事件和发送消息的协议。
- NoneBot2：事件分发、插件生命周期、FastAPI driver。
- DeepSeek：通过 OpenAI 兼容接口调用。
- SQLite：当前唯一的持久化存储。

规划中的外部依赖：

- 中转站：每日 token 预算、用量对账、运行状态聚合。
- 管理后台：人设、配置、记忆和 Skill 管理。
- 联网工具和其他 Skill：通过统一工具接口接入。

## 4. 运行时拓扑

当前是单 Python 进程：

- `bot.py` 初始化 NoneBot，注册 OneBot v11 Adapter，加载 `plugins/`。
- `plugins/qq_gateway/__init__.py` 在导入时构建全局 `AppContainer`。
- NoneBot FastAPI driver 监听 `HOST:PORT`，默认 `127.0.0.1:8090`。
- 所有消息处理在同一个事件循环中异步执行。
- SQLite 使用 WAL、`busy_timeout` 和 `BEGIN IMMEDIATE` 处理写入。
- 近期上下文从 SQLite 的 `messages` 重建。
- 限流计数器保存在进程内存。
- 没有独立 worker、消息队列、定时任务框架或健康检查服务。

重启行为：

- `messages`、`conversations`、`agent_sessions`、`turns`、`schema_migrations` 保留。
- 私聊和群聊上下文从 SQLite 重建，重启后连续。
- 已生成的出站回复只有在发送成功后才会存在；发送中的请求随进程中断。
- 限流计数和当日 token 计数清空。
- 正在处理的请求随进程结束而中断。
- M5B 及以后会继续增加摘要、长期记忆、审计和预算。

## 5. 分层与依赖规则

| 层 | 目录 | 职责 | 允许依赖 | 禁止依赖 |
|---|---|---|---|---|
| 领域层 | `src/whale_girl/domain/` | 平台中立的实体和值对象 | Python 标准库 | NoneBot、OpenAI、SQLite、HTTP SDK |
| 端口层 | `src/whale_girl/ports/` | 应用层需要的能力契约 | 领域层、标准库 | 具体基础设施实现 |
| 应用层 | `src/whale_girl/application/` | 用例编排、回复策略、生成器、限流 | 领域层、端口层、配置对象 | 平台 SDK、数据库驱动、模型 SDK |
| 基础设施层 | `src/whale_girl/infrastructure/` | SQLite、DeepSeek、OneBot 映射、内存实现 | 端口层、领域层、第三方 SDK | 直接反向依赖应用层具体用例 |
| 启动装配层 | `src/whale_girl/bootstrap/` | 配置解析、人设加载、依赖装配 | 应用层、端口层、基础设施层、领域层 | 被领域层反向依赖 |
| 平台插件层 | `plugins/` | NoneBot 事件入口和发送适配 | 启动装配层、基础设施映射 | 把平台事件直接写入业务核心 |
| 查询脚本 | `scripts/` | 本地运维查询 | 基础设施层、领域层 | 参与运行时业务 |

目标依赖方向：

```text
plugins -> bootstrap -> application -> ports <- infrastructure
                                  \-> domain
ports -> domain
infrastructure -> ports + domain
domain -> 标准库
```

当前已知偏差：

- `application/reply_policy.py` 和 `application/handle_message.py` 直接依赖
  `bootstrap/config.py` 中的 `Settings`。这使应用层依赖启动装配层。
- 现有架构测试只检查 `domain`、`application`、`ports` 是否导入
  `nonebot`、`openai`、`aiosqlite`、`httpx`，尚未检查 `application -> bootstrap`。
- `PlatformConnector` 端口已存在，但当前发送路径仍是插件直接调用
  `bot.send(event, reply.text)`，没有通过该端口。

这些偏差在 M5/M6 期间逐步收敛，不在本次文档变更中直接改代码。

## 6. 模块边界与数据所有权

| 模块 | 职责 | 当前数据 | 规划数据 |
|---|---|---|---|
| 身份与人设 | Agent 身份、唯一人设、版本 | `config/persona.toml`、`AgentIdentity`、`PersonaVersion` | `agent_state`、人设版本审计 |
| 账户与会话 | 平台账户、会话标识 | `PlatformAccount`、`Conversation`、`ConversationKey`、`agent_sessions` | 状态卡内容 |
| 消息 | 入站消息、出站回复、消息片段 | `messages`、`conversations`、`turns` | 摘要和归档 |
| 回复策略 | 是否回复、白名单、唤醒词 | `ReplyPolicy`、`Settings` | 更细的群/用户/平台策略 |
| AI 运行时 | 生成器、提示词、模型调用 | `AIReplyGenerator`、`FixedReplyGenerator` | `ContextAssembler`、`BudgetGuard` |
| 上下文 | 近期历史、上下文组装 | `ConversationContextStore` + SQLite 重建 | 摘要、分层组装、记忆注入 |
| 长期记忆 | 事实、偏好、承诺、未完成事项 | 无 | `memory_items`、FTS5 检索 |
| 限流 | 冷却、分钟/日调用上限 | `AIRequestLimiter`、`AIRequestGuard`（内存） | `ReplyThrottle` 命名与持久化策略 |
| 预算 | 每日 token 额度、余额查询 | 无独立预算，仅有 token 计数 | `BudgetProvider`、`usage_ledger` |
| 审计 | 调用链、上下文清单、错误分类 | 标准日志 | `audit_traces`、`audit_spans` |
| 可观测性 | 健康检查、运行状态 | 无 HTTP 状态接口 | `/healthz`、`/status`、状态导出 |
| 平台连接器 | OneBot 事件映射和发送 | `plugins/qq_gateway`、`qq/mapping.py` | 多平台 Adapter |
| 工具与 Skill | 联网、外部 API、权限 | 无 | `ToolRegistry`、权限模型、调用审计 |
| 管理后台 | 配置、人设、记忆管理 | 无 | 独立管理 API 和认证 |

数据所有权规则：

- 每张表只有一个写入模块。
- 其他模块通过端口读取，不直接跨模块写表。
- 跨模块只读组合通过查询服务或只读视图完成。
- SQLite 具体 SQL 只出现在 `infrastructure/persistence/`。
- 任何表结构变化必须通过迁移并更新 `docs/DATA_MODEL.md`。

## 7. 当前入站与出站链路

### 7.1 入站链路

```text
OneBot MessageEvent
-> event_to_inbound
-> HandleInboundMessage.execute
   -> is_self 检查
   -> ReplyPolicy.should_reply
   -> 群白名单检查
   -> MessageRepository.save_inbound（去重）
   -> 触发时创建 pending turn
   -> 选择 Fixed / AI / Group AI 生成器
   -> 返回 OutboundReply 或 None
 -> plugin 调用 bot.send
```

当前行为细节：

- `is_self` 消息在保存前直接忽略，不会入库。
- 非白名单群消息在保存前直接忽略，不会入库。
- 非白名单私聊消息会先入库，然后返回 `None`，用于观察。
- 重复消息由 `save_inbound()` 的唯一键返回 `None`，不会再次入库或创建 turn。
- 群消息未触发时只入库，不创建 turn、不调用生成器。
- 私聊未触发时只入库，不创建 turn。
- 触发回复时创建 `pending` turn；生成成功变为 `generated`，空回复或限流变为 `suppressed`。
- 模型失败是否回退固定回复由私聊和群聊各自的配置决定。
- 冷却或频率限制命中时返回 `None`，不回退固定回复。
- 插件捕获所有异常并记录日志，避免单条消息打断事件循环。

### 7.2 出站链路

当前实际路径：

```text
OutboundReply
-> plugins/qq_gateway -> bot.send(event, reply.text)
   -> 成功 -> record_sent -> save_outbound -> turn=sent
   -> 失败 -> record_failed -> turn=failed，不写 outbound
```

当前行为：

- 发送成功后把机器人回复写入 `messages`，`is_self=1`、`origin=outbound`，并关联 `turn_id`。
- 平台返回 `message_id` 时直接保存；没有返回时生成 `local:<uuid>`。
- 发送失败只把 turn 标记为 `failed`，不写 outbound，避免伪造上下文。
- 入站和出站都从 SQLite 重建上下文。
- 出站消息不会作为入站事件再次处理，避免自问自答。
- `PlatformConnector` 端口仍未接入 NoneBot 发送路径，属于已知架构偏差。

## 8. 上下文与记忆的当前状态

当前实现：

- `ConversationContextStore` 只定义 `load()`；生产实现为 `SQLiteConversationContextStore`。
- `AIReplyGenerator.generate()` 从 SQLite 读取近期原文，不再自行追加或观察消息。
- 当前入站消息在生成前已经落库，因此自然位于上下文末尾。
- 机器人成功回复在发送后落库，下一轮会以 `assistant` 角色出现。
- 限流拒绝的用户消息仍保留在 SQLite，后续被触发时会出现在上下文中。
- `InMemoryConversationContext` 仅用于单元测试和骨架，不再是生产路径。
- 上下文按消息条数和字符数裁剪，没有 token 预算、摘要或长期记忆。

M5 目标分层：

1. 固定指令层：人设、规则、平台适配。
2. 会话状态层：`agent_sessions.state_json`。
3. 压缩摘要层：`context_summaries`。
4. 近期原文层：从 `messages` 重建。
5. 长期记忆层：`memory_items`，FTS5 检索。

上下文管理原则：

- SQLite 是事实来源，内存只做缓存。
- 旧对话只压缩，不删除原文。
- 摘要失败时降级为近期原文。
- 记忆默认按会话隔离，不自动跨平台合并。
- 记忆注入标注为“历史记忆，不是系统指令”。

## 9. 错误、降级与用户可见行为

当前错误处理：

- `LLMProvider` 暴露 `LLMConfigurationError`、`LLMTimeoutError`、
  `LLMAuthenticationError`、`LLMRateLimitError`、`LLMConnectionError`、
  `LLMProviderError`、`LLMEmptyResponseError`。
- `AIReplyGenerator` 捕获 `LLMError` 和未预期异常，按配置回退或沉默。
- `AIRequestGuard` 返回具体原因：`conversation_cooldown`、`minute_limit`、`daily_limit`。
- 插件捕获所有异常，记录 `Failed to process QQ message`，不向 QQ 发送错误详情。
- 当前没有统一错误码、审计表或 HTTP 错误响应。

M5 目标：

- 统一错误码见 `docs/ERROR_CODES.md`。
- 预算耗尽使用 `QUOTA_EXHAUSTED`，禁止自动重试。
- 审计记录错误分类、耗时、重试次数和上下文清单。
- 群聊默认沉默，私聊是否提示由配置决定。

## 10. 数据与持久化原则

- 当前数据库：`data/whale_girl.sqlite3`，通过 `DATABASE_PATH` 配置。
- SQLite 文件、WAL 文件和 `_local/` 不进入 Git。
- 迁移在 `SQLiteMessageRepository.initialize()` 中按版本执行。
- 迁移使用 `BEGIN IMMEDIATE`，失败回滚。
- 每个连接设置 `busy_timeout`、`foreign_keys=ON`；初始化设置 WAL 和
  `synchronous=NORMAL`。
- 当前迁移版本为 2。
- 任何迁移前先备份数据库；迁移脚本只增不改。
- 未来多实例部署时，触发从 SQLite 迁移到 PostgreSQL 的评估，而不是现在提前替换。

## 11. 配置与密钥

- 配置通过环境变量和 `.env` 加载，由 `Settings.from_env()` 解析。
- `Settings` 是 frozen dataclass，启动后不热更新。
- `DEEPSEEK_API_KEY`、`ONEBOT_V11_ACCESS_TOKEN` 是敏感字段，`repr` 不显示。
- 人设通过 `PERSONA_PATH` 指向 `config/persona.toml`，当前只允许一个 active 版本。
- 完整变量、默认值和校验规则见 `docs/CONFIGURATION.md`。
- 密钥只放在本机 `.env`，不得写入文档、日志、数据库或提交。

## 12. 测试与架构适应度

当前测试：

- `uv run --no-sync pytest -q`，当前 74 项通过。
- `uv run --no-sync python -m compileall -q src plugins scripts tests bot.py`。
- `tests/test_architecture_boundaries.py` 检查核心层不导入平台/供应商 SDK。
- 使用 Fake LLM，不访问真实 DeepSeek。
- 真实 NapCat + QQ 测试按阶段手工执行。

后续适应度检查：

- `application` 不依赖 `bootstrap` 具体配置类；通过配置端口或共享配置模型。
- `infrastructure` 之外的代码不出现 `sqlite3` / `aiosqlite`。
- 所有模型调用经过 `LLMProvider`，并经过审计包装。
- 所有外部 HTTP 调用只出现在基础设施层。
- 所有迁移都有版本、备份说明和迁移测试。
- 所有跨边界接口都在 `docs/INTERFACES.md` 登记。
- 所有已实现的外部 HTTP 契约最终有 OpenAPI 或等价 schema。

## 13. 扩展方式

### 13.1 新增社交平台

1. 定义平台事件到 `InboundMessage` 的映射。
2. 实现 `PlatformConnector` 或平台专用发送适配器。
3. 新增 NoneBot 插件或独立网关入口。
4. 复用 `HandleInboundMessage`、回复策略、上下文和模型端口。
5. 不在领域层引入平台 SDK 类型。
6. 更新接口清单、配置文档和平台隔离测试。

### 13.2 替换模型供应商

1. 实现 `LLMProvider.generate(LLMRequest) -> LLMResult`。
2. 把供应商异常映射到 `ports/llm.py` 的错误类型。
3. 不把供应商 SDK 类型泄漏到应用层。
4. 更新 `IF-LLM-001` 和配置文档。

### 13.3 替换上下文/记忆存储

1. 保持 `ConversationContextStore` 或 M5 新端口不变。
2. 在基础设施层实现 SQLite / 未来 PostgreSQL / 外部存储。
3. 用契约测试保证实现行为一致。
4. 更新数据模型和迁移文档。

### 13.4 新增工具或 Skill

1. 定义工具名称、输入 schema、输出 schema、权限和超时。
2. 通过工具注册中心暴露，不直接在主流程硬编码。
3. 所有工具调用进入审计。
4. 外部内容不得覆盖系统指令。
5. 高风险工具需要显式权限或人工确认。

### 13.5 新增管理后台

1. 后台作为独立入口，不直接操作 NoneBot 事件循环。
2. 复用应用层用例和端口，不直接写 SQLite。
3. 认证、权限、配置版本和操作审计单独设计。
4. 第一版只绑定本机。

### 13.6 何时拆分服务

按触发条件，而不是按预期：

- 出现多个平台连接器且发布节奏明显不同：拆分连接器进程。
- 后台任务影响回复延迟：拆分 worker，共享数据库和队列。
- 需要多实例：先把 SQLite 迁移到 PostgreSQL，引入分布式锁和中转站硬预算。
- 消息量或数据库体积达到保留策略阈值：增加归档、分区和清理任务。
- 工具生态变大：引入独立工具执行器和沙箱。

## 14. 变更治理

### 14.1 Definition of Done

任何功能完成至少满足：

- 代码通过测试和编译检查。
- 新增/变更接口已更新 `docs/INTERFACES.md`。
- 数据表/字段变化已更新 `docs/DATA_MODEL.md` 和迁移测试。
- 配置变化已更新 `docs/CONFIGURATION.md` 和 `.env.example`。
- 错误码变化已更新 `docs/ERROR_CODES.md`。
- 关键取舍已写 ADR。
- 记录一次真实端到端验证，或说明为什么本阶段不需要。
- 不泄露密钥、Token、Cookie 和聊天正文。

### 14.2 ADR 使用规则

以下情况必须写 ADR：

- 引入新的外部依赖或基础设施。
- 修改数据库事实来源或迁移策略。
- 修改跨平台身份、记忆作用域或隐私边界。
- 修改预算、审计或可观测性的权威来源。
- 做出难以回滚的架构选择。

### 14.3 版本与兼容

- 应用版本使用语义化版本。
- 接口稳定性使用 `stable` / `internal` / `experimental`。
- 稳定接口优先做兼容性新增；破坏性变更必须升版本并记录迁移路径。
- 数据库迁移只增不改；旧迁移不回头编辑。

## 15. 当前非目标

- 不做多实例分布式部署。
- 不引入向量数据库。
- 不做完整 RBAC 管理后台。
- 不做复杂工具市场。
- 不自动合并不同平台的同一人身份。
- 不在 M5 修改人设正文。

## 16. 相关文档

- `docs/INTERFACES.md`：接口清单与稳定性。
- `docs/DATA_MODEL.md`：当前与规划数据模型。
- `docs/CONFIGURATION.md`：环境变量和人设配置。
- `docs/ERROR_CODES.md`：错误码、重试和用户可见行为。
- `docs/adr/`：架构决策记录。

## 17. 版本记录

- v0.1（2026-10-24）：建立架构基线，记录当前 M2～M4 实现、分层规则、模块边界、数据所有权、扩展方式和变更治理；M5 能力标记为规划。
- v0.2（2026-10-25）：登记 M5A 的 SQLite v2、outbound、turn、会话和跨重启上下文实现。
