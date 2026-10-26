# Whale-girl

基于 NapCatQQ + OneBot v11 + NoneBot2 的陪伴型 Agent。当前阶段完成 QQ
私聊 AI、白名单群 AI、出站回复持久化和跨重启上下文，模型使用 DeepSeek 的
OpenAI 兼容接口。

## Architecture

项目是模块化单体。平台接入、应用编排和模型实现相互隔离，后续可以继续增加
其他社交平台、长期记忆、后台和 Skill，而不需要推翻 QQ 连接层。

```text
QQ / future platform
  -> plugins/qq_gateway        NoneBot 薄适配层
  -> application              白名单、回复策略、生成器、限流
  -> ports                    LLM / Context / Limiter / Repository 接口
  -> infrastructure           SQLite、DeepSeek、QQ 事件映射
```

核心目录：

```text
config/persona.toml           唯一鲸鱼娘人设
plugins/qq_gateway/           OneBot v11 接入
src/whale_girl/domain/        无平台 SDK 依赖的领域模型
src/whale_girl/application/   用例、回复生成、上下文与限流
src/whale_girl/ports/         LLM、上下文、存储抽象
src/whale_girl/infrastructure/DeepSeek 与存储实现
src/whale_girl/bootstrap/     配置解析与依赖装配
tests/                        使用 Fake LLM 的自动化测试
scripts/query_messages.py     本地消息查询工具
```

## Documentation

- [架构基线](docs/ARCHITECTURE.md)：分层、模块边界、数据所有权和扩展方式。
- [接口清单](docs/INTERFACES.md)：当前接口、M5 草案接口和稳定性分级。
- [数据模型](docs/DATA_MODEL.md)：SQLite v2、消息、会话和 turn 结构。
- [配置说明](docs/CONFIGURATION.md)：环境变量、默认值和校验规则。
- [错误码与失败行为](docs/ERROR_CODES.md)：异常、重试和用户可见行为。
- [架构决策记录](docs/adr/README.md)：ADR 索引和模板。

## Reply Flow

```text
QQ 私聊 -> OneBot -> NoneBot -> 好友白名单
        -> SQLite 近期上下文 -> 唯一人设 -> DeepSeek
        -> 回复清洗 -> OneBot -> QQ -> 出站消息落库

QQ 群聊 -> OneBot -> NoneBot -> 白名单群观察
        -> 全部群消息写入 SQLite，并按需重建上下文
        -> @ 或唤醒词 -> 群聊限流 -> DeepSeek
        -> 回复清洗 -> OneBot -> QQ -> 出站消息落库
```

- 只有 `QQ_FRIEND_WHITELIST` 中的私聊会调用 AI。
- 白名单群内只有 @ 机器人或命中唤醒词时调用 AI。
- 群内其他普通消息只观察并进入群聊上下文，不调用模型、不发送回复。
- 群聊上下文会带上成员昵称，图片、表情、语音等以占位符表示。
- 非白名单私聊只观察消息，不回复。
- 上下文按平台、账号、会话类型和会话 ID 隔离，并从 SQLite 重建。
- 入站消息和机器人成功回复都持久化到 SQLite，重启后上下文连续。
- 机器人自己发送的消息不会再触发回复，避免自问自答。
- 冷却或频率限制命中时保持沉默；模型失败是否回退固定回复由配置决定。
- 每次成功调用记录模型、耗时和 token，不记录聊天正文或密钥。

## Group AI and Limits

群聊和私聊使用独立的 AI 生成器与独立限流器，但共享同一个 Agent 人设和
LLM Provider。`AIRequestLimiter` 是 `ports/` 中的可替换边界，当前实现
`AIRequestGuard` 只负责会话冷却、每分钟和每日调用上限；后续可以替换为
群级、用户级、token 预算或 Redis 分布式限流，而不改回复生成流程。

```dotenv
AI_GROUP_ENABLED=true
AI_GROUP_FALLBACK_TO_FIXED=false
AI_GROUP_MAX_CONTEXT_MESSAGES=200
AI_GROUP_COOLDOWN_SECONDS=0
AI_GROUP_MAX_CALLS_PER_MINUTE=0
AI_GROUP_MAX_CALLS_PER_DAY=0
```

当前本机把群聊冷却和每分钟/每日调用上限都设为 `0`，因此不会触发这三类限流；限流命中时仍不会回退成固定回复，避免绕过限制刷屏。群聊模型失败默认
保持沉默；需要临时回退时把 `AI_GROUP_FALLBACK_TO_FIXED` 改为 `true`。

## Message Storage

默认数据库路径：

```dotenv
DATABASE_PATH=data/whale_girl.sqlite3
SQLITE_BUSY_TIMEOUT_MS=5000
```

SQLite 保存白名单群消息、私聊消息、机器人成功回复、消息片段、发送者和时间。
同一个平台 `message_id` 不会重复写入；没有平台 ID 的回复使用 `local:<uuid>`。
上下文按内部消息 `id` 排序，平台消息 ID 只用于去重。数据库文件已被
`.gitignore` 忽略。

查看测试群最近 20 条消息：

```powershell
uv run --no-sync python scripts/query_messages.py --group 807913552 --limit 20
```

输出完整结构化记录，包括内部 ID、`origin`、`turn_id`、消息片段和原始事件：

```powershell
uv run --no-sync python scripts/query_messages.py --group 807913552 --limit 20 --json
```

查询私聊：

```powershell
uv run --no-sync python scripts/query_messages.py --friend 3099225100 --limit 20
```

## Setup

```powershell
uv sync --dev
Copy-Item .env.example .env
uv run python bot.py
```

在本地 `.env` 中填写 DeepSeek Key。真实 Key 只放在该文件里，且 `.env`
已被 Git 忽略：

```dotenv
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

`REPLY_MODE=fixed` 可以随时退回固定回复。Key 为空不会阻止 NoneBot 启动；
私聊和群聊会分别按 `AI_FALLBACK_TO_FIXED` 与
`AI_GROUP_FALLBACK_TO_FIXED` 决定是否回退固定回复。

常用配置：

```dotenv
QQ_FRIEND_WHITELIST=["你的测试好友QQ"]
REPLY_MODE=ai
AI_FALLBACK_TO_FIXED=true
AI_MAX_CONTEXT_MESSAGES=120
AI_MAX_CONTEXT_CHARS=10000
AI_MAX_INPUT_CHARS=4000
AI_MAX_REPLY_CHARS=600
AI_MAX_OUTPUT_TOKENS=300
AI_COOLDOWN_SECONDS=0
AI_MAX_CALLS_PER_MINUTE=0
AI_MAX_CALLS_PER_DAY=0
AI_GROUP_ENABLED=true
AI_GROUP_FALLBACK_TO_FIXED=false
AI_GROUP_MAX_CONTEXT_MESSAGES=200
AI_GROUP_COOLDOWN_SECONDS=0
AI_GROUP_MAX_CALLS_PER_MINUTE=0
AI_GROUP_MAX_CALLS_PER_DAY=0
```

`0` 表示不限制该维度；当前本机配置关闭了冷却和每分钟/每日调用上限，但尚未设置每日 token 硬预算。

## Tests

```powershell
uv run --no-sync pytest -q
uv run --no-sync python -m compileall -q src plugins scripts tests bot.py
```

测试不访问真实 DeepSeek API，也不需要 NapCat 在线。

## Notes

- Python 3.12 recommended.
- Default NoneBot port: 8090.
- Do not commit `.env`, API keys, OneBot tokens, QQ credentials, or `_local/`.
- NapCat 属于非官方接入方案，只用于自己的小号和测试群。
