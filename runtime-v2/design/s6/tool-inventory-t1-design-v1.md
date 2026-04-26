# S6-T1 Tool 全量分类表（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S6-T1`

## 1. 当前工具装配入口

核心入口：

1. `app/core/tools/registry.py`
2. `app/core/tools/adapters.py`
3. `app/core/tools/validator.py`

默认注册来自：

1. 基础工具
2. search guard 工具
3. subagent 工具
4. todo 工具
5. memory 查询工具

## 2. 当前工具分组

### 基础执行工具

1. `bash`
2. `read_file`
3. `write_file`
4. `get_current_time`
5. `history_recall`

### 记忆工具

1. `get_memory_card_by_id`

### 搜索工具

1. `search_guard`
2. `ddg_search`
3. `baidu_search`
4. `url_search`

### SubAgent 工具

1. 创建、运行、并行运行相关工具

### Todo 工具

1. `plan_task`
2. `update_task_status`
3. `get_next_task`
4. `generate_task_report`
5. 其他 subtask 维护工具

## 3. 当前分类问题

1. capability、workflow、orchestration 工具混在一起
2. runtime 仍然理解部分工具语义，尤其是 todo
3. tool result 协议虽然统一，但领域边界还不清楚

## 4. 对后续的直接输入

这份分类表直接服务：

1. `S6-T2` 统一 tool protocol
2. `S6-T3` runtime 与工具语义耦合策略
3. `S6-T4` 工具分域结构
