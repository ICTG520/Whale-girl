# 鲸鱼娘数据模型

- 版本：v0.2
- 日期：2026-10-25
- 状态：SQLite 迁移 v2 已实现（M5A）；M5B 及以后表仍为规划
- 数据库：`data/whale_girl.sqlite3`（由 `DATABASE_PATH` 配置）
- 关联文档：`docs/ARCHITECTURE.md`、`docs/INTERFACES.md`、`docs/CONFIGURATION.md`

## 1. 概览

SQLite 是消息与会话的事实来源。当前迁移版本为 2，包含：

- `schema_migrations`
- `conversations`
- `messages`
- `agent_sessions`
- `turns`

M5A 已实现：

- 入站消息持久化与去重。
- 机器人成功回复写入 `messages`。
- 入站消息与出站回复通过 `turn_id` 和 `turns` 归组。
- 私聊、群聊近期上下文从 `messages` 重建。
- 进程重启后上下文连续。
- 机器人自己的消息不会再次触发回复。

当前仍未实现：

- 摘要压缩表 `context_summaries`。
- 长期记忆表 `memory_items`。
- 调用审计表 `audit_traces` / `audit_spans`。
- token 用量账本。
- 自动清理、归档和导出任务。

## 2. SQLite 运行参数

初始化时：

- `PRAGMA journal_mode=WAL`
- `PRAGMA synchronous=NORMAL`
- `PRAGMA busy_timeout=<SQLITE_BUSY_TIMEOUT_MS>`

每个连接：

- `PRAGMA busy_timeout=<SQLITE_BUSY_TIMEOUT_MS>`
- `PRAGMA foreign_keys=ON`

写入规则：

- 写事务使用 `BEGIN IMMEDIATE`。
- 迁移失败会回滚整个版本。
- `initialize()` 幂等，并通过 `schema_migrations` 跳过已应用版本。
- 当前是单进程，但仍按单写入者设计。

## 3. schema_migrations

```sql
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
```

- 每个成功迁移写入一行。
- `applied_at` 为 UTC ISO 8601 字符串。
- 迁移版本只增不减；已发布迁移不原地修改。
- 当前版本记录为 `1`、`2`。

## 4. conversations

```sql
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    account_id TEXT NOT NULL,
    conversation_type TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE (platform, account_id, conversation_type, external_id)
);
```

字段语义：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER | 内部会话引用 ID |
| `platform` | TEXT | 平台标识，当前为 `qq` |
| `account_id` | TEXT | 机器人账号 ID |
| `conversation_type` | TEXT | `group` / `private` |
| `external_id` | TEXT | 群号或好友 QQ |
| `title` | TEXT | 私聊为发送者显示名；群聊当前为 NULL |
| `first_seen_at` | TEXT | 首次写入消息的事件时间 |
| `last_seen_at` | TEXT | 最近一次写入消息或成功回复的时间 |

唯一键：

```text
(platform, account_id, conversation_type, external_id)
```

`conversations` 表达平台外部会话身份。`agent_sessions` 必须通过
`conversation_ref_id` 与它一对一关联。

