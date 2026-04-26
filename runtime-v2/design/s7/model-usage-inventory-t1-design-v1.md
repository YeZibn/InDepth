# S7-T1 模型调用场景清单（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S7-T1`

## 1. 当前模型接入层

主要模块：

1. `app/core/model/base.py`
2. `app/core/model/http_chat_provider.py`
3. `app/core/model/mock_provider.py`

基础对象：

1. `ModelProvider`
2. `ModelOutput`
3. `GenerationConfig`

## 2. 当前主要调用场景

1. 主 runtime step loop 调用主模型
2. prepare 阶段调用 planner 模型
3. clarification judge 调用 mini model
4. user preference extract 调用抽取模型
5. verifier / LLM judge 调用评估模型
6. memory metadata / compression 相关辅助模型调用

## 3. 当前问题

1. 多模型角色已经出现，但还没有正式角色分层
2. provider 和 runtime policy 仍然耦合
3. generation config 的归属还不统一

## 4. 对后续的直接输入

这份清单直接服务：

1. `S7-T2` 模型角色划分
2. `S7-T3` model provider 边界
3. `S7-T4` generation config 规则
