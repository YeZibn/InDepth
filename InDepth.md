# InDepth 运行时执行协议（精简强化版）

目标：让执行可落地、可审计、可复用。

术语：
- MUST：强制，禁止违反。
- SHOULD：推荐，若不做需说明理由。
- MAY：按场景可选。

## 1. 启动门禁

任务开始前，Agent MUST 明确：
1. 任务目标
2. 时间基准（时区 + 截止时刻）
3. 执行范围
4. 约束条件
5. 交付标准
6. 验收口径

若边界不清、指标不明、上下文缺失，MUST 先澄清，再执行。

复杂任务启动时，SHOULD 同步完成：
- 用 `todo_tool` 做任务拆解
- 用记忆能力做历史经验检索

## 2. 时效任务强约束

凡包含“最新/近期/动态/趋势/新闻”等语义，检索前 MUST 通过四项门禁：
1. 时间基准已定义
2. 问题清单已定义（3-5 个核心问题）
3. 检索预算已定义（轮次或时长）
4. 停止阈值已定义（何时信息足够）

任一缺失：MUST NOT 启动检索。

输出 MUST 标注时间基准；MUST NOT 主观臆测“最新”。

### 2.1 检索预算与止损

1. 检索前 MUST 先写问题清单，禁止无目标泛搜。
2. 检索前 MUST 设预算。默认上限：单子任务最多 3 轮或 10 分钟（先到即止）。
3. 每轮 MUST 优先核心来源，再补充次级来源。
4. 每个结论点 SHOULD 控制在 2-3 个高质量来源。
5. 每轮结束 MUST 去重与裁剪，只保留与问题直接相关的信息。
6. 核心问题覆盖且结论稳定时 MUST 立即停止扩搜。
7. 超预算仍不充分时 MUST 输出：当前结论 + 信息缺口 + 后续建议。
8. MUST NOT 因“可能还有更多信息”无限追加轮次。
9. 若要突破预算，MUST 先记录：突破理由、追加预算、预期收益。

### 2.2 检索收敛格式

检索结果 MUST 统一为：
1. 核心结论
2. 关键证据
3. 信息缺口
4. 下一步建议

禁止无结构堆叠。

## 3. 拆解与执行边界

满足任一条件时，MUST 拆解任务：
- 至少 3 个可识别步骤
- 涉及跨文件或跨组件修改
- 预计执行超过 5 分钟
- 存在依赖或并行机会

拆解结果 MUST 覆盖完整链路：
- Agent 调度
- 工具/API 调用
- 数据/文件操作
- 状态更新
- 汇总交付

执行边界：
1. 后续动作 MUST 以子任务清单为执行依据。
2. 清单外动作 MUST 先补入清单再执行。
3. MUST NOT 跳过规划直接做未登记动作。

## 4. SubAgent 协同

角色职责：
- 主 Agent：调度、依赖管理、状态监控、汇总交付
- SubAgent：执行已分配子任务

主 Agent SHOULD NOT 在复杂任务中包揽全部动作（除非记录例外理由）。

### 4.1 创建决策

执行前，主 Agent MUST 先完成“是否创建 SubAgent”评估并记录。

满足任一条件时，SHOULD 创建 SubAgent：
- 存在 2 个及以上可并行子任务
- 子任务边界清晰可独立推进
- 子任务资源密集（大量检索/处理）
- 子任务需要专门工具或领域能力

可不创建，但 MUST 记录理由：
- 任务很小（< 5 分钟）
- 拆分成本高于并行收益
- 关键工具/上下文仅主 Agent 可用
- 当前链路对时延极敏感

### 4.2 高频协同要求（todo + SubAgent）

1. 拆解完成后，MUST 先把“创建/启动 SubAgent”写入 todo，再执行。
2. 并行流 SHOULD 拆成两步：
   - 创建 SubAgent 配置
   - 启动 SubAgent 执行
3. 主 Agent MUST 在关键节点同步状态：启动、完成、阻塞、恢复。
4. 不创建 SubAgent 时 MUST 记录原因。
5. 与 Agent 有关的配置动作 MUST 显式入 todo（角色、工具、I/O 约束、验收口径、并发参数）。

### 4.3 角色路由（显式必填）

调用 `create_sub_agent` 前，MUST 先确定并显式传入 `role`。
MUST NOT 使用 `auto` 或隐式路由。

允许角色：
- `researcher`
- `builder`
- `reviewer`
- `verifier`
- `general`

时机建议：
- `researcher`：外部检索、证据补全
- `builder`：实现类子任务（代码/文件/数据）
- `reviewer`：高风险变更前质量把关
- `verifier`：独立验收与约束核验
- `general`：通用或兜底执行

创建约束：
1. `reviewer` 与 `verifier` SHOULD NOT 做实现改动。
2. 同一子任务 MUST NOT 重复分配给多个角色（交叉验证除外）。
3. 创建 `reviewer/verifier` 时，MUST 在 todo 写清验收口径与输出格式。
4. `search_memory_cards` 默认仅推荐给 `researcher/reviewer/verifier`。

## 5. 状态管理与审计

状态更新 MUST 真实、及时：
1. 开始执行：`pending -> in-progress`
2. 执行完成：`completed`
3. 出现阻塞：MUST 回写状态并标注阻塞原因

执行依据：`app/tool/todo_tool/todo_tool.py`

## 6. 系统记忆（Memory / Knowledge）

最小目标：可检索、可触发、可评估。禁止文档堆积。

### 6.1 存储与入口

1. 统一载体：`memory_card`
2. 存储：`db/system_memory.db`（主表 `memory_card`）
3. 运行时会话记忆 MUST 按 Agent 类型聚合落盘：
   - 主 Agent：`db/runtime_memory_main_agent.db`
   - SubAgent：`db/runtime_memory_subagent_<role>.db`
4. 录入/查询统一入口：`memory_card_cli.py`（`upsert-json/search/due`）

### 6.2 触发与注入

1. 运行中可在 `pull_request/pre_release/postmortem` 阶段调用 `capture_runtime_memory_candidate`
2. `task_finished` 后，框架 MUST 强制沉淀一次 `postmortem` 记忆
3. Runtime 当前默认不做模型请求前自动注入
4. 若启用注入，MUST 保持“未命中不阻塞、内容摘要化”

### 6.3 观测与治理

记忆链路 MUST 记录：
- `memory_triggered`
- `memory_retrieved`
- `memory_decision_made`

事件 MUST 入库，并周期跟踪：命中率、采纳率、噪音率、新鲜度、到期治理。

## 7. Skill 主动选择

1. 任务开始时，Agent MUST 主动判断所需能力，不等待用户提示。
2. 复杂任务 SHOULD 组合多个能力模块。
3. 关键能力决策 MUST 可追溯（为何调用/为何不调用）。

## 8. 最小执行闭环

复杂任务至少完成以下闭环：
1. 前置校验
2. 任务拆解
3. SubAgent 评估
4. 执行与状态同步
5. 结果汇总与交付
6. 复盘沉淀

任一步缺失，MUST 在交付前补齐或说明原因。
