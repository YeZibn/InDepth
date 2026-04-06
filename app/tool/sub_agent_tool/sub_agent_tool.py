from agno.tools import tool
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import json
import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.agent.sub_agent import SubAgent
from app.observability.events import emit_event


ROLE_GENERAL = "general"
ROLE_RESEARCHER = "researcher"
ROLE_BUILDER = "builder"
ROLE_REVIEWER = "reviewer"
ROLE_VERIFIER = "verifier"


def normalize_role(role: str) -> str:
    allowed = {ROLE_GENERAL, ROLE_RESEARCHER, ROLE_BUILDER, ROLE_REVIEWER, ROLE_VERIFIER}
    role_norm = (role or "").strip().lower()
    if role_norm not in allowed:
        allowed_str = ", ".join(sorted(allowed))
        raise ValueError(f"Invalid role '{role}'. Allowed roles: {allowed_str}")
    return role_norm


def _emit_obs(
    task_id: str,
    role: str,
    event_type: str,
    status: str = "ok",
    duration_ms: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Best-effort observability hook. Never break business flow."""
    try:
        emit_event(
            task_id=task_id,
            run_id=task_id,
            actor="subagent",
            role=role,
            event_type=event_type,
            status=status,
            duration_ms=duration_ms,
            payload=payload or {},
        )
    except Exception:
        pass


@dataclass
class AgentInstance:
    """SubAgent 实例封装"""
    id: str
    name: str
    agent: SubAgent
    role: str = ROLE_GENERAL
    task_id: str = ""
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
            cls._instance._executor = ThreadPoolExecutor(max_workers=10)
            cls._instance._lock = threading.RLock()
        return cls._instance
    
    def create(
        self,
        name: str,
        description: str,
        task: str,
        role: str,
        instructions: str = "",
        task_id: str = "",
    ) -> Tuple[str, str]:
        """
        创建 SubAgent
        
        Args:
            name: Agent 名称
            description: Agent 描述
            task: Agent 的专属任务说明
            
        Returns:
            Tuple[str, str]: (agent_id, resolved_role)
        """
        agent_id = str(uuid.uuid4())[:8]
        resolved_role = normalize_role(role)
        agent = SubAgent(
            name,
            description,
            task,
            role=resolved_role,
            generated_instructions=instructions,
        )
        
        with self._lock:
            self._pool[agent_id] = AgentInstance(
                id=agent_id,
                name=name,
                agent=agent,
                role=resolved_role,
                task_id=task_id.strip(),
                status="idle"
            )
        obs_task_id = task_id.strip() or f"subagent:{agent_id}"
        _emit_obs(
            task_id=obs_task_id,
            role=resolved_role,
            event_type="subagent_created",
            payload={"agent_id": agent_id, "name": name, "task": task},
        )
        return agent_id, resolved_role
    
    def get(self, agent_id: str) -> Optional[AgentInstance]:
        """获取指定 Agent 实例"""
        with self._lock:
            return self._pool.get(agent_id)
    
    def list_all(self) -> List[Dict[str, Any]]:
        """列出所有 Agent"""
        with self._lock:
            return [
                {
                    "id": a.id,
                    "name": a.name,
                    "role": a.role,
                    "status": a.status,
                    "created_at": a.created_at.isoformat(),
                    "task_count": len(a.task_history)
                }
                for a in self._pool.values()
            ]
    
    def destroy(self, agent_id: str) -> bool:
        """销毁 Agent"""
        with self._lock:
            if agent_id in self._pool:
                del self._pool[agent_id]
                return True
            return False
    
    def destroy_all(self) -> int:
        """销毁所有 Agent，返回销毁数量"""
        with self._lock:
            count = len(self._pool)
            self._pool.clear()
            return count
    
    def run_task(self, agent_id: str, message: str) -> Dict[str, Any]:
        """
        运行任务（同步）
        
        Args:
            agent_id: Agent ID
            message: 任务消息
            
        Returns:
            Dict[str, Any]: 结构化执行结果
        """
        with self._lock:
            instance = self._pool.get(agent_id)
            if not instance:
                return {
                    "success": False,
                    "error": f"Agent '{agent_id}' not found",
                    "agent_id": agent_id,
                    "message": message,
                }
            instance.status = "running"
        start_time = datetime.now()
        start_perf = time.time()
        obs_task_id = instance.task_id or f"subagent:{agent_id}"
        _emit_obs(
            task_id=obs_task_id,
            role=instance.role,
            event_type="subagent_started",
            payload={"agent_id": agent_id, "message": message},
        )
        
        try:
            result = instance.agent.chat(message)
            result_text = "" if result is None else str(result)
            success = bool(result_text.strip())
            end_time = datetime.now()
            duration_ms = int((time.time() - start_perf) * 1000)
            with self._lock:
                instance.status = "completed" if success else "error"
                task_record = {
                    "task": message,
                    "result": result_text,
                    "status": "completed" if success else "error",
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                }
                instance.task_history.append(task_record)

            if not success:
                _emit_obs(
                    task_id=obs_task_id,
                    role=instance.role,
                    event_type="subagent_failed",
                    status="error",
                    duration_ms=duration_ms,
                    payload={"agent_id": agent_id, "error": "SubAgent returned empty result"},
                )
                return {
                    "success": False,
                    "error": "SubAgent returned empty result",
                    "agent_id": agent_id,
                    "message": message,
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "result": result_text,
                }

            _emit_obs(
                task_id=obs_task_id,
                role=instance.role,
                event_type="subagent_finished",
                duration_ms=duration_ms,
                payload={"agent_id": agent_id},
            )
            return {
                "success": True,
                "agent_id": agent_id,
                "message": message,
                "result": result_text,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
            }
            
        except Exception as e:
            end_time = datetime.now()
            duration_ms = int((time.time() - start_perf) * 1000)
            with self._lock:
                instance.status = "error"
                task_record = {
                    "task": message,
                    "result": str(e),
                    "status": "error",
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                }
                instance.task_history.append(task_record)
            _emit_obs(
                task_id=obs_task_id,
                role=instance.role,
                event_type="subagent_failed",
                status="error",
                duration_ms=duration_ms,
                payload={"agent_id": agent_id, "error": str(e)},
            )

            return {
                "success": False,
                "error": f"Error executing task: {str(e)}",
                "agent_id": agent_id,
                "message": message,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
            }

    async def run_task_async(self, agent_id: str, message: str) -> Dict[str, Any]:
        """
        异步运行任务
        
        Args:
            agent_id: Agent ID
            message: 任务消息
            
        Returns:
            Dict[str, Any]: 结构化执行结果
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, 
            self.run_task, 
            agent_id, 
            message
        )
    
    async def run_tasks_parallel(self, tasks: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
        """
        并行运行多个 SubAgent 任务
        
        Args:
            tasks: List of (agent_id, message) tuples
            
        Returns:
            List of results with task info
        """
        async def run_single(agent_id: str, message: str, index: int) -> Dict[str, Any]:
            result = await self.run_task_async(agent_id, message)
            return {
                "index": index,
                **result,
            }
        
        coroutines = [
            run_single(agent_id, message, i) 
            for i, (agent_id, message) in enumerate(tasks)
        ]
        
        results = await asyncio.gather(*coroutines, return_exceptions=True)
        
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "index": i,
                    "success": False,
                    "agent_id": tasks[i][0],
                    "message": tasks[i][1],
                    "error": f"Error: {str(result)}",
                    "status": "error"
                })
            else:
                processed_results.append({
                    **result,
                    "status": "completed" if result.get("success") else "error",
                })
        
        return processed_results


