# S5-T1 Todo 体系用途分析（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S5-T1`

## 1. 当前涉及模块

1. `app/core/todo/models.py`
2. `app/core/todo/service.py`
3. `app/core/runtime/todo_session.py`
4. `app/core/runtime/todo_runtime_lifecycle.py`
5. `app/tool/todo_tool/todo_tool.py`
6. `todo/` 目录任务文件

## 2. 当前真实用途

todo 现在不只是计划列表，它实际承担：

1. 任务拆分
2. active subtask 定位
3. 执行阶段绑定
4. 恢复执行上下文
5. subagent / followup 动作挂点
6. 任务状态可观测性

## 3. 当前两层混合

### 用户可见语义

1. task / subtask 列表
2. 状态流转
3. markdown 任务文件

### runtime 内部语义

1. active todo context
2. binding_required
3. execution_phase
4. prepare 自动承接与自动废弃

## 4. 当前问题

1. todo 既像业务对象，又像 runtime 执行图
2. 文件格式、工具协议、runtime 状态三层还没分离
3. 当前已经接近 task graph，但名字和抽象仍停留在 todo

## 5. 对后续的直接输入

这份分析直接服务：

1. `S5-T2` todo / task graph 命名决策
2. `S5-T3` 最小执行单元定义
3. `S5-T4` 执行图关系模型定义
