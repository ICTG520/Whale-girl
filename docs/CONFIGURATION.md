# 鲸鱼娘配置基线

- 版本：v0.1
- 日期：2026-10-24
- 状态：当前变量已实现；M5 变量为草案
- 关联文档：`docs/ARCHITECTURE.md`、`docs/INTERFACES.md`、`docs/ERROR_CODES.md`

## 1. 配置来源与加载时机

当前配置分为两部分：

1. NoneBot 自身读取的环境变量：`DRIVER`、`HOST`、`PORT`、`LOG_LEVEL`、`COMMAND_START`、`NICKNAME`、`ONEBOT_V11_ACCESS_TOKEN` 等。
2. 应用通过 `Settings.from_env()` 读取的环境变量：白名单、模型、回复策略、群聊策略、数据库路径等。

加载规则：

- `Settings.from_env()` 未传入 mapping 时，会调用 `python-dotenv` 的 `load_dotenv()`，再读取 `os.environ`。
- 进程环境变量优先级高于 `.env` 中的同名值（`load_dotenv()` 默认不覆盖已有环境变量）。
- `Settings` 是 frozen dataclass，启动后不热更新。
- 修改配置后需要重启进程。
- `.env` 不进入 Git；只保留 `.env.example`。
- 当前没有统一的配置中心或远程配置。

## 2. 敏感字段

以下字段不得出现在日志、文档、截图、提交或聊天中：

- `DEEPSEEK_API_KEY`
- `ONEBOT_V11_ACCESS_TOKEN`

保护措施：

- `Settings` 对这两个字段使用 `repr=False`。
- DeepSeek 失败日志只记录异常类别，不记录 Key。
- 文档和示例只使用占位符。
- 如果怀疑泄露，立即在供应商和 NapCat 侧轮换。

## 3. NoneBot / OneBot 变量

| 变量 | 默认值 | 类型 | 说明 |
|---|---|---|---|
| `DRIVER` | `~fastapi` | string | NoneBot driver |
| `HOST` | `127.0.0.1` | string | NoneBot 监听地址 |
| `PORT` | `8090` | int | NoneBot 监听端口；应用也会校验 1..65535 |
| `LOG_LEVEL` | `INFO` | string | 日志级别 |
| `COMMAND_START` | `["/"]` | JSON array | NoneBot 命令前缀 |
| `NICKNAME` | `["鲸鱼娘"]` | JSON array | NoneBot 昵称 |
| `ONEBOT_V11_ACCESS_TOKEN` | 空 | string，敏感 | OneBot 连接 Token，必须与 NapCat 配置一致 |

注意：

- `HOST`、`PORT`、`ONEBOT_V11_ACCESS_TOKEN` 同时被 NoneBot 和应用配置读取；当前没有单一配置源。
- 默认只监听本机。不要在没有认证和防火墙的情况下改为公网地址。

## 4. 应用基础变量

| 变量 | 默认值 | 类型 | 校验/说明 |
|---|---|---|---|
| `AGENT_NAME` | `鲸鱼娘` | string | 用于固定回复和展示 |
| `QQ_GROUP_WHITELIST` | 空 | JSON array 或 CSV | 白名单群号集合 |
| `QQ_FRIEND_WHITELIST` | 空 | JSON array 或 CSV | 白名单好友 QQ 集合 |
| `WAKE_WORDS` | `["鲸鱼娘"]` | JSON array 或 CSV | 群聊唤醒词；大小写不敏感子串匹配 |
| `OBSERVE_ALL_GROUP_MESSAGES` | `true` | bool | 是否观察白名单群的普通消息 |
| `REPLY_ENABLED` | `true` | bool | 全局回复开关；关闭后仍可观察/入库 |
| `REPLY_MODE` | `ai` | enum | `ai` / `fixed` |

列表解析：

- 以 `[` 开头时按 JSON 数组解析。
- 否则按逗号分隔。
- 空值回退默认值。
- 结果去空白、去空项。
- 群号和好友号按字符串保存，避免整数精度和前导零问题。

## 5. DeepSeek 变量

| 变量 | 默认值 | 类型 | 说明 |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | 空 | string，敏感 | DeepSeek API Key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | string | 末尾斜杠会被去掉 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | string | 模型名 |

