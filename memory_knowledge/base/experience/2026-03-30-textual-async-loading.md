# Textual TUI 异步数据加载卡顿问题

## 问题
在开发 Textual TUI 应用时，数据加载会导致界面卡顿，用户无法进行其他操作。

具体表现：
- 启动应用时，界面白屏等待数据加载完成
- 刷新数据时，整个界面无响应
- 用户无法在加载过程中进行其他操作

触发条件：
- 在 `on_mount` 生命周期中直接调用同步数据加载
- 数据量较大时（>100条记录）卡顿明显

## 解决过程

1. **尝试方案1：使用 asyncio.sleep**（失败）
   - 在数据加载过程中插入 sleep
   - 结果：只是延迟了卡顿，没有解决问题

2. **尝试方案2：使用 Thread**（部分成功）
   - 在后台线程中加载数据
   - 结果：可以工作，但需要手动处理线程安全，代码复杂

3. **最终方案：使用 Textual 的 Worker**（成功）
   - 使用 `@work` 装饰器将数据加载放到后台
   - 使用 `self.call_from_thread` 更新 UI
   - 结果：界面流畅，代码简洁

## 结果

最终解决方案：
```python
from textual.work import work

class MyApp(App):
    @work
    async def load_data(self):
        data = await fetch_data()
        self.call_from_thread(self.update_table, data)
```

关键收获：
- Textual 的 Worker 是处理后台任务的最佳方式
- UI 更新必须在主线程进行，使用 `call_from_thread`

后续注意事项：
- 所有耗时操作都应使用 Worker
- 注意 Worker 的生命周期管理

## 标签
#bug #fix #textual #async #TUI
