# UI 线程禁止阻塞操作

## 规则
如果需要在 UI 应用中执行耗时操作，则必须使用后台线程或异步机制，禁止在 UI 线程直接执行。

## 原因

技术原因：
- UI 线程负责渲染和响应用户交互
- 阻塞 UI 线程会导致界面卡顿或无响应
- 用户体验极差，可能导致用户误以为应用崩溃

业务原因：
- 用户期望应用始终可交互
- 响应速度是用户体验的核心指标

历史教训：
- 多次因为同步加载数据导致界面卡顿
- 用户投诉应用"卡死"

## 示例

正确做法：
```python
# Textual
@work
async def load_data(self):
    data = await fetch_data()
    self.call_from_thread(self.update_ui, data)

# PyQt
QThread.run(lambda: self.load_data())

# Web 前端
async function loadData() {
    const data = await fetch(url);
    updateUI(data);
}
```

错误做法：
```python
# 直接在 UI 线程同步加载
def on_mount(self):
    data = fetch_data_sync()  # 阻塞 UI 线程
    self.update_ui(data)
```

## 标签
#规范 #性能 #UI #async
