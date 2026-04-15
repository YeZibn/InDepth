# Hermes Agent 多维度开发报告（样本）

> 文档目的：提供一份可复用、可落地、可审查的工程报告模板，作为 Hermes Agent 后续迭代、评审与上线前检查的参考。
>
> 适用范围：CLI、Gateway、Tools、Agent Loop、Profile、多平台适配、测试与发布流程。

## 1. 执行摘要（Executive Summary）

Hermes Agent 是一个以工具调用（Tool Calling）为核心的多平台智能体系统，架构上具备以下特点：

- 主循环清晰：`AIAgent.run_conversation()` 负责模型调用、工具执行与结果回填。
- 扩展路径标准化：新工具接入有固定“三步法”（工具文件 + discovery import + toolset 挂载）。
- 跨端一致性强：Slash 命令由中心注册表统一派生到 CLI、Gateway、Autocomplete、帮助菜单。
- 运行隔离完善：Profile 机制通过 `HERMES_HOME` 提供配置、会话、记忆、技能与网关状态隔离。
- 成本控制意识强：强调 prompt caching 稳定性，禁止会话中途破坏缓存前提。

总体判断：该项目具备中大型 Agent 工程的核心骨架，适合持续演进，但对“路径规范、全局状态、配置一致性、缓存纪律”有较高工程约束要求。

---

## 2. 系统架构维度

### 2.1 核心分层

- Agent 层：`run_agent.py`（主会话循环、消息编排）
- 工具层：`tools/registry.py` + `tools/*.py`（工具注册、可用性检查、分发）
- 编排层：`model_tools.py`（工具发现与函数调用处理）
- 交互层：`cli.py` + `hermes_cli/*`（CLI、命令系统、皮肤与配置）
- 接入层：`gateway/*`（Telegram/Discord/Slack/WhatsApp 等平台适配）
- 存储层：`hermes_state.py`（会话持久化、FTS5 搜索）
- 支撑层：上下文压缩、prompt caching、模型元数据、skills、trajectory。

### 2.2 关键依赖链

```text
tools/registry.py
  -> tools/*.py
  -> model_tools.py
  -> run_agent.py / cli.py / batch_runner.py / environments
```

说明：该链路是排障和扩展的主线。多数“工具不可见/不可调用”问题都可沿此链快速定位。

### 2.3 主要优势

- 低耦合工具接入。
- 统一命令元数据驱动（减少多端重复维护）。
- 架构职责边界明确，便于多人并行开发。

### 2.4 潜在复杂点

- 配置加载存在多入口（CLI、setup/tools 子命令、gateway 直读），易出现行为漂移。
- 进程级全局状态（如 `_last_resolved_tool_names`）在子代理并发场景有时序风险。

---

## 3. 安全维度

### 3.1 威胁面梳理

- 终端工具：命令注入、越权执行、危险命令误触发。
- 网关接入：多平台 token 泄露、重复启动冲突、消息回放。
- 文件工具：路径遍历、敏感文件误读误写。
- 外部服务：第三方 API Key 泄露、依赖供应链风险。

### 3.2 现有安全设计（基于代码组织）

- `tools/approval.py`：危险命令检测与审批流程。
- 环境变量分层：`~/.hermes/.env` + 可选变量白名单管理。
- 网关适配建议使用 scoped lock（同 token 多 profile 互斥）。
- 工具可用性检查（`check_requirements` + `requires_env`）避免无凭据调用。

### 3.3 安全改进建议

- 对 terminal/file tool 增加统一审计日志（谁、何时、调用了什么、结果如何）。
- 为高风险工具建立 denylist + allowlist 双机制（例如 shell 重定向/网络外联策略）。
- 引入“最小权限”默认值：新工具默认禁用，显式启用后才可用。
- 网关平台增加凭据轮换与失效告警流程。

### 3.4 上线前安全检查清单

- [ ] 新增工具是否定义了 `check_requirements` 与 `requires_env`
- [ ] 是否存在硬编码密钥或路径
- [ ] 是否覆盖危险命令审批路径
- [ ] 是否记录可追溯审计日志
- [ ] 是否验证多 profile 同 token 互斥

