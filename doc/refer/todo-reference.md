# InDepth Todo 编排参考

更新时间：2026-04-21

## 1. 目标

Todo 编排层负责把复杂任务拆成可执行、可验证、可审计的最小动作单元，并为主 Agent / SubAgent 协作提供统一状态面。

当前实现已经回到一条更简单的主线：
1. 当前 task 绑定一个 `todo_id`
2. prepare 决定是否创建或沿用 todo
3. 执行过程围绕某个 active subtask 展开
4. 通过状态流转和增量更新维护 todo
5. task 结束后关闭当前 todo 绑定

Todo 当前不再承载独立的 fallback/recovery 数据模型。

## 2. 当前 Todo 主线

### 2.1 Task 绑定 Todo

Runtime 会维护 task 级的 todo 上下文，当前最重要的字段有：
- `todo_id`
- `active_subtask_id`
- `active_subtask_number`
- `execution_phase`
- `binding_required`
- `binding_state`
- `todo_bound_at`

作用：
1. 确保当前 task 围绕一个 todo 主线推进
2. 避免普通路径重复创建新 todo
3. 让 executing/finalizing 阶段知道当前处在哪个编排上下文

### 2.2 Prepare 与现状扫描

当 active todo 存在时，prepare 会先补一层 `current_state_scan`，当前包含：
- `progress`
- `completed_subtasks`
- `unfinished_subtasks`
- `ready_subtasks`
- `known_artifacts`
- `summary`

因此 prepare 不只是知道“有没有 todo”，还知道“当前 todo 已做到哪里”。

### 2.3 当前 active subtask

当前真正被执行的是某个 active subtask，通常来自：
- `get_next_task`
- `update_task_status(..., "in-progress")`
- `reopen_subtask`
- 某些 `update_subtask` 后的上下文同步

## 3. 公开工具

当前对外 todo 工具只有：
- `prepare_task`
- `plan_task`
- `update_task_status`
- `reopen_subtask`
- `update_subtask`
- `append_followup_subtasks`
- `list_tasks`
- `get_next_task`
- `get_task_progress`
- `generate_task_report`

## 4. `plan_task` 的角色

`plan_task` 是当前唯一的对外 todo 落盘入口。

它负责：
1. 校验结构化计划
2. 决定 create 还是 update
3. 调用内部落盘逻辑
4. 返回统一执行结果给 Runtime

也就是说：
1. prepare 负责产生候选计划
2. Runtime 负责决定何时自动落盘
3. `plan_task` 负责真正修改 todo 文件

## 5. Subtask 设计原则

当前仍建议 subtask 遵守这些约束：
1. 粒度尽量是“单一可验证动作”
2. 描述必须明确交付物或检查点
3. 依赖尽量显式写出
4. 不要把多个大阶段压成一个 subtask
5. 子代理协同行为若存在，应体现在 subtasks 里，而不是只写在说明文字里

## 6. 状态流转

当前 todo 主要通过三类动作推进：
1. `update_task_status`
2. `update_subtask`
3. `reopen_subtask`

其中：
- `update_task_status` 是标准状态迁移入口
- `update_subtask` 是字段级补丁入口
- `reopen_subtask` 用来把已有任务重新拉回执行主线

## 7. Follow-up subtasks

`append_followup_subtasks` 仍然保留，用于：
1. 在 active todo 下追加新阶段
2. 补充后续执行清单
3. 把 prepare 或执行阶段中新增的可执行步骤落进当前 todo

但它不再默认承担“失败后恢复”的专用语义。

## 8. 相关代码

- `app/tool/todo_tool/todo_tool.py`
- `app/core/runtime/todo_runtime_lifecycle.py`
- `app/core/runtime/agent_runtime.py`