_manager = SubAgentManager()


@tool(
    name="create_sub_agent",
    description="创建一个 SubAgent 来执行特定任务，返回 agent_id。当遇到需要专门处理的复杂任务时使用此工具。",
    stop_after_tool_call=False,
)
def create_sub_agent(
    name: str,
    description: str,
    task: str,
    role: str,
    instructions: str = "",
    task_id: str = "",
) -> str:
    """
    创建 SubAgent
    
    Args:
        name: Agent 名称，用于标识
        description: Agent 描述，说明其职责
        task: Agent 的专属任务说明，告诉 Agent 应该专注什么
        role: 角色，必填：researcher/builder/reviewer/verifier/general
        instructions: 主Agent生成的附加指令，会与角色预设指令拼接
        task_id: 可选的任务ID，用于观测与复盘归档
    
    Returns:
        str: agent_id，用于后续操作（如运行任务、销毁等）
    """
    try:
        agent_id, resolved_role = _manager.create(
            name,
            description,
            task,
            role=role,
            instructions=instructions,
            task_id=task_id,
        )
    except ValueError as e:
        return json.dumps(
            {"success": False, "error": str(e)},
            ensure_ascii=False,
            indent=2,
        )
    return json.dumps(
        {
            "success": True,
            "agent_id": agent_id,
            "name": name,
            "description": description,
            "task": task,
            "role": resolved_role,
        },
        ensure_ascii=False,
        indent=2,
    )


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
        return json.dumps(
            {"success": False, "error": "Both agent_id and message are required"},
            ensure_ascii=False,
            indent=2,
        )
    
    return json.dumps(_manager.run_task(agent_id, message), ensure_ascii=False, indent=2)


