from dotenv import load_dotenv

from app.agent.agent import BaseAgent


load_dotenv()


def build_runtime_cli_agent() -> BaseAgent:
    return BaseAgent(
        name="runtime_cli",
        description="Runtime CLI agent powered by BaseAgent",
        instructions="遵守 InDepth 协议，优先结构化回答。",
        tools=[],
        load_default_tools=True,
        skills="app/skills",
        load_memory_knowledge=True,
    )


def handle_cli_command(agent: BaseAgent, command: str, mode: str) -> tuple[str, str, bool]:
    text = (command or "").strip()
    if not text.startswith("/"):
        return mode, "", False

    if text in {"/help", "/h"}:
        return (
            mode,
            (
                "命令:\n"
                "/mode chat - 切换到聊天模式\n"
                "/mode task [label] - 切换到任务模式（自动开启新任务并结束旧任务）\n"
                "/task <label> - 在任务模式下开启新任务并结束旧任务\n"
                "/newtask <label> - /task 的别名\n"
                "/status - 查看当前模式和 task_id\n"
                "/exit - 退出"
            ),
            True,
        )

    if text.startswith("/mode "):
        mode_args = text.split()[1:]
        target = (mode_args[0] if mode_args else "").strip().lower()
        task_label = " ".join(mode_args[1:]).strip()
        if target not in {"chat", "task"}:
            return mode, "无效模式，仅支持: chat/task", True
        if target == mode:
            return mode, f"当前已是 {mode} 模式。", True
        if target == "task":
            old_task_id = agent.current_task_id
            new_task_id = agent.start_new_task(task_label or "task")
            return (
                "task",
                f"已进入 task 模式。\n已结束任务: {old_task_id}\n新任务: {new_task_id}",
                True,
            )
        old_task_id = agent.current_task_id
        new_task_id = agent.start_new_task("chat")
        return (
            "chat",
            f"已进入 chat 模式。\n已结束任务: {old_task_id}\n新任务: {new_task_id}",
            True,
        )

    if text.startswith("/task") or text.startswith("/newtask"):
        if mode != "task":
            return mode, "请先使用 /mode task 进入任务模式。", True
        label = text.split(" ", 1)[1].strip() if " " in text else ""
        old_task_id = agent.current_task_id
        new_task_id = agent.start_new_task(label or "next_task")
        return (
            mode,
            f"已结束任务: {old_task_id}\n新任务已启动: {new_task_id}",
            True,
        )

    if text == "/status":
        return mode, f"mode={mode}, task_id={agent.current_task_id}", True

    if text == "/exit":
        return mode, "", False

    return mode, f"未知命令: {text}，输入 /help 查看命令。", True


if __name__ == "__main__":
    agent = build_runtime_cli_agent()
    mode = "chat"
    agent.start_new_task("chat")
    print("欢迎使用 InDepth Runtime（BaseAgent 模式）！输入 'exit' 退出。\n")
    print("输入 /help 查看命令。\n")

    while True:
        user_input = input("请输入: ").strip()
        if user_input.lower() in ["exit", "quit", "q"]:
            print("再见！")
            break
        if not user_input:
            continue
        mode, command_output, handled = handle_cli_command(agent, user_input, mode)
        if user_input == "/exit":
            print("再见！")
            break
        if command_output:
            print(f"\nRuntime: {command_output}\n")
        if handled:
            continue
        print("\nRuntime: ", end="")
        agent.chat(user_input)
        print()
