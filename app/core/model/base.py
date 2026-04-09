from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class ModelOutput:
    content: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationConfig:
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    stop: Optional[List[str] | str] = None
    seed: Optional[int] = None
    n: Optional[int] = None
    max_tokens: Optional[int] = None
    enable_thinking: Optional[bool] = None
    provider_options: Dict[str, Any] = field(default_factory=dict)


class ModelProvider(Protocol):
    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        config: Optional[GenerationConfig] = None,
    ) -> ModelOutput:
        """Generate the next assistant turn based on messages and available tools."""
