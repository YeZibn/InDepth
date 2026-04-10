from typing import Any, Dict, List, Optional, Protocol


class MemoryStore(Protocol):
    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_call_id: str = "",
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        ...

    def get_recent_messages(self, conversation_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        ...

    def compact(self, conversation_id: str) -> None:
        ...