## 5. messages

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    account_id TEXT NOT NULL,
    conversation_type TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    sender_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    text TEXT NOT NULL,
    parts_json TEXT NOT NULL,
    raw_event_json TEXT NOT NULL,
    is_to_me INTEGER NOT NULL DEFAULT 0,
    is_self INTEGER NOT NULL DEFAULT 0,
    reply_to_message_id TEXT,
    origin TEXT NOT NULL DEFAULT 'inbound',
    turn_id TEXT,
    conversation_ref_id INTEGER,
    UNIQUE (platform, account_id, message_id)
);
```

字段语义：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER | 内部消息 ID；消息顺序和水位的唯一依据 |
| `platform` | TEXT | 平台标识，当前为 `qq` |
| `account_id` | TEXT | 机器人账号 ID |
| `conversation_type` | TEXT | `group` / `private` |
| `conversation_id` | TEXT | 群号或好友 QQ |
| `message_id` | TEXT | 平台消息 ID；无平台 ID 的出站消息使用 `local:<uuid>` |
| `sender_id` | TEXT | 发送者 QQ；出站消息为机器人账号 ID |
| `sender_name` | TEXT | 群名片 / 昵称 / QQ 兜底；出站消息为 Agent 名称 |
| `timestamp` | TEXT | 事件时间或发送成功时间的 UTC ISO 8601 字符串 |
| `text` | TEXT | 只包含文本片段拼接结果 |
| `parts_json` | TEXT | 消息片段数组 JSON |
| `raw_event_json` | TEXT | OneBot 原始事件 JSON；出站消息为 `{}` |
| `is_to_me` | INTEGER | 是否 @ 机器人或私聊触发，0/1 |
| `is_self` | INTEGER | 是否 Agent 自己发送，0/1 |
| `reply_to_message_id` | TEXT | 引用的平台消息 ID，可空 |
| `origin` | TEXT | `inbound` / `outbound` / `system` |
| `turn_id` | TEXT | 该消息所属回复轮次，可空 |
| `conversation_ref_id` | INTEGER | 指向 `conversations.id`，新数据必须写入 |

### 5.1 消息来源

`origin` 语义：

- `inbound`：来自平台或测试的入站消息。
- `outbound`：机器人发送成功后写入的回复。
- `system`：未来由系统生成、需要进入日志但不参与普通上下文的消息。

出站消息必须满足：

- `is_self=1`
- `origin='outbound'`
- `sender_id=account_id`
- 写入时机在平台发送成功之后

发送失败时不写 outbound 消息，也不伪造成功上下文。

### 5.2 去重与顺序

- 平台消息按 `(platform, account_id, message_id)` 去重。
- 平台 `message_id` 只用于去重和关联，不用于排序。
- 上下文和水位统一按内部 `messages.id ASC` 排序。
- 平台不返回消息 ID 时，出站消息使用 `local:<uuid>` 作为内部唯一 ID。

### 5.3 消息片段

`parts_json` 形状：

```json
[
  {"type": "text", "data": {"text": "你好"}},
  {"type": "image", "data": {"file": "..."}}
]
```

上下文渲染规则：

- `text` 原样拼接。
- 图片、表情、语音、视频、文件、@、引用和卡片使用占位符。
- 群聊中其他成员的消息渲染为 `昵称: 内容`。
- 机器人自己的消息不增加昵称前缀。

### 5.4 隐私

- `raw_event_json` 可能包含消息正文、昵称、群号、图片地址等敏感信息。
- 只允许本地存储，不进入审计正文，不导出到外部服务。
- 数据库文件被 `.gitignore` 忽略。

## 6. agent_sessions

```sql
CREATE TABLE agent_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_ref_id INTEGER NOT NULL UNIQUE
        REFERENCES conversations(id) ON DELETE CASCADE,
    state_json TEXT NOT NULL DEFAULT '{}',
    state_version INTEGER NOT NULL DEFAULT 1,
    last_summarized_message_id INTEGER,
    last_user_message_at TEXT,
    last_agent_message_at TEXT,
    last_seen_message_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

语义：

- 一个平台会话对应一个 `agent_session`。
- `state_json` 为 M5B 的状态卡预留；M5A 只写入空对象。
- `last_user_message_at` 在入站消息成功写入后更新。
- `last_agent_message_at` 在成功回复写入后更新。
- `last_seen_message_id` 指向最近的内部消息 ID，不使用平台消息 ID。
- `last_summarized_message_id` 为 M5B 摘要水位预留。
- 由 `MessageRepository` 维护，应用层不直接写表。

## 7. turns

