# 用户偏好记忆（单层 Markdown 存储）设计稿 V1

更新时间：2026-04-16  
状态：V1 已落地（LLM 提取，已验收）

## 1. 背景与目标

当前记忆体系以运行时上下文与系统记忆为主，尚缺少针对“用户偏好”的稳定沉淀能力。  
本设计新增“用户偏好记忆”模块，并采用本地 `.md` 文件持久化（不使用 DB），用于跨会话复用用户偏好（兴趣、职业背景、表达偏好、常用工具等）。

目标：
1. 提供跨会话可复用的用户偏好记忆能力。
2. 采用单层存储模型（不分级，不分库表）。
3. 采用 Markdown 本地文件作为唯一持久化载体。
4. 偏好提取默认走 LLM（结构化抽取），并通过双闸门控制写入质量。

## 2. 范围与非目标

范围：
1. 偏好记忆的 Markdown 文件模型。
2. 偏好记忆写入（capture）与读取（recall）策略。
3. 用户可控能力：查看、修改、删除、清空、禁用。
4. 与现有 runtime prompt 组装的注入接口。

非目标：
1. 不实现多层级存储（全局/项目/会话分层）。
2. 不实现自动画像推断（人格标签、心理模型）。
3. 不实现高敏感数据默认采集。
4. 不替代 system memory / runtime memory 既有机制。

## 3. 核心原则

1. 单层模型：所有偏好写入同一类 Markdown 文档。
2. 用户主权：用户可随时查看、修正、删除、清空、关闭。
3. 最小必要：只记录对回答质量有明确帮助的信息。
4. 低风险默认：敏感内容默认不写入。
5. 可追踪：每条偏好包含来源、证据片段与更新时间。

## 4. 存储方案（Markdown）

### 4.1 目录约定

建议目录：`/Users/yezibin/Project/InDepth/memory/preferences/`

### 4.2 文件约定

1. 主文件：`user-preferences.md`
2. 仅维护一个主文件（单层），不按类型拆分多级目录。

### 4.3 文件结构（建议模板）

```md
# User Preferences

meta:
- version: 1
- updated_at: 2026-04-16T00:00:00+08:00
- enabled: true

## preferences

### job_role
- value: 后端工程师
- source: llm_extract_v1
- confidence: 0.92
- updated_at: 2026-04-16T00:00:00+08:00
- note: evidence=我是后端工程师
```

说明：
1. 每个偏好项使用三级标题作为稳定 key。
2. `value` 支持标量或数组文本。
3. `source/confidence/updated_at` 必填，`note` 可存证据摘要。

## 5. 偏好键规范（白名单）

V1 白名单：
1. `job_role`
2. `domain_expertise`
3. `interest_topics`
4. `language_preference`
5. `response_style`
6. `tooling_stack`
7. `goal_long_term`

规则：
1. key 使用英文 snake_case。
2. 非白名单 key 一律丢弃。
3. 禁止写入 task/run 等流程噪声字段。

## 6. 提取方案（LLM 主路径）

### 6.1 提取输入

1. 当前 `user_input`（必选）。
2. 可选：已有偏好快照（用于冲突判断）。
3. 不输入系统长文本与工具日志，控制噪声与成本。

### 6.2 提取输出（强约束 JSON）

要求 LLM 输出：

```json
{
  "updates": [
    {
      "key": "response_style",
      "value": "简洁、结论先行",
      "confidence": 0.9,
      "explicit": true,
      "action": "upsert",
      "evidence_span": "回答简洁一点"
    }
  ]
}
```

字段约束：
1. `action` 仅允许：`upsert` / `delete` / `ignore`。
2. `confidence` 必须在 `[0,1]`。
3. `explicit` 为布尔值。
4. `evidence_span` 建议保留原句片段。

解析失败或 schema 不合法：本轮不写入。

## 7. 写入策略（双闸门）

写入时机：
1. 主时机：`run_end`。
2. 次时机：`awaiting_user_input`（仅允许高置信显式项）。

闸门 A（显式性闸门）：
1. `explicit=true` 才允许自动写入。

闸门 B（置信/冲突闸门）：
1. 普通写入：`confidence >= 0.75`。
2. 冲突写入（与当前值不同）：`confidence >= 0.90` 才覆盖。
3. 不满足条件则跳过并记录原因。

附加规则：
1. 同 key 覆盖更新，保留最新时间。
2. 数组值去重并限制长度（建议最多 10 项）。
3. 一轮最多写入一次（批量 upsert）。
4. 敏感信息命中时强制跳过。

## 8. 读取策略（Recall）

1. 每次 `run_start` 读取 `user-preferences.md`。
2. 仅注入 Top-K 偏好（建议 K=3~5）。
3. `language_preference`、`response_style` 可常驻注入。
4. 注入仅保留短句，不注入完整文件原文。

注入示例：
- `用户偏好召回：response_style=简洁、结论先行；language_preference=中文。`

## 9. 用户可控能力

建议提供命令/工具能力：
1. 查看：读取并展示 `user-preferences.md`。
2. 更新：按 key upsert。
3. 删除：删除某个 key 区块。
4. 清空：清空 `preferences` 区域。
5. 开关：修改 `meta.enabled`。

行为约束：
1. 用户说“不要记住”时，应删除对应项或 `enabled=false`。
2. 用户说“忘记全部偏好”时，应清空并确认。

## 10. 可观测性

建议事件：
1. `user_preference_extract_started`
2. `user_preference_extract_succeeded`
3. `user_preference_extract_failed`
4. `user_preference_capture_succeeded`
5. `user_preference_capture_failed`
6. `user_preference_recall_succeeded`

`capture_succeeded` 至少记录：
1. `updated_count`
2. `updated_keys`
3. `skipped_count`
4. `skipped_reasons`

## 11. 配置项建议（V1）

1. `ENABLE_USER_PREFERENCE_MEMORY=true`
2. `USER_PREFERENCE_FILE_PATH=memory/preferences/user-preferences.md`
3. `USER_PREFERENCE_RECALL_TOP_K=5`
4. `USER_PREFERENCE_ALWAYS_INCLUDE_KEYS=language_preference,response_style`
5. `USER_PREFERENCE_MAX_INJECT_CHARS=240`
6. `ENABLE_USER_PREFERENCE_LLM_EXTRACT=true`
7. `USER_PREFERENCE_AUTO_WRITE_MIN_CONFIDENCE=0.75`
8. `USER_PREFERENCE_CONFLICT_MIN_CONFIDENCE=0.90`

## 12. 验收口径

1. 存储层不依赖 DB，仅使用 Markdown 文件。
2. 偏好提取主路径为 LLM，且输出受 schema 约束。
3. 双闸门生效：显式性 + 置信/冲突。
4. 用户可执行查看/修改/删除/清空/禁用。
5. 偏好模块故障不影响主任务流程。

## 13. 落地步骤

1. 新增 `memory/preferences/` 目录与默认模板文件。
2. 实现 Markdown 解析与原子写回。
3. 在 runtime 中接入 LLM 偏好提取链路（run_end/awaiting_user_input）。
4. 实现双闸门写入与敏感信息拦截。
5. 在 run_start 注入偏好 recall。
6. 增加回归测试并更新参考文档。

## 14. 风险与缓解

1. 风险：LLM 幻觉导致误写。  
缓解：白名单 + schema 校验 + 双闸门。

2. 风险：并发写导致文件冲突。  
缓解：临时文件原子替换（必要时加文件锁）。

3. 风险：偏好过多导致注入冗余。  
缓解：Top-K + 字符预算限制。
