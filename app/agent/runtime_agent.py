from dotenv import load_dotenv
import uuid

from app.core import create_runtime


load_dotenv()


if __name__ == "__main__":
    runtime = create_runtime(system_prompt="遵守 InDepth 协议，优先结构化回答。", max_steps=50)
    session_task_id = f"runtime_cli_task_{uuid.uuid4().hex[:8]}"
    print("欢迎使用 InDepth Runtime（自研内核 MVP）！输入 'exit' 退出。\n")

    while True:
        user_input = input("请输入: ").strip()
        if user_input.lower() in ["exit", "quit", "q"]:
            print("再见！")
            break
        if not user_input:
            continue
        run_id = f"runtime_cli_run_{uuid.uuid4().hex[:8]}"
        answer = runtime.run(user_input=user_input, task_id=session_task_id, run_id=run_id)
        print(f"\nRuntime: {answer}\n")
