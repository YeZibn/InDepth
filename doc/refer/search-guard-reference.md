# InDepth Search Guard 参考文档

更新时间：2026-04-13

本文档描述 `app/tool/search_tool/search_guard.py` 的当前实现行为（含自动扩容预算）。

## 1. 目标与边界

Search Guard 用于约束检索类任务，核心目标：
1. 强制在检索前显式初始化门禁（时间基准 + 问题清单 + 预算 + 停止阈值）。
2. 在检索过程中执行预算与停止条件校验。
3. 把检索过程写入可观测事件与会话日志，支持复盘。

## 2. 核心数据结构

`SearchSession` 关键字段：
1. 基础预算：`max_rounds`、`max_seconds`、`rounds_used`、`created_at`。
2. 停止状态：`stopped`、`stop_reason`。
3. 进度状态：`answered_question_ids`、`stable_conclusion`。
4. 自动扩容配置：
- `auto_override_enabled`（默认 `true`）
- `auto_override_rounds_left_threshold`（默认 `1`）
- `auto_override_seconds_left_threshold`（默认 `120`）
- `auto_override_rounds_step`（默认 `1`）
- `auto_override_seconds_step`（默认 `180`）
- `auto_override_max_times`（默认 `4`）
- `auto_override_max_total_rounds`（默认 `6`）
- `auto_override_max_total_seconds`（默认 `1800`）
5. 自动扩容运行态：
- `auto_overrides_used`
- `auto_override_total_rounds`
- `auto_override_total_seconds`
6. 收益信号：
- `progress_update_count`
- `consecutive_no_gain_progress`

## 3. 工具与调用顺序

标准调用链：
1. `init_search_guard(...)`
2. `guarded_ddg_search(...)` / `guarded_url_search(...)`（可多轮）
3. `update_search_progress(...)`（每轮后上报进度）
4. `get_search_guard_status(...)`（可选调试）
5. `build_search_conclusion(...)`（收口）

预算不足时：
1. 自动扩容可用且未达上限时，系统自动小步扩容继续执行。
2. 自动扩容不可用时，返回阻断错误。
3. 调用 `request_search_budget_override(...)` 可手动扩容恢复会话。

## 4. 门禁逻辑

`check_gate(task_id)` 判定顺序：
1. 会话不存在：报错要求先初始化。
2. 已停止：直接返回 `Search is stopped: ...`。
3. 临近阈值：尝试自动扩容。
4. 轮次耗尽：先尝试自动扩容，失败则 `round budget exhausted`。
5. 时间耗尽：先尝试自动扩容，失败则 `time budget exhausted`。

## 5. 自动扩容逻辑

触发时机（任一满足）：
1. `rounds_left <= auto_override_rounds_left_threshold`
2. `seconds_left <= auto_override_seconds_left_threshold`

拒绝条件：
1. `auto_override_enabled == false`
2. `auto_overrides_used >= auto_override_max_times`
3. `consecutive_no_gain_progress >= 2`
4. 总扩容额度（rounds/seconds）已用完

执行效果：
1. `max_rounds += extra_rounds`，`max_seconds += extra_seconds`
2. 记录日志 `auto_budget_override`
3. 发事件 `search_budget_auto_overridden`
4. 清除 `stopped/stop_reason`

## 6. 进度上报与低收益判定

`update_search_progress(...)` 在写入进度时同步维护收益信号：
1. 若 `new_evidence_count > 0` 或覆盖增长（回答问题数增加）则视为有收益，`consecutive_no_gain_progress = 0`。
2. 否则 `consecutive_no_gain_progress += 1`。

该信号用于自动扩容的收益门槛。

## 7. 状态查询字段

`get_search_guard_status(task_id)` 除基础预算外，新增返回：
1. 自动扩容配置字段（阈值、步长、上限）
2. 自动扩容运行态（已用次数/总增量）
3. 收益信号（无收益连续次数、进度更新次数）

## 8. 观测事件

Search Guard 相关事件：
1. `search_guard_initialized`
2. `search_round_started`
3. `search_round_finished`
4. `search_budget_auto_overridden`
5. `search_stopped`

## 9. 常见阻断原因

1. `Search gate not initialized`：未先调用 `init_search_guard`。
2. `Search is stopped: ...`：会话已停止，需要检查 `stop_reason`。
3. `round budget exhausted`：自动扩容上限已达，需手动 override 或结束。
4. `time budget exhausted`：同上。

## 10. 代码与测试映射

实现：
1. `app/tool/search_tool/search_guard.py`

测试：
1. `tests/test_search_guard_auto_override.py`
