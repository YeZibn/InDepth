# Runtime Memory 实现说明

## 当前范围

当前 `runtime-v2` 已正式落地短期上下文 `runtime memory` 的最小 sqlite 版实现，并已开始接入 execute 主链与 `ReActStepRunner`。

当前已实现：

1. runtime memory 正式模型
2. sqlite store
3. runtime memory processor
4. step / tool 轨迹写入
5. task 级 `prompt_context_text` 组装
6. `reflexion` 正式写入链

对应代码：

1. [src/rtv2/memory/models.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/memory/models.py)
2. [src/rtv2/memory/store.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/memory/store.py)
3. [src/rtv2/memory/sqlite_store.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/memory/sqlite_store.py)
4. [src/rtv2/memory/processor.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/memory/processor.py)
5. [src/rtv2/solver/react_step.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/solver/react_step.py)
6. [src/rtv2/orchestrator/runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py)
7. [tests/test_runtime_memory_models.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_memory_models.py)
8. [tests/test_runtime_memory_sqlite_store.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_memory_sqlite_store.py)
9. [tests/test_runtime_memory_processor.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_memory_processor.py)

## 当前正式结构

当前 `runtime memory` 采用 unified entry 流。

第一版核心对象包括：

1. `RuntimeMemoryEntry`
2. `RuntimeMemoryQuery`
3. `RuntimeMemoryStore`
4. `SQLiteRuntimeMemoryStore`
5. `RuntimeMemoryProcessor`

其中：

1. `RuntimeMemoryEntryType` 当前只保留：
   - `context`
   - `reflexion`
2. `RuntimeMemoryRole` 当前最小保留：
   - `user`
   - `assistant`
   - `tool`
   - `system`
3. `reflexion` entry 当前带最小结构化字段：
   - `reflexion_trigger`
   - `reflexion_reason`
   - `next_attempt_hint`
   - `reflexion_action`

## 当前 sqlite 设计

当前 sqlite 使用单表：

1. `runtime_memory_entries`

当前主要字段包括：

1. `seq`
2. `entry_id`
3. `task_id`
4. `run_id`
5. `step_id`
6. `node_id`
7. `entry_type`
8. `role`
9. `content`
10. `tool_name`
11. `tool_call_id`
12. `related_result_refs_json`
13. `reflexion_trigger`
14. `reflexion_reason`
15. `next_attempt_hint`
16. `reflexion_action`
17. `created_at`

其中：

1. `seq` 是内部稳定排序键
2. `entry_id` 是业务唯一标识
3. 第一版查询主要围绕：
   - `task_id`
   - `run_id`
   - `step_id`
   - `node_id`
   - `entry_type`
   - `tool_name`

## 当前 processor 行为

`RuntimeMemoryProcessor` 当前读取整个 `task_id` 下的 runtime memory，并输出：

1. `prompt_context_text`

当前输出特征如下：

1. 先输出当前调用锚点：
   - `task_id`
   - `run_id`
   - `current_phase`
   - `active_node_id`
   - `user_input`
2. 再输出 task 级 runtime memory timeline
3. timeline 按 `seq ASC` 排序
4. 多个 run 会按 `run_id` 显式分段
5. 旧 run 的 user 输入原文会保留
6. `reflexion` 的结构化字段会展开成显式文本

## 当前主链接线

当前 memory 接线分为两层：

1. `RuntimeOrchestrator`
   - 负责写入 run 级 user 输入
   - 负责调用 `RuntimeMemoryProcessor`
   - 负责把 `prompt_context_text` 拼入当前 `step_prompt`
2. `ReActStepRunner`
   - 负责写入 step 内 assistant 轨迹
   - 负责写入 tool call entry
   - 负责写入 tool result entry

当前第一版写入粒度如下：

1. run 开始时写 1 条 user entry
2. 每次 tool call 写 1 条 assistant entry
3. 每次 tool result 写 1 条 tool entry
4. 每次 step 完成写 1 条 assistant entry
5. 每次 evaluator fail / blocked / failed 触发的 reflexion 写 1 条 reflexion entry

## 当前边界

当前这一步明确不进入：

1. compaction
2. summarize
3. compression 对接
4. 长期记忆 recall / write
5. 用户偏好 recall / write
6. memory view 裁剪
7. 更细粒度的 memory view 裁剪策略

这些内容会在后续模块继续落地。
