# S8-T8 Memory Skeleton Interfaces（V1）

更新时间：2026-04-23  
状态：Draft  
对应任务：`S8-T8`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版 memory domain 的最小接口骨架。

目标是：

1. 把三层 memory 正式落到接口层
2. 明确 runtime memory、system memory、user preference 各自的最小接口
3. 让后续实现可以围绕统一接口直接展开

## 2. 正式结论

本任务最终结论如下：

1. runtime memory 采用单入口处理器接口
2. system memory 拆成 recall / write 两组接口
3. user preference 也拆成 recall / write 两组接口
4. system memory 正文获取工具属于 memory domain 正式接口的一部分
5. closeout write 接口直接消费 `memory_payload / preference_payload`

## 3. Runtime Memory 接口

runtime memory 第一版只暴露单入口处理器接口。

推荐方向如下：

```ts
type RuntimeMemoryInput = {
  task_id: string;
  run_id: string;
  current_phase: string;
  active_node_id?: string;
  user_input: string;
  compression_state?: unknown;
};

interface RuntimeMemoryProcessor {
  build_prompt_context_text(input: RuntimeMemoryInput): string;
}
```

本任务明确规定：

1. runtime memory 不暴露很多碎方法
2. 第一版只围绕生成 `prompt_context_text`

## 4. System Memory Recall 接口

system memory recall 第一版建议如下：

```ts
type SystemMemoryRecallInput = {
  user_input: string;
};

type SystemMemoryRecallSelection = {
  selected: Array<{
    memory_id: string;
    score: number;
    reason?: string;
  }>;
};

type SystemMemoryRecallPromptItem = {
  memory_id: string;
  title: string;
  memory_type: "fact" | "pattern" | "strategy" | "experience" | "context";
  summary: string;
  tags: string[];
};

interface SystemMemoryRecallService {
  recall(input: SystemMemoryRecallInput): SystemMemoryRecallSelection;
  build_prompt_items(selection: SystemMemoryRecallSelection): SystemMemoryRecallPromptItem[];
}
```

本任务明确规定：

1. recall 只在 run 开始时调用一次
2. recall 只使用初始 `user_input`

## 5. System Memory Write 接口

system memory write 第一版建议如下：

```ts
type MemoryPayload = {
  candidates: Array<{
    title: string;
    memory_type: "fact" | "pattern" | "strategy" | "experience" | "context";
    summary: string;
    tags: string[];
  }>;
};

interface SystemMemoryWriteService {
  write(payload: MemoryPayload): void;
}
```

本任务明确规定：

1. write 直接消费 `handoff.memory_payload`
2. write 负责补正式 `memory_id`、`md_path`、时间戳等

## 6. System Memory 正文获取工具接口

本任务明确规定：

1. 正文获取工具属于 system memory 正式接口的一部分

推荐方向如下：

```ts
type GetLongTermMemoryContentResult = {
  memory_id: string;
  title: string;
  memory_type: "fact" | "pattern" | "strategy" | "experience" | "context";
  content_md: string;
};

interface SystemMemoryContentTool {
  get(memory_id: string): GetLongTermMemoryContentResult;
}
```

## 7. User Preference Recall 接口

user preference recall 第一版建议如下：

```ts
interface UserPreferenceRecallService {
  recall_full_markdown(): string;
}
```

本任务明确规定：

1. recall 只在 run 开始时调用一次
2. recall 不做筛选
3. recall 直接返回整份偏好 md

## 8. User Preference Write 接口

user preference write 第一版建议如下：

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

interface UserPreferenceWriteService {
  write(payload: PreferencePayload): void;
}
```

本任务明确规定：

1. write 直接消费 `handoff.preference_payload`
2. write 采用按 key 更新 md 的方式

## 9. 推荐总骨架

可以用下面这张图理解：

```text
MemoryDomain
  -> RuntimeMemoryProcessor
  -> SystemMemoryRecallService
  -> SystemMemoryWriteService
  -> SystemMemoryContentTool
  -> UserPreferenceRecallService
  -> UserPreferenceWriteService
```

## 10. 与统一挂点的关系

本任务与 `S8-T7` 对齐如下：

```text
run-start / prompt-build
  -> SystemMemoryRecallService
  -> UserPreferenceRecallService

run-progress / step-prep
  -> RuntimeMemoryProcessor

finalize-closeout
  -> SystemMemoryWriteService
  -> UserPreferenceWriteService
```

## 11. 第一版边界

第一版明确不建议：

1. runtime memory 再拆很多细接口
2. system memory recall / write 混成一套接口
3. user preference recall / write 混成一套接口
4. write 接口再回头消费完整运行历史
5. memory domain 直接读写 `RunContext`

## 12. 对其他任务的直接输入

`S8-T8` 直接服务：

1. `S3-T5` step / orchestrator 实现
2. `S1-T5` prompt assembly 实现
3. `S11-T6` finalize closeout hooks 实现
4. `S12-T7` 观测与测试 skeleton

同时它直接依赖：

1. `S8-T2` runtime memory 模型
2. `S8-T4` system memory 设计
3. `S8-T6` user preference 设计
4. `S8-T7` memory domain 重设计

## 13. 本任务结论摘要

可以压缩成 5 句话：

1. runtime memory 采用单入口处理器接口
2. system memory 和 user preference 都拆成 recall / write 两组接口
3. system memory 正文获取工具属于正式 memory 接口
4. closeout write 直接消费 `memory_payload / preference_payload`
5. 三层 memory 的接口骨架已可直接支撑后续实现
