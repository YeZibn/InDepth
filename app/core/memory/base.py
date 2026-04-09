from typing import Dict, List, Protocol


class MemoryStore(Protocol):
    def append_message(self, conversation_id: str, role: str, content: str) -> None:
        ...

    def get_recent_messages(self, conversation_id: str, limit: int = 20) -> List[Dict[str, str]]:
        ...

    def compact(self, conversation_id: str) -> None:
        ...
