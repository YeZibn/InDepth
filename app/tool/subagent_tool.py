from app.tool.create_subagent_tool import SubAgentRunner
from agno.tools import tool
from typing import List, Dict, Any


@tool(
    name="run_subagent",
    description="创建并运行一个轻量子 Agent 来执行简单任务。适用于：(1)简单查询和分析 (2)需要分离执行的独立子任务 (3)并行执行多个简单任务。每个 SubAgent 只执行一个任务，执行完自动销毁。",
    stop_after_tool_call=True,
    requires_confirmation=False,
)
def run_subagent(task: str, context: Dict[str, Any] = None, forbidden: List[str] = None) -> str:
    """
    运行单个 SubAgent 任务。

    Args:
        task: 要执行的子任务描述（简洁明确）
        context: 必要上下文（可选）
        forbidden: 禁止行为列表（可选），如 ["todo", "subagent"]

    Returns:
        str: SubAgent 的执行结果
    """
    result = SubAgentRunner.run(task=task, context=context, forbidden=forbidden)

    if result.get("success"):
        return f"✅ SubAgent {result['subagent_id']} 执行成功\n\n{result['result']}"
    else:
        return f"❌ SubAgent {result['subagent_id']} 执行失败\n\n{result.get('error', 'Unknown error')}"


@tool(
    name="run_subagents_parallel",
    description="并行运行多个轻量子 Agent 来执行多个独立任务。适用于：(1)需要同时查询多个来源 (2)需要并行分析多个内容 (3)批量执行简单任务。所有 SubAgent 同时执行，结果最后聚合返回。",
    stop_after_tool_call=True,
    requires_confirmation=False,
)
def run_subagents_parallel(tasks: List[str], shared_context: Dict[str, Any] = None, forbidden: List[str] = None) -> str:
    """
    并行运行多个 SubAgent 任务。

    Args:
        tasks: 任务描述列表
        shared_context: 共享上下文（可选）
        forbidden: 禁止行为列表（可选）

    Returns:
        str: 聚合后的执行结果
    """
    results = SubAgentRunner.run_parallel(tasks=tasks, context=shared_context, forbidden=forbidden)
    return SubAgentRunner.aggregate_results(results)