行为：

- Key 为空不会阻止 NoneBot 启动。
- `REPLY_MODE=ai` 且 Key 为空时，容器会记录警告。
- 私聊和群聊分别按回退配置决定是否使用固定回复。

## 6. 私聊 AI 与通用回复变量

| 变量 | 默认值 | 类型 | 范围/说明 |
|---|---|---|---|
| `AI_FALLBACK_TO_FIXED` | `true` | bool | 私聊模型失败是否回退固定回复 |
| `AI_MAX_CONTEXT_MESSAGES` | `12` | int | 1..1000，私聊上下文最大条数 |
| `AI_MAX_CONTEXT_CHARS` | `6000` | int | 100..100000，上下文最大字符数 |
| `AI_MAX_INPUT_CHARS` | `2000` | int | 100..100000，单条输入截断 |
| `AI_MAX_REPLY_CHARS` | `600` | int | 20..10000，输出截断 |
| `AI_MAX_OUTPUT_TOKENS` | `300` | int | 1..8192 |
| `AI_TEMPERATURE` | `0.8` | float | 0.0..2.0 |
| `AI_TIMEOUT_SECONDS` | `30` | float | 1..300 |
| `AI_MAX_RETRIES` | `1` | int | 0..5，传给 OpenAI 客户端 |
| `AI_COOLDOWN_SECONDS` | `2` | float | 0..300，私聊会话冷却 |
| `AI_MAX_CALLS_PER_MINUTE` | `10` | int | 0..1000，0 表示不限制每分钟调用 |
| `AI_MAX_CALLS_PER_DAY` | `200` | int | 0..100000，0 表示不限制每日调用 |

说明：

- `AI_MAX_CONTEXT_CHARS` 同时用于群聊生成器的字符预算；群聊没有单独的 `AI_GROUP_MAX_CONTEXT_CHARS`。
- 限流计数当前是进程内存，重启清零。
- `AI_MAX_CALLS_PER_MINUTE=0` 和 `AI_MAX_CALLS_PER_DAY=0` 都表示不限制调用次数；不代表 token 预算无限。`AI_COOLDOWN_SECONDS=0` 表示关闭冷却。

## 7. 群聊 AI 变量

| 变量 | 默认值 | 类型 | 范围/说明 |
|---|---|---|---|
| `AI_GROUP_ENABLED` | `true` | bool | 是否创建群聊 AI 生成器 |
| `AI_GROUP_FALLBACK_TO_FIXED` | `false` | bool | 群聊模型失败是否回退固定回复 |
| `AI_GROUP_MAX_CONTEXT_MESSAGES` | `20` | int | 1..1000 |
| `AI_GROUP_COOLDOWN_SECONDS` | `30` | float | 0..3600，群级冷却 |
| `AI_GROUP_MAX_CALLS_PER_MINUTE` | `6` | int | 0..1000，0 表示不限制每分钟调用 |
| `AI_GROUP_MAX_CALLS_PER_DAY` | `100` | int | 0..100000，0 表示不限制每日调用 |

行为：

- 群聊只使用 `AI_GROUP_*` 的冷却和调用上限。
- 私聊和群聊共享同一个 `LLMProvider` 和人设，但使用独立生成器和独立限流器。
- 群聊模型失败默认沉默，避免刷屏。
- 冷却/限流命中时不回退固定回复。

## 8. 人设与数据库变量

| 变量 | 默认值 | 类型 | 说明 |
|---|---|---|---|
| `PERSONA_PATH` | `config/persona.toml` | string | 人设文件路径 |
| `DATABASE_PATH` | `data/whale_girl.sqlite3` | string | SQLite 文件路径 |
| `SQLITE_BUSY_TIMEOUT_MS` | `5000` | int | 100..60000 |

相对路径解析：

- `PERSONA_PATH` 和 `DATABASE_PATH` 相对项目根目录解析。
- 项目根目录由 `bootstrap/container.py` 向上定位。

### 8.1 当前本机运行值（2026-10-24）

本机 `.env` 目前使用以下放宽值。它们不是代码默认值；新建环境仍以代码默认值和 `.env.example` 为准。

