# S8-T4 System Memory 定位与 Recall 机制（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S8-T4`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版 system memory 的正式定位与 recall 机制。

目标是：

1. 明确 system memory 在 `S8` 中的职责
2. 明确 system memory 的 recall 时机与方式
3. 明确 system memory 的正文、召回层、索引层分工
4. 明确 system memory write 与 `handoff` 的关系

## 2. 正式结论

本任务最终结论如下：

1. system memory 属于长期记忆层
2. system memory 保存跨 run 可复用的完整长期记忆
3. system memory recall 只在 run 最开始执行一次
4. system memory recall 只使用初始 `user_input`
5. system memory 的轻召回层来自 sqlite
6. system memory 正文来自 md
7. system memory write 通过 `handoff.memory_payload` 驱动

## 3. System Memory 的定位

system memory 在 v1 中的定位是：

1. 长期记忆层的正式主体
2. 保存可跨 run 复用的长期知识、经验、模式、事实、背景

它不负责：

1. 当前 run 的运行期上下文
2. 用户个体协作偏好

## 4. System Memory 的三重表达

第一版 system memory 采用三重表达：

1. `md`
2. `sqlite`
3. 索引页

## 4.1 `md`

职责：

1. 保存 system memory 正文
2. 作为完整长期记忆内容载体

## 4.2 `sqlite`

职责：

1. 保存轻召回层
2. 保存结构化检索字段
3. 为 recall matcher 提供候选集合

## 4.3 索引页

职责：

1. 提供人类导航入口
2. 提供按类型、主题的总览
3. 方便维护 system memory 体系

## 5. 最小记忆单元

system memory 第一版最小单元如下：

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

## 6. Recall 触发时机

本任务明确规定：

1. system memory recall 只在整次 run 最开始触发一次
2. 不按 phase 重复 recall
3. 不按 step 重复 recall

这意味着：

1. recall 结果作为整次 run 的共享长期背景
2. 后续所有 phase 复用这份结果

## 7. Recall 输入

第一版 system memory recall 只使用：

1. 初始 `user_input`

不使用：

1. `current_phase`
2. `active_node`
3. 运行中临时状态

## 8. Recall 候选来源

本任务明确规定：

1. recall 从 sqlite 中读取所有 `active` system memory
2. 不做文本粗筛
3. 如有必要，只做数量上限保护

数量上限保护的定位是：

1. 运行安全措施
2. 不是召回语义策略

## 9. Recall Matcher

第一版使用一个小模型 matcher 进行 system memory 选择。

matcher 的职责：

1. 基于 `user_input`
2. 对候选记忆的 `summary` 做相关性判断
3. 打分并筛选少量条目

matcher 输出保留：

1. `memory_id`
2. `score`
3. `reason`

其中：

1. `reason` 只用于内部可观测
2. 不进入主 prompt

## 10. 轻召回层注入

最终进入 prompt 的 system memory 轻召回内容包括：

1. `memory_id`
2. `title`
3. `memory_type`
4. `summary`
5. 最多 `5` 个 tags

也就是说：

1. prompt 不直接拿正文 md
2. prompt 先拿轻召回结果

## 11. 正文获取工具

本任务明确规定：

1. system memory 正文只能通过正式工具获取
2. 输入只使用 `memory_id`

第一版工具输出如下：

```ts
type GetLongTermMemoryContentResult = {
  memory_id: string;
  title: string;
  memory_type: "fact" | "pattern" | "strategy" | "experience" | "context";
  content_md: string;
};
```

## 12. Write 输入来源

system memory write 不再直接消费旧的 `verification_handoff`。

第一版明确规定：

1. system memory write 通过 `handoff.memory_payload` 驱动

其最小结构如下：

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

这意味着：

1. `handoff` 表达“要保留什么”
2. system memory write 再补正式 `memory_id`、`md_path`、时间戳等

## 13. 与主链路的关系

system memory 与主链路的关系如下：

1. recall 挂在 run-start / prompt-build
2. write 挂在 finalize-closeout
3. recall 进入 prompt
4. write 不进入当前主判定链

## 14. 对其他任务的直接输入

`S8-T4` 直接服务：

1. `S8-T7` memory domain 总设计
2. `S11-T3` handoff 字段扩展
3. `S11-T6` finalize memory hooks
4. `S1-T4` prompt 与状态边界

同时它直接依赖：

1. `S8-T3` system memory 现状清单
2. `S8-T7` memory domain 重设计

## 15. 本任务结论摘要

可以压缩成 5 句话：

1. system memory 是长期记忆层的正式主体
2. recall 只在 run 开始时发生一次，只看初始 `user_input`
3. sqlite 提供轻召回层，md 提供正文，索引页提供导航
4. 正文只能通过 `memory_id` 对应的正式工具获取
5. write 统一通过 `handoff.memory_payload` 驱动
