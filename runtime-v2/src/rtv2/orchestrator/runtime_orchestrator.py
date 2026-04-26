"""RuntimeOrchestrator skeleton module."""

from __future__ import annotations

from rtv2.host.interfaces import HostRunResult, StartRunIdentity


class RuntimeOrchestrator:
    """Temporary host-facing orchestrator stub until Step 05 lands."""

    def run(self, start_run_identity: StartRunIdentity) -> HostRunResult:
        """Return an explicit stub result until real phase execution exists."""

        return HostRunResult(
            task_id=start_run_identity.task_id,
            run_id=start_run_identity.run_id,
            runtime_state="stub",
            output_text="",
        )
