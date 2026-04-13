# InDepth Search Guard 自动扩容预算设计稿 V1

更新时间：2026-04-13  
状态：V1 已实现（2026-04-13）

## 1. 背景

当前 `search_guard` 在预算耗尽时会直接停止：
1. 轮次耗尽：`round budget exhausted`
2. 时间耗尽：`time budget exhausted`

继续检索只能依赖手动调用 `request_search_budget_override`。这在长链路调研任务中容易造成中断，且用户期望“预算即将耗尽时可以自主扩容”。

## 2. 目标

V1 目标：
1. 在“临近耗尽”阶段自动小步扩容，避免硬中断。
2. 保持 guard 的可控性，避免无限扩容。
3. 扩容行为可观测、可审计、可解释。
4. 保持手动扩容工具兼容，不破坏现有调用方式。

## 3. 非目标

V1 不做：
1. 不接入外部审批流或人审系统。
2. 不改变 `guarded_ddg_search/guarded_url_search` 的核心输入输出结构。
3. 不用复杂打分模型判断“收益”，仅使用轻量启发式信号。

## 4. 核心策略

采用“三段式”策略：自动扩容 + 硬上限 + 收益门槛。

1. 触发条件（任一满足）：
- `rounds_left <= auto_override_rounds_left_threshold`（默认 1）
- `seconds_left <= auto_override_seconds_left_threshold`（默认 120）

2. 收益门槛：
- 如果连续 2 次 `update_search_progress` 都没有新增证据且没有覆盖增长（`consecutive_no_gain_progress >= 2`），禁止自动扩容。

3. 上限控制：
- 每次自动扩容步长：`+auto_override_rounds_step`（默认 1）、`+auto_override_seconds_step`（默认 180）
- 自动扩容次数上限：`auto_override_max_times`（默认 4）
- 自动扩容总增量上限：`auto_override_max_total_rounds`（默认 6）、`auto_override_max_total_seconds`（默认 1800）

4. 兜底：
- 超过自动扩容上限后保持原行为，返回 budget exhausted。
- 手动 `request_search_budget_override` 始终可用。

## 5. 数据结构变更

`SearchSession` 新增字段：
1. 自动扩容配置：
- `auto_override_enabled`
- `auto_override_rounds_left_threshold`
- `auto_override_seconds_left_threshold`
- `auto_override_rounds_step`
- `auto_override_seconds_step`
- `auto_override_max_times`
- `auto_override_max_total_rounds`
- `auto_override_max_total_seconds`

2. 自动扩容运行态：
- `auto_overrides_used`
- `auto_override_total_rounds`
- `auto_override_total_seconds`

3. 收益信号：
- `consecutive_no_gain_progress`
- `progress_update_count`

## 6. 运行逻辑

1. `check_gate` 在预算判定前先尝试“临近耗尽自动扩容”。
2. 若已达硬耗尽（round/time），再尝试一次自动扩容兜底。
3. 自动扩容成功后：
- 清除 stopped 状态
- 记录 `auto_budget_override` 日志
- 发出 `search_budget_auto_overridden` 观测事件
4. 自动扩容失败则维持现有阻断语义。

## 7. 接口与兼容

1. `init_search_guard` 新增可选参数（均有默认值），保持旧调用不受影响。
2. `get_search_guard_status` 增加自动扩容相关状态字段，便于调试与观测。
3. `request_search_budget_override` 不变，仍可在自动上限后继续人工扩容。

## 8. 可观测性

新增事件：`search_budget_auto_overridden`，payload 包含：
1. `trigger`
2. `auto_overrides_used`
3. `extra_rounds`
4. `extra_seconds`
5. `max_rounds`
6. `max_seconds`

## 9. 测试要求

新增最小回归集：
1. 临近轮次耗尽时自动扩容成功。
2. 达到自动扩容上限后，预算耗尽仍应阻断。
3. 自动扩容上限触达后，手动扩容仍可恢复会话。
4. 连续低收益信号达到阈值时，自动扩容应被拒绝。

## 10. 风险与边界

1. 收益门槛依赖 `update_search_progress` 调用质量；若调用缺失，系统会更倾向于放行自动扩容。
2. 时间阈值设置过大可能造成过早扩容；V1 采用保守默认值并支持参数覆盖。
3. 多线程/并发调用场景下当前管理器无锁；V1 与现有实现保持一致，后续可在 V2 引入锁。

## 11. 实施清单

1. 修改 `app/tool/search_tool/search_guard.py`：
- 扩展 `SearchSession`
- 实现自动扩容判定与执行
- 增加状态字段与观测事件
- 扩展 `init_search_guard` 参数校验

2. 新增 `tests/test_search_guard_auto_override.py`：
- 覆盖触发、限流、兜底、兼容路径
