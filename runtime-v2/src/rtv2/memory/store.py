"""Runtime memory store interfaces for runtime-v2."""

from __future__ import annotations

from abc import ABC, abstractmethod

from rtv2.memory.models import RuntimeMemoryEntry, RuntimeMemoryQuery


class RuntimeMemoryStore(ABC):
    """Abstract store contract for short-term runtime memory."""

    @abstractmethod
    def append_entry(self, entry: RuntimeMemoryEntry) -> RuntimeMemoryEntry:
        """Persist one runtime memory entry and return the stored value."""

    @abstractmethod
    def list_entries_for_run(self, *, task_id: str, run_id: str) -> list[RuntimeMemoryEntry]:
        """List all runtime memory entries for one run in stable order."""

    @abstractmethod
    def list_entries(self, query: RuntimeMemoryQuery) -> list[RuntimeMemoryEntry]:
        """List runtime memory entries filtered by the provided query."""

    @abstractmethod
    def get_latest_entries(self, query: RuntimeMemoryQuery) -> list[RuntimeMemoryEntry]:
        """List the latest runtime memory entries for the provided query."""