| 变量 | 当前运行值 |
|---|---:|
| `AI_MAX_OUTPUT_TOKENS` | `300` |
| `AI_MAX_REPLY_CHARS` | `600` |
| `AI_MAX_INPUT_CHARS` | `4000` |
| `AI_MAX_CONTEXT_CHARS` | `10000` |
| `AI_MAX_CONTEXT_MESSAGES` | `120` |
| `AI_GROUP_MAX_CONTEXT_MESSAGES` | `200` |
| `AI_COOLDOWN_SECONDS` | `0`（关闭冷却） |
| `AI_MAX_CALLS_PER_MINUTE` | `0`（不限） |
| `AI_MAX_CALLS_PER_DAY` | `0`（不限） |
| `AI_GROUP_COOLDOWN_SECONDS` | `0`（关闭冷却） |
| `AI_GROUP_MAX_CALLS_PER_MINUTE` | `0`（不限） |
| `AI_GROUP_MAX_CALLS_PER_DAY` | `0`（不限） |

这组配置会移除应用层的防刷屏限流。群聊仍然只在被 @ 或命中唤醒词时调用模型，但不再有冷却和调用次数上限；私聊白名单消息会直接调用模型。

## 9. persona.toml 格式

当前人设文件只允许一个 active 版本。

```toml
version = 1
name = "角色名"
system_prompt = """
这里是唯一的系统人设提示词。
"""
active = true
```

校验：

- `version` 必须是 >= 1 的整数。
- `name` 非空。
- `system_prompt` 非空。
- `active` 必须为 true。
- 文件缺失、TOML 解析失败或字段不完整会抛出 `PersonaConfigError`。
- 当前不热更新；修改后重启生效。
- 不要把人设正文写入日志或审计正文。

## 10. 配置变更流程

1. 修改 `bootstrap/config.py` 的字段和校验。
2. 更新 `.env.example`。
3. 更新本文档。
4. 如果影响行为契约，更新 `docs/INTERFACES.md`。
5. 如果影响错误语义，更新 `docs/ERROR_CODES.md`。
6. 补配置解析测试。
7. 不把真实密钥写入任何示例或测试。

## 11. M5 规划变量（草案，未实现）

以下变量只作为设计占位，当前代码不读取：

| 变量 | 建议默认值 | 用途 |
|---|---|---|
| `CONTEXT_MAX_INPUT_TOKENS` | 待定 | 单次上下文输入预算 |
| `CONTEXT_RECENT_MESSAGES_PRIVATE` | `12` | 私聊近期原文条数 |
| `CONTEXT_RECENT_MESSAGES_GROUP` | `20` | 群聊近期原文条数 |
| `CONTEXT_COMPACT_THRESHOLD` | `0.75` | 触发压缩的窗口比例 |
| `CONTEXT_KEEP_RECENT_TURNS` | `10` | 压缩后保留的近期轮数 |
| `SUMMARY_ENABLED` | `true` | 是否启用摘要 |
| `MEMORY_ENABLED` | `true` | 是否启用长期记忆 |
| `MEMORY_TOP_K` | `6` | 召回记忆条数 |
| `AUDIT_ENABLED` | `true` | 是否写审计 |
| `AUDIT_SAMPLE_RATE` | `0.1` | 成功请求采样率 |
| `AUDIT_RETENTION_DAYS` | `30` | 明细保留期 |
| `BUDGET_DAILY_TOKENS` | `10000000` | 每日 token 上限示例 |
| `BUDGET_HARD_LIMIT` | `false` | 当前是否硬切断 |
| `RELAY_BASE_URL` | 空 | 中转站地址 |
| `RELAY_TIMEOUT_SECONDS` | `5` | 中转站超时 |
| `STATUS_HOST` | `127.0.0.1` | 状态接口地址 |
| `STATUS_PORT` | `8091` | 状态接口端口（仅在独立服务时使用） |

这些变量在 M5 审批并实现前，不应出现在运行配置中作为已生效选项。

## 12. 版本记录

- v0.1（2026-10-24）：记录当前 NoneBot、应用、DeepSeek、私聊/群聊、人设和 SQLite 配置；M5 变量标记为草案。