---

## 4. 记忆与上下文维度

### 4.1 记忆构成

- 会话历史：消息序列（OpenAI 格式）。
- 长期状态：SessionDB（SQLite + FTS5）。
- 技能注入：来自 `~/.hermes/skills/`，按用户消息方式注入。
- 轨迹：`trajectory` 辅助追踪与回放。

### 4.2 关键约束（高优先级）

项目明确规定：**Prompt Caching 不可被中途破坏**。

禁止行为包括：

- 会话中途修改历史上下文语义。
- 会话中途变更工具集。
- 会话中途重建系统提示或重新加载记忆。

仅允许在“上下文压缩”机制下做受控调整。

### 4.3 风险点

- 过度压缩可能损失关键约束信息。
- 技能文本注入若不做去重，可能重复污染上下文。
- 会话历史膨胀导致响应时延与成本上升。

### 4.4 优化建议

- 为压缩策略建立可回归评估集（准确性/完整性/成本三指标）。
- 为“系统约束片段”设置压缩豁免标签。
- 对技能注入内容做哈希去重与版本标记。

---

## 5. 工具生态与可扩展性维度

### 5.1 新工具接入标准流程

1. 新建 `tools/your_tool.py`，注册 schema、handler、requirements。
2. 在 `model_tools.py` 的 `_discover_tools()` 中加入 import。
3. 在 `toolsets.py` 中加入对应 toolset（核心或新增）。

### 5.2 工程规范关键点

- handler 返回值必须是 JSON 字符串。
- 工具 schema 中涉及用户路径展示时，使用 `display_hermes_home()`。
- 工具持久化状态路径必须使用 `get_hermes_home()`，禁止硬编码 `~/.hermes`。
- schema 描述不要硬编码跨工具依赖，避免模型调用不可用工具。

### 5.3 建议新增机制

- Tool Capability Matrix（按平台/凭据/配置动态出图）。
- 工具级 SLA 指标（成功率、延迟、错误码分布）。
- “灰度启用”开关：新工具先在限定 profile 平台试运行。

---

## 6. 命令系统与多平台一致性维度

### 6.1 现状

- `COMMAND_REGISTRY` 是单一真相源。
- CLI dispatch、Gateway dispatch、help、Telegram command、Slack mapping、autocomplete 均自动派生。

### 6.2 价值

- 显著降低命令新增/别名新增的人为遗漏风险。
- 文档、帮助、实际行为一致性高。

### 6.3 风险与建议

- 命令语义变更需强制更新回归测试（CLI + Gateway）。
- 对 config-gated command 增加可视化状态提示，减少“命令存在但不可用”的困惑。

---

## 7. 配置与 Profile 多实例维度

### 7.1 核心原则

- 所有状态路径走 `get_hermes_home()`。
- 所有用户可见路径走 `display_hermes_home()`。
- Profile 根目录是 HOME 锚定（用于跨 profile 可见性）。

### 7.2 常见错误

- 硬编码 `Path.home() / ".hermes"`。
- 测试只 mock `Path.home()`，但未设置 `HERMES_HOME`。

### 7.3 建议实践

- 引入静态扫描规则：阻止新代码中出现 `".hermes"` 硬编码。
- 在 PR 模板中加入 profile-safe checklist。

---

## 8. 可观测性与运维维度

### 8.1 建议最小可观测集

- 会话级：请求量、平均轮次、工具调用次数、失败率。
- 工具级：耗时分位数（P50/P95）、异常类型、重试效果。
- 平台级：Gateway 连接稳定性、重连次数、消息延迟。
- 成本级：token 用量、缓存命中率、压缩触发率。

### 8.2 后台进程通知策略

已有 `display.background_process_notifications` 多级配置（`all/result/error/off`），建议默认按平台场景调优：

- 人机交互密集平台：`result`
- 自动化/监控平台：`error`

### 8.3 事故演练建议

