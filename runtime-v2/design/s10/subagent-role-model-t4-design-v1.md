# S10-T4 SubAgent 角色模型（V1）

更新时间：2026-04-24  
状态：Draft  
对应任务：`S10-T4`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 subagent 的正式角色模型。

本任务不再讨论：

1. subagent 的运行模型
2. subagent 与主任务图的绑定结构
3. subagent 结果回流字段细节
4. subagent 失败、超时、取消策略

这里只回答五件事：

1. role 在 v2 中到底是什么
2. 第一版 role 是否允许动态新增
3. role 到底约束哪些东西
4. 主链 step 如何选择 role
5. role 是否需要正式结构定义

## 2. 正式结论

第一版正式结论如下：

1. `subagent role` 在 v2 中定义为正式能力类型
2. `role` 不是单纯 prompt 标签
3. 第一版主链只允许使用已创建角色
4. 第一版不允许运行时自由发明新角色
5. 主链 `step` 直接选择正式角色
6. 第一版不增加“任务意图 -> 角色映射”的中间层
7. 未来如果引入再规划机制，应允许引入新角色，但不属于第一版范围
8. role 约束是多方面的，不只约束 prompt
9. 第一版 role 至少同时约束：
   - `prompt`
   - `tool`
   - `skill`
   - 输出预期
   - 行为边界
10. 第一版不拆“能力边界”和“权限边界”两套系统
11. 第一版统一收在一个 `role definition` 中
12. role 必须有正式结构定义
13. 第一版正式角色集先采用：
   - `general`
   - `researcher`
   - `builder`
   - `reviewer`
   - `verifier`
14. 第一版虽然只使用固定内建角色集，但结构上按“可注册角色定义”设计

## 3. Role 的正式定位

第一版中，`role` 的正式定位是：

1. subagent 的能力类型
2. 主链对 subagent 执行方式的正式约束入口
3. subagent 执行边界的统一定义单元

这意味着：

1. role 不只是“换一段 prompt”
2. role 也不只是“换一个名字”
3. role 是主链在创建和配置 subagent 时的正式能力配置选择

## 4. 为什么不是 Prompt 标签

第一版明确规定：

1. role 不能退化成 prompt 文件名
2. role 不能只靠隐式命名约定存在

原因如下：

1. role 除了影响 prompt，还会影响 tool、skill 和行为边界
2. 如果 role 只是 prompt 标签，后续很难稳定挂接更多约束
3. `S10` 需要的是可治理的正式协作角色，而不是一组散落模板

因此 role 应理解为：

1. 一个能力类型
2. 一个正式配置单元
3. 一个可被主链 step 显式选择的协作角色

## 5. 第一版角色集

第一版正式角色集采用以下 5 个内建角色：

1. `general`
2. `researcher`
3. `builder`
4. `reviewer`
5. `verifier`

这组角色的定位如下：

### 5.1 `general`

作用：

1. 通用型子代理
2. 适合边界不够明确、但仍需要委派的局部工作

### 5.2 `researcher`

作用：

1. 面向检索、资料整理、事实收集、对比分析
2. 不承担最终实现决策

### 5.3 `builder`

作用：

1. 面向实现、修改、产出具体工作结果
2. 不承担最终验收裁决

### 5.4 `reviewer`

作用：

1. 面向审查已有结果
2. 负责识别问题、风险、回归点或缺口

### 5.5 `verifier`

作用：

1. 面向验证产物是否满足要求
2. 偏向测试、证据核对、完成度判断

## 6. 第一版为何采用固定内建角色

第一版主链只允许使用已创建角色，不允许运行时自由发明新角色。

原因如下：

1. 第一版首先要保证角色语义稳定
2. 角色若可在运行时随意创建，约束边界会迅速失控
3. tool、skill、prompt 和行为边界都需要稳定挂点
4. 先用固定角色集能降低 `S10` 第一版的复杂度

因此第一版正式规定：

1. 主链只能从已有角色集中做选择
2. 不允许 step 临时拼一个新 role name
3. 不允许通过 prompt 临时“伪造”一个新角色

## 7. 为什么未来仍要允许扩展

虽然第一版采用固定内建角色集，但本任务明确保留一个后续方向：

1. 未来如果引入再规划机制，应允许新增角色

原因如下：

1. 随着 graph、memory、skills 和 verification 进一步收敛，可能出现更细的协作角色需求
2. 如果结构上完全写死成纯枚举，后续扩展成本会偏高

