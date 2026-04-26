# S3-T1 AgentRuntime 职责拆解（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S3-T1`

## 1. 当前主职责

`AgentRuntime` 当前主要承担 6 类职责：

1. phase 编排：prepare / execute / finalize 切换
2. 主循环驱动：模型调用、tool calling、stop 收敛
3. prepare 规划：todo 现状扫描、prepare LLM / rule fallback、自动 plan
4. 状态收口：runtime_state、stop_reason、final_answer
5. 增强能力挂载：memory recall、user preference、todo session
6. 收尾链路：verification、postmortem、memory finalize、parallel finalizers

## 2. 代码热点

关键区域：

1. `PREPARING_PHASE_PROMPT` / `EXECUTING_PHASE_PROMPT` / `FINALIZING_PHASE_PROMPT`
2. `_run_prepare_phase*`
3. `run(...)`
4. `_run_finalizing_pipeline(...)`
5. `_handle_native_tool_calls(...)`
6. `_build_system_prompt(...)`

## 3. 当前问题

1. orchestration、policy、domain、infra 还混在一个类里
2. prepare 已经带副作用，不只是规划
3. finalizing 既做总结，又做验证和沉淀
4. memory / todo / verification 都仍由主 runtime 直接调度

## 4. 对后续的直接输入

这份拆解直接服务：

1. `S3-T2` 定义 v2 主控对象
2. `S3-T3` 定义 phase engine 接口
3. `S3-T4` 定义 step loop 最小职责
