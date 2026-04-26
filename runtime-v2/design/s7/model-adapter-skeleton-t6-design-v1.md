# S7-T6 Model Adapter Skeleton（V1）

更新时间：2026-04-23  
状态：Draft  
对应任务：`S7-T6`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版 model adapter 的最小骨架。

目标是：

1. 明确 adapter 在模型接入层中的位置
2. 明确 adapter 与 provider、runtime、policy 的边界
3. 为后续不同模型实现提供统一接入骨架

## 2. 正式结论

本任务最终结论如下：

1. adapter 只负责把底层模型实现接成统一 `ModelProvider` 协议
2. adapter 不负责 prompt、策略和业务 fallback
3. 第一版允许一个 adapter 对应一个 provider 家族
4. adapter 可以暴露轻量能力信息
5. provider 选择权不在 adapter

## 3. Adapter 的定位

adapter 在 v1 中的定位是：

1. provider 接入层
2. 底层协议适配层
3. 能力描述入口

它不负责：

1. prompt assembly
2. generation config policy
3. budget policy
4. runtime orchestration
5. 业务语义 fallback

## 4. 推荐最小骨架

第一版建议至少包含：

1. `ModelProvider`
2. `ModelAdapter`
3. `ProviderCapabilities`
4. `ModelProviderRegistry`

## 5. ModelProvider

本任务沿用统一 provider 接口方向：

```ts
interface ModelProvider {
  generate(request: ModelRequest): ModelResult;
}
```

其中：

1. 输入是已准备好的模型请求
2. 输出是统一模型结果

## 6. ModelAdapter

`ModelAdapter` 的职责是：

1. 把底层 SDK / HTTP / mock 等实现包装成 `ModelProvider`
2. 屏蔽底层协议差异
3. 输出轻量能力描述

推荐最小接口方向：

```ts
interface ModelAdapter {
  build_provider(config: unknown): ModelProvider;
  get_capabilities(): ProviderCapabilities;
}
```

## 7. 一个 Adapter 对应一个 Provider 家族

本任务明确规定：

1. 第一版允许一个 adapter 对应一个 provider 家族

例如：

1. OpenAI adapter
2. Mock adapter
3. 未来其他 provider adapter

不建议：

1. 搞一个超大全能 adapter
2. 在同一个 adapter 中硬塞所有 provider 差异

## 8. ProviderCapabilities

adapter 可以暴露轻量能力信息。

第一版建议如下：

```ts
type ProviderCapabilities = {
  supports_structured_output: boolean;
  supports_tool_calling: boolean;
  supports_json_mode: boolean;
};
```

这些能力信息的作用是：

1. 让上层知道某个 provider 能做什么
2. 避免上层直接硬编码 provider 名字做判断

本任务明确规定：

1. 能力信息保持轻量
2. 不暴露过多 provider 内部细节

## 9. ModelProviderRegistry

第一版建议保留一个 provider registry。

推荐方向如下：

```ts
interface ModelProviderRegistry {
  register(provider_name: string, adapter: ModelAdapter): void;
  get(provider_name: string): ModelAdapter | null;
  list(): string[];
}
```

它的职责包括：

1. 注册 adapter
2. 按名字取 adapter
3. 提供 provider 目录

它不负责：

1. 选择用哪个 provider
2. 执行模型调用
3. 做策略切换

## 10. Provider 选择权

本任务明确规定：

1. provider 选择权不在 adapter
2. provider 选择权在上层 runtime / config / policy

这意味着：

1. adapter 只负责接入
2. 不负责决定“这次该用哪个 provider”

## 11. 与 Runtime 的关系

本任务与 `S7-T3` 对齐如下：

1. runtime 只消费统一 `ModelProvider`
2. runtime 不直接依赖底层 provider 实现
3. adapter 不反向读取 `RunContext`

## 12. 与 Verification 的关系

本任务明确规定：

1. final verification 复用同一 provider / adapter 骨架
2. 不为 verifier 另造一套 adapter 协议

差异只在于：

1. 调用入口不同
2. prompt 输入不同
3. 上层解释逻辑不同

## 13. 第一版边界

第一版明确不建议：

1. adapter 直接决定业务 fallback
2. adapter 直接拼 prompt
3. adapter 直接管理 budget policy
4. registry 直接选择 provider
5. 为每种上层场景再复制一套 adapter 协议

## 14. 对其他任务的直接输入

`S7-T6` 直接服务：

1. `S3-T5` step / orchestrator 实现
2. `S11-T7` verification skeleton
3. `S12-T7` 测试 skeleton

同时它直接依赖：

1. `S7-T3` model provider 边界
2. `S7-T4` generation config 规则
3. `S7-T5` context budget 策略

## 15. 本任务结论摘要

可以压缩成 5 句话：

1. adapter 只负责把底层实现接成统一 provider 协议
2. 一个 adapter 对应一个 provider 家族即可
3. adapter 可暴露轻量能力信息
4. provider 选择权仍在上层
5. verification 复用同一套 adapter 骨架
