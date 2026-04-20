# Python 高级计算器

这是一个放在 `work` 目录下的高级 Python 计算器程序，支持安全表达式求值、科学函数、变量、历史记录、内存寄存器以及交互式 REPL。

## 文件说明

- `work/calculator.py`：主程序
- `work/README.md`：使用说明

## 核心功能

1. **基础运算**
   - 支持 `+ - * / // % **`
   - 支持括号与一元正负号

2. **科学计算**
   - 常量：`pi`、`e`、`tau`、`inf`
   - 函数：`sin`、`cos`、`tan`、`asin`、`acos`、`atan`、`sqrt`、`log`、`log10`、`exp`
   - 其他：`factorial`、`floor`、`ceil`、`round`、`abs`、`min`、`max`、`pow`

3. **变量与结果引用**
   - 支持变量赋值：`x = 2**8`
   - 支持上一条结果：`ans * 3`

4. **历史记录**
   - 输入 `history` 查看当前会话中的历史记录

5. **内存寄存器**
   - `mr`：读取内存
   - `mc`：清空内存
   - `m+`：将当前结果或指定表达式加入内存
   - `m-`：将当前结果或指定表达式从内存中减去

6. **输出精度控制**
   - `precision 6` 设置浮点输出精度

7. **安全求值**
   - 基于 Python AST 做受限表达式解析
   - 不允许任意执行 Python 代码

## 运行方式

### 1. 交互模式

```bash
python3 work/calculator.py
```

启动后可连续输入表达式或命令：

```text
calc> x = 7
calc> ans * 3
21
calc> m+
内存 = 21
calc> mr
21
calc> history
1. 7 = 7
2. ans * 3 = 21
```

### 2. 单次执行模式

```bash
python3 work/calculator.py "sin(pi/2) + 2**8"
```

输出示例：

```text
257
```

## 支持的命令

- `help`：显示帮助
- `history`：查看历史记录
- `vars`：查看变量
- `precision N`：设置输出精度（0 到 20）
- `mr` / `mc` / `m+` / `m-`：内存操作
- `quit` / `exit`：退出程序

## 使用示例

### 表达式计算

```text
calc> (1 + 2) * 3**2
27
```

### 科学函数

```text
calc> sqrt(16) + log10(100)
6
```

### 变量

```text
calc> rate = 3.5
calc> amount = 1000
calc> amount * rate / 100
35
```

### 精度控制

```text
calc> precision 4
calc> 10 / 3
3.3333
```

## 设计说明

程序采用单文件实现，核心结构包括：

- `SafeEvaluator`：基于 AST 的安全表达式求值器
- `AdvancedCalculator`：封装状态、命令解析与交互逻辑
- `CalculatorState`：保存变量、历史、内存、精度和上一结果

## 限制说明

- 历史记录、变量和内存仅保存在当前运行会话中，不会持久化到文件
- 仅支持程序白名单中的函数与语法
- 不支持自定义函数、复杂 Python 语句、关键字参数调用

## 已验证命令

以下命令已在当前环境执行验证：

```bash
python3 work/calculator.py "sin(pi/2) + 2**8"
printf 'x = 7\nans * 3\nm+\nmr\nhistory\nquit\n' | python3 work/calculator.py
```

## 编译 / 检查命令

Python 为解释型语言，无需传统编译。可使用以下命令做语法检查：

```bash
python3 -m py_compile work/calculator.py
```
