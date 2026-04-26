# S10-T1 当前 SubAgent 链路清单（V1）

更新时间：2026-04-24  
状态：Draft  
对应任务：`S10-T1`

## 1. 目标

本任务用于盘点当前项目中的 subagent 链路现状，并输出问题盘点，作为后续 `S10-T2 ~ S10-T7` 的输入。

本任务只回答三件事：

1. 当前 subagent 链路有哪些正式阶段
2. 当前 subagent 有哪些角色、状态、事件
3. 当前实现与新设计之间有哪些主要偏差

## 2. 正式结论

当前 subagent 链路已经具备以下 5 个正式阶段：

1. `create`
2. `role prompt build`
3. `runtime init`
4. `run`
5. `info / destroy`

但当前实现仍主要是：

1. 工具驱动的附属运行时
2. 尚未正式绑定到 task graph node

## 3. 现有链路总表

| link_stage | current_entry | current_object | current_state_holder | observability | main_issue |
|---|---|---|---|---|---|
| `create` | `create_sub_agent` | `SubAgentManager.create(...)` | `SubAgentManager._pool` | `subagent_created` | 仍是工具入口，不是 graph node 生命周期入口 |
| `role prompt build` | `SubAgent.__init__` | role prompt template + generated instructions | `SubAgent` | 无显式独立事件 | role prompt 已存在，但还未纳入 v2 正式 prompt 编排模型 |
| `runtime init` | `SubAgent.__init__` | `SubAgentRuntime` | `SubAgent.runtime` | 无显式独立事件 | 已有独立轻 runtime，但边界尚未正式化 |
| `run` | `run_sub_agent` / `SubAgentManager.run_task(...)` | `SubAgentRuntime.run(...)` | `AgentInstance.status / task_history` | `subagent_started / finished / failed` | 运行结果尚未正式回流到 task graph node |
| `info / destroy` | `list_sub_agents / get_sub_agent_info / destroy_sub_agent` | manager pool 操作 | `SubAgentManager._pool` | 无 destroy 事件 | 生命周期管理存在，但尚未与 node 生命周期对齐 |

## 4. 当前代码落点

当前 subagent 相关实现主要位于：

| 类型 | 代码位置 | 当前作用 |
|---|---|---|
| runtime agent | `app/agent/sub_agent.py` | 定义 `SubAgent`，负责 role prompt、runtime 构建、工具绑定 |
| lightweight runtime | `app/agent/sub_agent_runtime.py` | 轻量执行循环，不带 prepare/taskgraph/finalize 主链路 |
| tool facade | `app/tool/sub_agent_tool/sub_agent_tool.py` | 暴露 create/run/list/destroy/info 等工具入口 |
| role prompts | `app/agent/prompts/sub_agent_roles/*` | 提供 role 模板 |

## 5. 当前角色模型

当前 subagent role 至少包括：

| role | 当前用途 | 当前落点 |
|---|---|---|
| `general` | 通用型子代理 | `sub_agent.py` + `general.md` |
| `researcher` | 检索/调研型子代理 | `sub_agent.py` + `researcher.md` |
| `builder` | 实现型子代理 | `sub_agent.py` + `builder.md` |
| `reviewer` | 审查型子代理 | `sub_agent.py` + `reviewer.md` |
| `verifier` | 验证型子代理 | `sub_agent.py` + `verifier.md` |

## 6. 当前状态模型

当前 manager 侧实例状态主要包括：

| 状态字段 | 当前值 | 含义 |
|---|---|---|
| `status` | `idle / running / completed / error` | 当前子代理实例运行状态 |
| `task_history` | 列表 | 历次执行记录 |
| `task_id` | 字符串 | 观测与归档引用 |
| `role` | 枚举字符串 | 当前子代理角色 |

当前判断：

1. 这些状态更像 manager 内部状态
2. 还不是 v2 正式 graph/state 模型的一部分

## 7. 当前事件链

当前已显式存在的 subagent 事件如下：

| event_type | 触发位置 | 当前作用 |
|---|---|---|
| `subagent_created` | create | 标记实例创建 |
| `subagent_started` | run start | 标记运行开始 |
| `subagent_finished` | run success | 标记运行成功结束 |
| `subagent_failed` | run failure | 标记运行失败 |

当前判断：

1. 事件链已经有雏形
2. 但还没有和 task graph node 生命周期正式对齐

## 8. 当前工具入口

当前对外暴露的 subagent 工具主要包括：

| tool_name | 当前作用 |
|---|---|
| `create_sub_agent` | 创建实例 |
| `run_sub_agent` | 运行单个 subagent |
| `run_sub_agents_parallel` | 并行运行多个 subagent |
| `list_sub_agents` | 查看活跃实例 |
| `destroy_sub_agent` | 销毁单个实例 |
| `destroy_all_sub_agents` | 清理全部实例 |
| `get_sub_agent_info` | 查看详细信息 |

当前判断：

1. 这些入口说明 subagent 现在首先是工具域能力
2. 还不是 graph 内正式协作对象

## 9. 当前实现的主要问题

结合当前代码与已收敛的新设计，主要问题如下：

1. subagent 仍是工具驱动的附属运行时，不是 graph 内正式协作对象
2. create / run / destroy 还没有对应到显式 node 生命周期
3. 子代理结果回流目前还是 tool/result 级，不是正式 node/state 级
4. manager 内部状态与正式 runtime 状态系统尚未打通
5. role prompt 已存在，但尚未纳入 v2 正式 subagent prompt 模型

## 10. 对后续任务的直接输入

`S10-T1` 直接服务：

1. `S10-T2` subagent 运行模型
2. `S10-T3` subagent 与 task graph 的关系
3. `S10-T4` subagent 角色模型
4. `S10-T5` subagent 结果/证据/状态回流

## 11. 本任务结论摘要

可以压缩成 6 句话：

1. 当前 subagent 链路已经具备 create、prompt build、runtime init、run、destroy 五段
2. 当前 role 至少包括 `general / researcher / builder / reviewer / verifier`
3. 当前 manager 已有内部状态和 task history
4. 当前 observability 已有四个基础 subagent 事件
5. 当前 subagent 首先仍是工具域能力
6. 它尚未正式绑定到 task graph node 生命周期
