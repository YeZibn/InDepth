from dotenv import load_dotenv

from app.core import create_runtime


load_dotenv()


if __name__ == "__main__":
    runtime = create_runtime(system_prompt="遵守 InDepth 协议，优先结构化回答。", max_steps=10)
    print("欢迎使用 InDepth Runtime（自研内核 MVP）！输入 'exit' 退出。\n")

    while True:
        user_input = input("请输入: ").strip()
        if user_input.lower() in ["exit", "quit", "q"]:
            print("再见！")
            break
        if not user_input:
            continue
        answer = runtime.run(user_input=user_input, task_id="runtime_cli_task", run_id="runtime_cli_run")
        print(f"\nRuntime: {answer}\n")