@tool(
    name="run_sub_agents_parallel",
    description="并行运行多个 SubAgent 任务。接收 JSON 格式的任务列表，每个任务包含 agent_id 和 message。适用于需要同时执行多个独立任务的场景，可大幅提升执行效率。",
    stop_after_tool_call=False,
)
def run_sub_agents_parallel(tasks_json: str) -> str:
    """
    并行运行多个 SubAgent 任务
    
    Args:
        tasks_json: JSON 格式的任务列表，格式为:
            '[{"agent_id": "xxx", "message": "任务1"}, {"agent_id": "yyy", "message": "任务2"}]'
    
    Returns:
        str: 所有任务的执行结果（JSON 格式）
    """
    try:
        tasks = json.loads(tasks_json)
        if not isinstance(tasks, list):
            return json.dumps(
                {"success": False, "error": "tasks must be a JSON array"},
                ensure_ascii=False,
                indent=2,
            )
        
        task_tuples = [(t["agent_id"], t["message"]) for t in tasks]
        
        previous_loop = None
        try:
            previous_loop = asyncio.get_event_loop()
        except RuntimeError:
            previous_loop = None

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(_manager.run_tasks_parallel(task_tuples))
        finally:
            loop.close()
            if previous_loop is not None:
                asyncio.set_event_loop(previous_loop)
            else:
                asyncio.set_event_loop(None)
        
        success_count = sum(1 for r in results if r.get("success"))
        return json.dumps(
            {
                "success": True,
                "total": len(results),
                "success_count": success_count,
                "failure_count": len(results) - success_count,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        
    except json.JSONDecodeError as e:
        return json.dumps(
            {"success": False, "error": f"Invalid JSON format - {e}"},
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return json.dumps(
            {"success": False, "error": str(e)},
            ensure_ascii=False,
            indent=2,
        )


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
    return json.dumps(
        {"success": True, "count": len(agents), "agents": agents},
        ensure_ascii=False,
        indent=2,
    )


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
        return json.dumps(
            {"success": False, "error": "agent_id is required"},
            ensure_ascii=False,
            indent=2,
        )
    
    success = _manager.destroy(agent_id)
    if success:
        return json.dumps(
            {"success": True, "agent_id": agent_id, "message": "destroyed"},
            ensure_ascii=False,
            indent=2,
        )
    return json.dumps(
        {"success": False, "agent_id": agent_id, "error": "not found"},
        ensure_ascii=False,
        indent=2,
    )


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
    return json.dumps(
        {"success": True, "destroyed_count": count},
        ensure_ascii=False,
        indent=2,
    )


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
        return json.dumps(
            {"success": False, "agent_id": agent_id, "error": "not found"},
            ensure_ascii=False,
            indent=2,
        )
    
    info = {
        "success": True,
        "id": instance.id,
        "name": instance.name,
        "role": instance.role,
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
    """
    return [
        create_sub_agent,
        run_sub_agent,
        run_sub_agents_parallel,
        list_sub_agents,
        destroy_sub_agent,
        destroy_all_sub_agents,
        get_sub_agent_info,
    ]
