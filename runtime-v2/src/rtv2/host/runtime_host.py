"""RuntimeHost minimal shell for runtime-v2."""

from __future__ import annotations

from rtv2.host.interfaces import HostIdGenerator, RuntimeHostState
from rtv2.orchestrator.runtime_orchestrator import RuntimeOrchestrator
from rtv2.task_graph.store import TaskGraphStore


class RuntimeHost:
    """Minimal host shell that owns host state and core runtime dependencies."""

    def __init__(
        self,
        *,
        graph_store: TaskGraphStore,
        orchestrator: RuntimeOrchestrator,
        id_generator: HostIdGenerator,
    ) -> None:
        self.graph_store = graph_store
        self.orchestrator = orchestrator
        self.id_generator = id_generator
        self.host_state = RuntimeHostState(session_id=id_generator.create_session_id())

    def get_host_state(self) -> RuntimeHostState:
        """Return a snapshot of the current host binding state."""

        return RuntimeHostState(
            session_id=self.host_state.session_id,
            current_task_id=self.host_state.current_task_id,
            active_run_id=self.host_state.active_run_id,
        )
