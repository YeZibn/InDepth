from agno.tools import tool
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import json

from app.agent.sub_agent import SubAgent


@dataclass
class AgentInstance:
    """SubAgent 实例封装"""
    id: str
    name: str
    agent: SubAgent
    status: str = "idle"  # "idle", "running", "completed", "error"
    created_at: datetime = field(default_factory=datetime.now)
    task_history: List[Dict[str, Any]] = field(default_factory=list)


class SubAgentManager:
    """
    SubAgent 管理器（单例模式）
    负责管理所有 SubAgent 实例的生命周期
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._pool: Dict[str, AgentInstance] = {}
        return cls._instance
    
    def create(self, name: str, description: str, task: str) -> str:
        """
        创建 SubAgent
        
        Args:
            name: Agent 名称
            description: Agent 描述
            task: Agent 的专属任务说明
            
        Returns:
            str: agent_id
        """
        agent_id = str(uuid.uuid4())[:8]
        agent = SubAgent(name, description, task)
        
        self._pool[agent_id] = AgentInstance(
            id=agent_id,
            name=name,
            agent=agent,
            status="idle"
        )
        return agent_id
    
    def get(self, agent_id: str) -> Optional[AgentInstance]:
        """获取指定 Agent 实例"""
        return self._pool.get(agent_id)
    
    def list_all(self) -> List[Dict[str, Any]]:
        """列出所有 Agent"""
        return [
            {
                "id": a.id,
                "name": a.name,
                "status": a.status,
                "created_at": a.created_at.isoformat(),
                "task_count": len(a.task_history)
            }
            for a in self._pool.values()
        ]
    
    def destroy(self, agent_id: str) -> bool:
        """销毁 Agent"""
        if agent_id in self._pool:
            del self._pool[agent_id]
            return True
        return False
    
    def destroy_all(self) -> int:
        """销毁所有 Agent，返回销毁数量"""
        count = len(self._pool)
        self._pool.clear()
        return count
    
    def run_task(self, agent_id: str, message: str) -> str:
        """
        运行任务（同步）
        
        Args:
            agent_id: Agent ID
            message: 任务消息
            
        Returns:
            str: 执行结果
        """
        instance = self._pool.get(agent_id)
        if not instance:
            return f"Error: Agent '{agent_id}' not found"
        
        instance.status = "running"
        start_time = datetime.now()
        
        try:
            # 调用 SubAgent 的 chat 方法
            result = instance.agent.chat(message)
            
            instance.status = "completed"
            
            # 记录任务历史
            task_record = {
                "task": message,
                "result": result,
                "status": "completed",
                "start_time": start_time.isoformat(),
                "end_time": datetime.now().isoformat()
            }
            instance.task_history.append(task_record)
            
            return result
            
        except Exception as e:
            instance.status = "error"
            
            # 记录失败任务
            task_record = {
                "task": message,
                "result": str(e),
                "status": "error",
                "start_time": start_time.isoformat(),
                "end_time": datetime.now().isoformat()
            }
            instance.task_history.append(task_record)
            
            return f"Error executing task: {str(e)}"


# 全局管理器实例
_manager = SubAgentManager()


@tool(
    name="create_sub_agent",
    description="创建一个 SubAgent 来执行特定任务，返回 agent_id。当遇到需要专门处理的复杂任务时使用此工具。",
    stop_after_tool_call=False,
)
def create_sub_agent(name: str, description: str, task: str) -> str:
    """
    创建 SubAgent
    
    Args:
        name: Agent 名称，用于标识
        description: Agent 描述，说明其职责
        task: Agent 的专属任务说明，告诉 Agent 应该专注什么
    
    Returns:
        str: agent_id，用于后续操作（如运行任务、销毁等）
    """
    agent_id = _manager.create(name, description, task)
    return f"SubAgent created successfully.\nName: {name}\nID: {agent_id}\nDescription: {description}"


@tool(
    name="run_sub_agent",
    description="让指定的 SubAgent 执行具体任务，需要提供 agent_id 和任务描述",
    stop_after_tool_call=False,
)
def run_sub_agent(agent_id: str, message: str) -> str:
    """
    运行 SubAgent 执行任务
    
    Args:
        agent_id: Agent ID（由 create_sub_agent 返回的 8 位字符串）
        message: 要执行的具体任务描述
    
    Returns:
        str: 执行结果
    """
    if not agent_id or not message:
        return "Error: Both agent_id and message are required"
    
    return _manager.run_task(agent_id, message)


@tool(
    name="list_sub_agents",
    description="列出所有活跃的 SubAgent，查看它们的状态和基本信息",
    stop_after_tool_call=False,
)
def list_sub_agents() -> str:
    """
    列出所有 SubAgent 及其状态
    
    Returns:
        str: Agent 列表（JSON 格式）
    """
    agents = _manager.list_all()
    if not agents:
        return "No active SubAgents."
    
    return json.dumps(agents, ensure_ascii=False, indent=2)


@tool(
    name="destroy_sub_agent",
    description="销毁指定的 SubAgent，释放资源。任务完成后建议及时销毁。",
    stop_after_tool_call=False,
)
def destroy_sub_agent(agent_id: str) -> str:
    """
    销毁 SubAgent
    
    Args:
        agent_id: 要销毁的 Agent ID
    
    Returns:
        str: 操作结果
    """
    if not agent_id:
        return "Error: agent_id is required"
    
    success = _manager.destroy(agent_id)
    if success:
        return f"Agent '{agent_id}' destroyed successfully"
    return f"Agent '{agent_id}' not found"


@tool(
    name="destroy_all_sub_agents",
    description="销毁所有 SubAgent，一键清理所有资源",
    stop_after_tool_call=False,
)
def destroy_all_sub_agents() -> str:
    """
    销毁所有 SubAgent
    
    Returns:
        str: 操作结果
    """
    count = _manager.destroy_all()
    return f"All SubAgents destroyed. Total: {count}"


@tool(
    name="get_sub_agent_info",
    description="获取指定 SubAgent 的详细信息，包括任务历史",
    stop_after_tool_call=False,
)
def get_sub_agent_info(agent_id: str) -> str:
    """
    获取 SubAgent 详细信息
    
    Args:
        agent_id: Agent ID
    
    Returns:
        str: Agent 详细信息
    """
    instance = _manager.get(agent_id)
    if not instance:
        return f"Agent '{agent_id}' not found"
    
    info = {
        "id": instance.id,
        "name": instance.name,
        "status": instance.status,
        "created_at": instance.created_at.isoformat(),
        "task_history": instance.task_history
    }
    
    return json.dumps(info, ensure_ascii=False, indent=2)


def get_sub_agent_tools() -> list:
    """
    获取所有 SubAgent 相关的工具函数
    
    Returns:
        list: 包含所有 SubAgent 工具的列表
        
    Usage:
        from app.tool.sub_agent_tool.sub_agent_tool import get_sub_agent_tools
        
        agent = Agent(
            model=...,
            tools=get_sub_agent_tools(),  # 一键导入所有工具
            ...
        )
    """
    return [
        create_sub_agent,
        run_sub_agent,
        list_sub_agents,
        destroy_sub_agent,
        destroy_all_sub_agents,
        get_sub_agent_info,
    ]

