# User Preferences

meta:
- version: 1
- updated_at: 2026-04-20T23:34:32+08:00
- enabled: true

## preferences

### domain_expertise
- value: [C, 终端界面程序, 菜单式计算器]
- source: llm_extract_v1
- confidence: 0.97
- updated_at: 2026-04-20T20:52:04+08:00
- note: evidence=在 work/c_ui 下实现一个简单的 C 终端界面程序，建议做成菜单式计算器

### goal_long_term
- value: 做一个C界面，同时加上一个README，两个放到各自目录下
- source: llm_extract_v1
- confidence: 0.93
- updated_at: 2026-04-20T20:55:22+08:00
- note: evidence=我希望做一个c界面，同时加上一个readme，两个放到个子目录下

### interest_topics
- value: [README.md编写, 项目说明, 目录结构, 编译命令, 运行方法, 功能说明]
- source: llm_extract_v1
- confidence: 0.95
- updated_at: 2026-04-20T20:51:42+08:00
- note: evidence=请在 work/docs 下编写 README.md，说明这是一个简单 C 界面程序项目，并包含目录结构、编译命令、运行方法、功能说明。请直接创建文件，并在完成后返回文件路径与摘要。

### job_role
- value: 程序员
- source: llm_extract_v1
- confidence: 0.98
- updated_at: 2026-04-16T00:36:16+08:00
- note: evidence=我是一名程序员

### language_preference
- value: 中文
- source: llm_extract_v1
- confidence: 0.99
- updated_at: 2026-04-17T20:17:00+08:00
- note: evidence=你好啊

### response_style
- value: [请直接创建文件, 完成后返回文件路径、核心功能、编译命令]
- source: llm_extract_v1
- confidence: 0.96
- updated_at: 2026-04-20T20:52:04+08:00
- note: evidence=请直接创建文件，并在完成后返回文件路径、核心功能、编译命令

### tooling_stack
- value: [CLI, README]
- source: llm_extract_v1
- confidence: 0.93
- updated_at: 2026-04-20T23:34:32+08:00
- note: evidence=补充一个cli交互，同时补充一个readme
