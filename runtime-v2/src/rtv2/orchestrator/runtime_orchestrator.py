"""RuntimeOrchestrator skeleton module."""

from __future__ import annotations

from rtv2.host.interfaces import HostRunResult, StartRunIdentity
from rtv2.state.models import DomainState, RunContext, RunIdentity, RunLifecycle, RunPhase, RuntimeState
from rtv2.task_graph.models import TaskGraphState, TaskGraphStatus


class RuntimeOrchestrator:
    """Temporary host-facing orchestrator stub until Step 05 lands."""

    def __init__(self) -> None:
        self._graph_counter = 0

    def build_initial_context(self, start_run_identity: StartRunIdentity) -> RunContext:
        """Build the minimal formal run context for a new run."""

        graph_id = self._create_graph_id()
        return RunContext(
            run_identity=RunIdentity(
                session_id=start_run_identity.session_id,
                task_id=start_run_identity.task_id,
                run_id=start_run_identity.run_id,
                user_input=start_run_identity.user_input,
            ),
            run_lifecycle=RunLifecycle(
                lifecycle_state="running",
                current_phase=RunPhase.PREPARE,
            ),
            runtime_state=RuntimeState(),
            domain_state=DomainState(
                task_graph_state=TaskGraphState(
                    graph_id=graph_id,
                    nodes=[],
                    active_node_id="",
                    graph_status=TaskGraphStatus.ACTIVE,
                    version=1,
                )
            ),
        )

    def run(self, start_run_identity: StartRunIdentity) -> HostRunResult:
        """Return an explicit stub result until real phase execution exists."""

        self.build_initial_context(start_run_identity)
        return HostRunResult(
            task_id=start_run_identity.task_id,
            run_id=start_run_identity.run_id,
            runtime_state="stub",
            output_text="",
        )

    def _create_graph_id(self) -> str:
        """Create a graph id inside the orchestrator boundary."""

        self._graph_counter += 1
        return f"graph-{self._graph_counter}"
