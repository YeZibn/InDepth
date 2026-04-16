from pathlib import Path
import ast


HISTORY_FILE = Path(__file__).with_name("history.txt")
SUPPORTED_OPERATORS = {"+", "-", "*", "/", "%", "//", "**"}


class SafeEvaluator(ast.NodeVisitor):
    """安全表达式计算器：仅允许数字、括号和基础算术运算。"""

    def visit_Expression(self, node):
        return self.visit(node.body)

    def visit_BinOp(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)

        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ZeroDivisionError("除数不能为 0")
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            if right == 0:
                raise ZeroDivisionError("除数不能为 0")
            return left // right
        if isinstance(node.op, ast.Mod):
            if right == 0:
                raise ZeroDivisionError("除数不能为 0")
            return left % right
        if isinstance(node.op, ast.Pow):
            return left ** right

        raise ValueError("表达式中包含不支持的运算。")

    def visit_UnaryOp(self, node):
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError("表达式中包含不支持的一元运算。")

    def visit_Constant(self, node):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("表达式中包含非法常量。")

    def visit_Num(self, node):  # 兼容旧版本 Python AST
        return node.n

    def generic_visit(self, node):
        raise ValueError("表达式中包含非法内容，仅支持数字、括号和基础运算。")


def calculate(num1, operator, num2):
    if operator == "+":
        return num1 + num2
    if operator == "-":
        return num1 - num2
    if operator == "*":
        return num1 * num2
    if operator == "/":
        if num2 == 0:
            raise ZeroDivisionError("除数不能为 0")
        return num1 / num2
    if operator == "%":
        if num2 == 0:
            raise ZeroDivisionError("除数不能为 0")
        return num1 % num2
    if operator == "//":
        if num2 == 0:
            raise ZeroDivisionError("除数不能为 0")
        return num1 // num2
    if operator == "**":
        return num1 ** num2
    raise ValueError("不支持的运算符，请使用 +, -, *, /, %, //, **")


def format_result(result):
    if isinstance(result, float) and result.is_integer():
        return int(result)
    return result


def evaluate_expression(expression):
    expression = expression.strip()
    if not expression:
        raise ValueError("表达式不能为空")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("表达式语法错误") from exc

    evaluator = SafeEvaluator()
    return evaluator.visit(tree)


def get_number(prompt):
    while True:
        raw = input(prompt).strip()
        if not raw:
            print("输入不能为空，请重新输入数字。")
            continue
        try:
            return float(raw)
        except ValueError:
            print("输入无效，请输入数字。")


def get_operator():
    while True:
        operator = input("请输入运算符 (+, -, *, /, %, //, **): ").strip()
        if operator in SUPPORTED_OPERATORS:
            return operator
        print("运算符无效，请输入 +, -, *, /, %, // 或 **。")


def append_history(entry):
    with HISTORY_FILE.open("a", encoding="utf-8") as file:
        file.write(entry + "\n")


def load_history():
    if not HISTORY_FILE.exists():
        return []
    return HISTORY_FILE.read_text(encoding="utf-8").splitlines()


def clear_history():
    HISTORY_FILE.write_text("", encoding="utf-8")


def show_history():
    history = load_history()
    print("\n=== 计算历史 ===")
    if not history:
        print("暂无历史记录。")
        return
    for index, item in enumerate(history, start=1):
        print(f"{index}. {item}")


def show_help():
    print("\n=== 帮助说明 ===")
    print("1. 标准计算：输入两个数字和一个运算符进行计算。")
    print("2. 表达式计算：可直接输入如 (2 + 3) * 4 这样的表达式。")
    print("3. 支持运算符：+, -, *, /, %, //, **")
    print("4. 历史记录会自动写入 work/history.txt")


def ask_continue():
    while True:
        choice = input("是否继续当前模式计算？(y/n): ").strip().lower()
        if choice in {"y", "n"}:
            return choice == "y"
        print("输入无效，请输入 y 或 n。")


def run_standard_mode():
    print("\n进入标准计算模式")
    while True:
        num1 = get_number("请输入第一个数字: ")
        operator = get_operator()
        num2 = get_number("请输入第二个数字: ")

        try:
            result = calculate(num1, operator, num2)
            formatted = format_result(result)
            record = f"{format_result(num1)} {operator} {format_result(num2)} = {formatted}"
            print(f"计算结果: {formatted}")
            append_history(record)
        except (ZeroDivisionError, ValueError) as exc:
            print(f"计算错误: {exc}")

        if not ask_continue():
            break


def run_expression_mode():
    print("\n进入表达式计算模式")
    print("示例：(2 + 3) * 4")
    while True:
        expression = input("请输入表达式: ").strip()
        try:
            result = evaluate_expression(expression)
            formatted = format_result(result)
            record = f"{expression} = {formatted}"
            print(f"计算结果: {formatted}")
            append_history(record)
        except (ZeroDivisionError, ValueError) as exc:
            print(f"表达式错误: {exc}")

        if not ask_continue():
            break


def print_menu():
    print("\n=== 复杂版 Python 计算器 ===")
    print("1. 标准计算模式")
    print("2. 表达式计算模式")
    print("3. 查看历史记录")
    print("4. 清空历史记录")
    print("5. 帮助")
    print("0. 退出")


def main():
    print("欢迎使用复杂版 Python 计算器！")

    while True:
        print_menu()
        choice = input("请选择功能: ").strip()

        if choice == "1":
            run_standard_mode()
        elif choice == "2":
            run_expression_mode()
        elif choice == "3":
            show_history()
        elif choice == "4":
            clear_history()
            print("历史记录已清空。")
        elif choice == "5":
            show_help()
        elif choice == "0":
            print("感谢使用，再见！")
            break
        else:
            print("无效选择，请输入 0-5。")


if __name__ == "__main__":
    main()
