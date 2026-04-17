from typing import Any, Dict, List, Union

from app.core.model.base import GenerationConfig, ModelOutput


class MockModelProvider:
    """Deterministic provider for runtime tests."""

    def __init__(self, scripted_outputs: List[Union[str, Dict[str, Any]]]):
        self._outputs = scripted_outputs[:]
        self.requests: List[Dict[str, Any]] = []

    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        config: GenerationConfig | None = None,
    ) -> ModelOutput:
        self.requests.append(
            {
                "messages": [dict(m) for m in messages],
                "tools": [dict(t) for t in tools],
                "config": config,
            }
        )
        if not self._outputs:
            return ModelOutput(content='{"type":"final","content":"No scripted output left."}')
        item = self._outputs.pop(0)
        if isinstance(item, dict):
            content = str(item.get("content", "") or "")
            raw = item.get("raw", {"mock": True})
            return ModelOutput(content=content, raw=raw if isinstance(raw, dict) else {"mock": True})
        return ModelOutput(content=item, raw={"mock": True})