- 模拟 API 失败、token 失效、工具超时、gateway 断连。
- 每次演练产出 runbook：发现、缓解、恢复、复盘。

---

## 9. 测试与质量保障维度

### 9.1 分层测试策略

- 单元测试：工具 handler、配置解析、命令解析。
- 集成测试：Agent loop + tool dispatch + state store。
- 平台测试：gateway adapters。
- 回归测试：高风险路径（profile、安全审批、prompt caching）。

### 9.2 推荐门禁

- 提交前跑 targeted tests；合并前跑全量 `pytest tests/ -q`。
- 新工具必须附最小可用测试（成功 + 失败 + 无凭据）。
- 涉及 profile 代码必须覆盖 profile fixture。

### 9.3 残余风险

- 多平台适配差异在本地 CI 不易完整覆盖。
- LLM 行为波动可能引入“非确定性回归”，需增加行为基线样本。

---

## 10. 研发流程与治理维度

### 10.1 建议研发流程

1. 需求分解：影响模块、风险评级、回滚策略。
2. 设计评审：特别检查 caching、profile、安全边界。
3. 实现：遵守三大硬约束（路径、缓存、命令注册）。
4. 验证：分层测试 + 手工冒烟。
5. 发布：灰度、监控、回滚预案。
6. 复盘：缺陷归因与规范更新。

### 10.2 Code Review 关注点

- 是否引入 `~/.hermes` 硬编码。
- 是否破坏会话中缓存前提。
- 是否新增跨工具 schema 硬编码引用。
- 是否考虑子代理与全局状态互斥。
- 是否补充最小可复现测试。

---

## 11. 未来演进建议（Roadmap）

### 11.1 短期（1-2 迭代）

- 建立 profile-safe 静态检查。
- 建立工具级审计日志统一格式。
- 为高风险工具新增审批与告警面板。

### 11.2 中期（1-2 月）

- 完善 observability 看板（成本/稳定性/成功率）。
- 推出 Tool Capability Matrix 自动生成。
- 构建上下文压缩质量评测基准。

### 11.3 长期（季度）

- 引入策略化工具路由（按成本/置信度/延迟）。
- 建立跨平台一致性测试沙箱。
- 形成“规范即检查器”体系（lint + CI policy gate）。

---

## 12. 附录 A：开发者快速检查表

### 12.1 新增工具

- [ ] `tools/xxx.py` 已注册 schema/handler/check
- [ ] `model_tools.py` 已 discover import
- [ ] `toolsets.py` 已挂载
- [ ] 返回值统一 JSON 字符串
- [ ] 增加成功/失败/无凭据测试

### 12.2 涉及路径与配置

- [ ] 使用 `get_hermes_home()` 读写状态
- [ ] 使用 `display_hermes_home()` 做展示
- [ ] 无 `~/.hermes` 或 `Path.home()/".hermes"` 硬编码

### 12.3 涉及会话与记忆

- [ ] 未在会话中途破坏 prompt caching 前提
- [ ] 上下文压缩策略可解释且可回归
- [ ] 技能注入不重复、不污染关键约束

### 12.4 涉及安全

- [ ] 危险命令走审批
- [ ] 凭据仅走环境变量与配置，不入库不入日志
- [ ] 关键操作具备审计轨迹

---

## 13. 附录 B：可复用报告模板（供后续项目复制）

可按以下骨架快速复制：

1. 执行摘要
2. 架构现状
3. 安全评估
4. 记忆与上下文策略
5. 扩展性与工具生态
6. 配置与多实例隔离
7. 可观测性与运维
8. 测试质量与残余风险
9. 治理流程与评审标准
10. 路线图与下一步
11. 检查清单与附录

---

## 14. 结论

Hermes Agent 的工程基因是“强扩展 + 强约束”。

若团队坚持以下三条红线，可显著降低演进成本：

- 路径与 profile 规范不破坏。
- prompt caching 约束不破坏。
- 命令与工具注册链路不绕过。

在此基础上补齐安全审计、可观测性与策略化治理，系统可从“可用”走向“可持续可靠”。
