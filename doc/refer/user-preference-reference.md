# InDepth User Preference 记忆参考

更新时间：2026-04-19

返回总览：
- [Memory 总览](./memory-reference.md)

## 1. 模块定位

User Preference Memory 负责“用户个人偏好的长期保存与再次注入”。

它关心的是用户是谁、喜欢什么风格、希望怎样协作，而不是某个任务本身发生了什么。

适合放进这里的内容：
- 语言偏好
- 回答风格
- 工具栈
- 长期目标
- 角色 / 领域偏好

不适合放进这里的内容：
- 当前 task 的对话历史
- 某次任务总结出来的经验卡

## 2. 关键文件

- `app/core/memory/user_preference_store.py`
- `app/core/runtime/user_preference_lifecycle.py`

## 3. 存储

默认存储文件：

- `memory/preferences/user-preferences.md`

这是一个单文件 Markdown store，不是 SQLite。

当前格式有两层：

1. `meta`
   - `version`
   - `updated_at`
   - `enabled`

2. `preferences`
   - 每个 key 一条记录

每条 preference 典型字段：
- `value`
- `source`
- `confidence`
- `updated_at`
- `note`

## 4. 生命周期

### 4.1 recall：运行开始时注入

入口：

- `inject_user_preference_recall(...)`

触发时机：

- `AgentRuntime.run()` 组装 prompt 早期

做法：

1. 从 `UserPreferenceStore` 读出所有偏好
2. 按：
   - `top_k`
   - `always_include_keys`
   - `max_chars`
   生成 recall block
3. 把 block 注入当前 messages

所以它是“任务开始前注入”，不是等任务结束才生效。

### 4.2 capture：任务结束后写回

入口：

- `capture_user_preferences(...)`

触发时机：

- runtime completed finalizer

做法：

1. 从当前 `user_input` 中抽取明确偏好
2. 先走 LLM extract
3. 再做白名单过滤、敏感信息过滤、置信度过滤
4. 满足条件后写回 Markdown 文件

## 5. 当前允许的 key

当前实现里允许的 key 主要包括：

- `job_role`
- `domain_expertise`
- `interest_topics`
- `language_preference`
- `response_style`
- `tooling_stack`
- `goal_long_term`

这意味着：

不是任意字符串都能写进 preference store。

User Preference 是受控字段，不是开放 KV 仓库。

## 6. 来源与可信度

每条偏好都有来源语义：

1. `explicit_user`
   - 用户显式声明
   - 通常可信度最高

2. `llm_extract_v1`
   - 从用户输入里抽取
   - 需要置信度门槛

当前系统特别强调两点：

1. 不要猜
2. 不要写入敏感信息

所以 `capture_user_preferences(...)` 会过滤：
- 非白名单 key
- 低置信度条目
- 高风险敏感值

## 7. 和另外两类 memory 的区别

### 7.1 vs Runtime Memory

Runtime Memory 记录的是：
- 当前任务发生了什么

User Preference 记录的是：
- 这个用户通常喜欢怎样协作

### 7.2 vs System Memory

System Memory 记录的是：
- 任务经验、复用路径、经验卡

User Preference 记录的是：
- 用户个人习惯和偏好

可以用一句话区分：

如果这个信息换个 task 还成立，而且换个用户就不一定成立，它大概率属于 User Preference。

## 8. 观测

User Preference 相关事件包括：

- `user_preference_recall_succeeded`
- `user_preference_recall_failed`
- `user_preference_extract_started`
- `user_preference_extract_succeeded`
- `user_preference_extract_failed`
- `user_preference_capture_succeeded`
- `user_preference_capture_failed`

这些事件能帮助回答：
- 是否真的注入了偏好
- 提取出了多少候选
- 最终写回了哪些 key
- 哪些被跳过

## 9. 你应该用它来回答什么问题

User Preference Memory 最适合回答：

- 为什么这次默认用中文回复
- 为什么系统倾向简洁或详细风格
- 某个长期偏好是什么时候写进去的
- 某个偏好为什么没有被写入

如果你的问题是下面这些，就不该优先看这里：

- “当前 task 的上下文为什么被压缩”
  - 去看 [Runtime 会话记忆](./runtime-memory-reference.md)
- “过去某个任务的经验为什么又被召回”
  - 去看 [System 经验记忆](./system-memory-reference.md)
