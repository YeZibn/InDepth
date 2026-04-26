# S8-T7 Memory Domain 重设计（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S8-T7`

## 1. 目标

本任务用于重新定义 `runtime-v2` 中 `S8` memory domain 的正式结构。

目标是：

1. 把 `S8` 重新收敛成 3 个正式主位
2. 明确三层记忆的职责边界
3. 明确三层记忆在主链路中的统一挂点
4. 明确 `handoff` 如何承接 memory / preference 写入输入

## 2. 正式结论

本任务最终结论如下：

1. `S8` 由 3 个正式主位组成
2. 这 3 个正式主位分别是：
   - 运行期上下文层
   - 长期记忆层
   - 用户偏好层
3. 三者都属于 `S8` 正式核心，不降为外围设施
4. 三者通过统一挂点接入主链路
5. closeout 后的长期沉淀统一由 `handoff` 承接输入

## 3. 三个正式主位

## 3.1 运行期上下文层

职责：

1. 处理当前 run 为继续推进所需的运行期上下文材料
2. 生成 prompt 所需的运行期上下文文本

本任务明确规定：

1. 运行期上下文层作为处理器存在
2. 它不作为 `RunContext` 主状态块存在
3. 第一版输出继续采用旧模式：
   - `prompt_context_text`

最小输入如下：

1. `task_id`
2. `run_id`
3. `current_phase`
4. `active_node_id`
5. `user_input`
6. `compression_state`

最小输出如下：

1. `prompt_context_text`

## 3.2 长期记忆层

职责：

1. 保存跨 run 可复用的完整长期记忆
2. 在新 run 开始时按需召回

本任务明确规定：

1. 它不只保存经验
2. 它保存完整长期记忆

第一版长期记忆单元最小结构如下：

```ts
type LongTermMemoryItem = {
  memory_id: string;
  title: string;
  memory_type: "fact" | "pattern" | "strategy" | "experience" | "context";
  summary: string;
  tags: string[];
  status: "active" | "archived";
  md_path: string;
  created_at: string;
  updated_at: string;
};
```

长期记忆采用三重表达：

1. `md` 保存正文
2. `sqlite` 保存轻召回层
3. 索引页提供人类导航入口

## 3.3 用户偏好层

职责：

1. 保存 user-specific preference
2. 为整次 run 提供用户长期协作偏好背景

本任务明确规定：

1. 用户偏好层不保存一般性长期知识
2. 用户偏好层以 `md` 为主
3. recall 时直接整页注入
4. write 时更新这份偏好 md

第一版最小偏好范围包括：

1. `language_preference`
2. `response_style`
3. `format_preference`
4. `tooling_preference`
5. `goal_preference`

## 4. 三层统一挂点

本任务明确采用以下统一挂点：

```text
run-start / prompt-build
  -> long-term memory recall
  -> user preference recall

run-progress / step-prep
  -> runtime memory processor

finalize-closeout
  -> long-term memory write
  -> user preference write
```

## 4.1 run-start / prompt-build

这里挂：

1. 长期记忆 recall
2. 用户偏好 recall

作用：

1. 形成整次 run 的初始长期背景
2. 后续所有 phase 共享这份背景

## 4.2 run-progress / step-prep

这里挂：

1. 运行期上下文处理器

作用：

1. 为每次 step 处理和生成当前 prompt 所需的上下文文本

## 4.3 finalize-closeout

这里挂：

1. 长期记忆 write
2. 用户偏好 write

作用：

1. 在 run 收尾后沉淀跨 run 内容
2. 不在 execute 中途频繁写入

## 5. 长期记忆 Recall 规则

第一版长期记忆 recall 规则如下：

1. 只在整次 run 最开始执行一次
2. 只使用初始 `user_input`
3. 不按 phase 重复 recall
4. 不按 step 重复 recall
5. 从 sqlite 中读取所有 `active` 长期记忆
6. 如有必要，只做数量上限保护
7. 不做文本粗筛
8. 使用一个小模型 matcher 基于 `summary` 做打分与筛选

matcher 输出保留：

1. `memory_id`
2. `score`
3. `reason`

其中：

1. `reason` 只作内部可观测
2. 不进入主 prompt

最终进入 prompt 的轻召回内容包括：

1. `memory_id`
2. `title`
3. `memory_type`
4. `summary`
5. 最多 `5` 个 tags

## 6. 长期记忆正文获取工具

本任务明确规定：

1. 长期记忆正文 `md` 不直接注入 prompt
2. 如主链路需要全文，必须通过正式工具获取

第一版工具最小输入输出如下：

输入：

1. `memory_id`

输出：

```ts
type GetLongTermMemoryContentResult = {
  memory_id: string;
  title: string;
  memory_type: "fact" | "pattern" | "strategy" | "experience" | "context";
  content_md: string;
};
```

## 7. 用户偏好 Recall / Write 规则

第一版用户偏好规则如下：

1. recall 只在整次 run 最开始执行一次
2. recall 直接把整份偏好 md 注入 prompt
3. 不做条目级筛选
4. 不按 phase 重复注入
5. write 放在 finalize closeout 后

## 8. Handoff 中的 Memory / Preference 字段

本任务明确规定：

1. `handoff` 是 closeout 后置保存动作的统一输入承接层
2. `handoff` 中应预留专门字段，表达要保留的记忆内容

## 8.1 `memory_payload`

第一版结构如下：

```ts
type MemoryPayload = {
  candidates: Array<{
    title: string;
    memory_type: "fact" | "pattern" | "strategy" | "experience" | "context";
    summary: string;
    tags: string[];
  }>;
};
```

这里表达的是：

1. 这次 closeout 后有哪些长期记忆候选值得保留

## 8.2 `preference_payload`

第一版结构如下：

```ts
type PreferencePayload = {
  candidates: Array<{
    preference_key:
      | "language_preference"
      | "response_style"
      | "format_preference"
      | "tooling_preference"
      | "goal_preference";
    value: string;
    summary: string;
  }>;
};
```

这里表达的是：

1. 这次 closeout 后有哪些用户偏好候选值得更新

## 9. 与 RunContext 的关系

本任务明确规定：

1. 运行期上下文层属于 `S8` 正式主位
2. 但它不直接成为 `RunContext` 的一级正式状态块
3. `RunContext` 只保留最小锚点状态
4. prompt 所需的运行期上下文由处理器输出

## 10. 对其他任务的直接输入

`S8-T7` 直接服务：

1. `S8-T2` runtime memory 模型
2. `S8-T4` system memory 定位与 recall 机制
3. `S8-T6` user preference 定位与更新规则
4. `S11-T3` handoff 字段扩展
5. `S11-T6` finalize closeout hooks

同时它直接依赖：

1. `S1-T4` prompt 与状态边界规则
2. `S4-T4` 极简 RunContext
3. `S11-T3` 统一 handoff 结构
4. `S11-T6` finalize pipeline

## 11. 本任务结论摘要

可以压缩成 5 句话：

1. `S8` 由运行期上下文、长期记忆、用户偏好三层组成
2. 长期记忆采用 `md + sqlite + 索引页`，用户偏好采用 `md`
3. recall 统一挂在 run 开始，write 统一挂在 finalize closeout
4. 长期记忆正文只能通过正式工具按 `memory_id` 获取
5. `handoff` 中预留 `memory_payload / preference_payload` 作为后置保存输入
