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


if __name__ == "__main__":
    agent = build_runtime_cli_agent()
    print("欢迎使用 InDepth Runtime（BaseAgent 模式）！输入 'exit' 退出。\n")

    while True:
        user_input = input("请输入: ").strip()
        if user_input.lower() in ["exit", "quit", "q"]:
            print("再见！")
            break
        if not user_input:
            continue
        print("\nRuntime: ", end="")
        agent.chat(user_input)
        print()