```sql
CREATE TABLE turns (
    id TEXT PRIMARY KEY,
    session_id INTEGER NOT NULL
        REFERENCES agent_sessions(id) ON DELETE CASCADE,
    inbound_message_id INTEGER NOT NULL UNIQUE
        REFERENCES messages(id),
    outbound_message_id INTEGER UNIQUE
        REFERENCES messages(id),
    trigger_type TEXT NOT NULL,
    status TEXT NOT NULL,
    persona_version INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT
);
```

`turn` 表示一次回复尝试：

- `trigger_type`：`private` / `group_at` / `group_wake_word`
- `status`：`pending` / `generated` / `suppressed` / `sent` / `failed`
- `inbound_message_id`：唯一对应的入站消息
- `outbound_message_id`：发送成功后关联的出站消息
- `persona_version`：本轮使用的人设版本

状态流转：

```text
触发回复
  -> pending
     -> generated（生成成功，等待发送）
        -> sent（平台发送成功且 outbound 已落库）
        -> failed（发送失败）
     -> suppressed（限流、空回复或策略决定不回复）
     -> failed（生成或处理异常）
```

约束：

- 普通群消息只写 `messages`，不创建 turn。
- 群聊 @、唤醒词和私聊触发才创建 turn。
- 同一入站消息最多创建一个 turn。
- 只有发送成功才写 outbound，并把 turn 更新为 `sent`。
- 发送失败只更新 turn 为 `failed`，不写 outbound。
- 入站消息和出站消息都回填同一个 `messages.turn_id`，便于直接追踪一轮问答。

## 8. 索引

当前索引：

| 索引 | 列 | 用途 |
|---|---|---|
| `idx_messages_conversation_time` | `platform, account_id, conversation_type, conversation_id, timestamp` | 会话过滤 |
| `idx_messages_sender` | `platform, account_id, sender_id, timestamp` | 按发送者查询 |
| `idx_turns_session_started` | `session_id, started_at` | 会话内 turn 时间线 |
| `idx_messages_turn` | `turn_id` | 按 turn 聚合消息 |

## 9. 上下文重建

`SQLiteConversationContextStore` 按以下步骤工作：

1. 使用 `(platform, account_id, conversation_type, conversation_id)` 定位会话。
2. 按 `messages.id DESC` 取最近 N 条。
3. 反转为时间正序。
4. 跳过 `origin='system'` 的消息。
5. 按消息来源和会话类型渲染内容。
6. 从尾部向前应用字符预算。
7. 返回 `user` / `assistant` 消息列表。

隔离规则：

- 私聊和群聊默认隔离。
- 不同平台、账号、会话类型和会话 ID 之间不共享上下文。
- 模型看不到原始 OneBot 事件，只能看到渲染后的上下文文本。

## 10. 迁移

### v1

建立：

- `conversations`
- `messages`

### v1 -> v2

M5A 增量迁移：

1. `messages` 增加 `origin`，默认 `inbound`。
2. `messages` 增加 `turn_id`。
3. `messages` 增加 `conversation_ref_id`。
4. 按 `is_self` 回填 `origin`：`1 -> outbound`，`0 -> inbound`。
5. 按平台和会话标识回填 `conversation_ref_id`。
6. 创建 `agent_sessions`，为已有 conversations 生成 session。
7. 创建 `turns` 和相关索引。

迁移要求：

- 迁移前备份数据库。
- 迁移在一个版本事务中执行，失败整体回滚。
- 已有消息、会话和原始事件不得丢失。
- `tests/test_sqlite_repository.py` 覆盖 v1 -> v2 数据保留。

## 11. 保留与清理

当前没有自动清理策略。所有入站消息和成功出站消息保留，供上下文重建和后续审计使用。

M5B 及以后需要补充：

- 原文、摘要、记忆和审计的分层保留期。
- 数据库备份与恢复演练。
- 超限时的归档和导出策略。
- 删除记忆、导出数据时的可审计流程。

## 12. 版本记录

- v0.1（2026-10-24）：记录 SQLite v1 结构、M5 草案表和数据所有权。
- v0.2（2026-10-25）：M5A 完成；记录 v2 迁移、outbound、session、turn 和上下文重建。