因此第一版的正式要求是：

1. 当前使用固定内建角色集
2. 但结构上按“可注册角色定义”设计

## 8. 主链如何选择 Role

第一版中，主链 `step` 直接选择正式角色。

也就是说：

1. `step` 明确决定使用哪个 role
2. 不增加“任务意图 -> role 映射”的中间层

这样做的原因是：

1. 第一版先保持控制链清晰
2. 避免再引入一层隐式推断逻辑
3. 便于把 role 选择和当前 node 目标直接对齐

第一版因此不引入：

1. role planner
2. role selector service
3. 单独的“意图标签 -> 角色映射表”

## 9. Role 约束范围

第一版中，role 的约束范围至少包括以下 5 类：

1. `prompt`
2. `tool`
3. `skill`
4. 输出预期
5. 行为边界

### 9.1 `prompt`

role 负责决定：

1. subagent 的角色提示焦点
2. 它被要求如何理解自己的任务

### 9.2 `tool`

role 负责决定：

1. 允许使用哪些工具域
2. 不应使用哪些工具域

### 9.3 `skill`

role 负责决定：

1. 哪些 skill 可以默认挂给该角色
2. 哪些 skill 不应默认暴露

### 9.4 输出预期

role 负责决定：

1. 该角色产出更偏实现、审查、验证还是信息整理
2. 主链在 `collect` 时应期待什么形态的结果

### 9.5 行为边界

role 负责决定：

1. 该角色可以推进到什么程度
2. 哪些决定不能由它做
3. 哪些动作必须回到主链裁决

## 10. 不拆能力边界与权限边界

第一版明确规定：

1. 不单独设计“能力边界系统”
2. 不单独设计“权限边界系统”
3. 两者统一收在一个 `role definition` 中

原因如下：

1. 第一版先求清晰和稳定
2. 如果一开始拆成两套系统，复杂度会上升过快
3. 当前 role 规模还小，没有必要过早抽象

## 11. Role Definition 的正式结构

第一版规定，role 必须有正式结构定义。

最小结构如下：

```ts
type SubAgentRoleDefinition = {
  role_name: string;
  purpose: string;
  prompt_profile: string;
  allowed_tools: string[];
  allowed_skills: string[];
  output_expectation: string;
  behavior_constraints: string[];
};
```

## 12. 各字段定位

### 12.1 `role_name`

作用：

1. 稳定标识角色

### 12.2 `purpose`

作用：

1. 定义该角色的核心任务定位

### 12.3 `prompt_profile`

作用：

1. 定义该角色的 prompt 焦点或提示模板挂点

### 12.4 `allowed_tools`

作用：

1. 定义该角色允许使用的工具范围

### 12.5 `allowed_skills`

作用：

1. 定义该角色允许挂接的 skill 范围

### 12.6 `output_expectation`

作用：

1. 定义主链期望它产出什么类型的结果

### 12.7 `behavior_constraints`

作用：

1. 定义该角色的行为边界和禁止事项

## 13. 第一版不做的事情

第一版中，`S10-T4` 明确不做以下设计：

1. 不允许运行时自由创建新角色
2. 不引入 role 自动规划或自动映射系统
3. 不把 role 退化成单纯 prompt 文件名
4. 不拆成能力系统和权限系统两套定义

## 14. 与其他任务的关系

`S10-T4` 直接依赖：

1. `S10-T1` 当前 subagent 链路清单
2. `S10-T2` subagent 运行模型
3. `S10-T3` subagent 与主任务图关系
4. `S9` skill 系统设计

`S10-T4` 直接服务：

1. `S10-T5` subagent 结果、证据、状态回流
2. `S10-T6` subagent 失败、超时、取消规则
3. `S10-T7` subagent skeleton
4. subagent role prompt 与 tool/skill 挂载实现

## 15. 本任务结论摘要

可以压缩成 6 句话：

1. `subagent role` 在 v2 中是正式能力类型，不是 prompt 标签
2. 第一版只允许使用已创建角色，不允许运行时自由发明新角色
3. 主链 `step` 直接选择正式 role，不增加中间映射层
4. role 至少同时约束 prompt、tool、skill、输出预期和行为边界
5. 第一版正式角色集采用 `general / researcher / builder / reviewer / verifier`
6. 第一版虽使用固定内建角色集，但结构上按可注册角色定义设计
