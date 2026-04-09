import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from app.core.tools.validator import validate_args


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Any]
    parameters: Optional[Dict[str, Any]] = None


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def has(self, name: str) -> bool:
        return name in self._tools

    def invoke(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        spec = self._tools.get(name)
        if not spec:
            return {"success": False, "error": f"Unknown tool: {name}"}
        ok, errors = validate_args(spec.parameters or {}, args or {})
        if not ok:
            return {"success": False, "error": "Tool args validation failed", "details": errors}
        try:
            result = spec.handler(**(args or {}))
            if isinstance(result, str):
                stripped = result.strip()
                if stripped.startswith("Error:"):
                    return {"success": False, "error": stripped}
                if stripped.startswith("{") or stripped.startswith("["):
                    try:
                        parsed = json.loads(stripped)
                        if isinstance(parsed, dict) and parsed.get("success") is False:
                            error_text = (
                                str(parsed.get("error", "")).strip()
                                or str(parsed.get("message", "")).strip()
                                or f"Tool {name} returned success=false"
                            )
                            return {"success": False, "error": error_text, "result": parsed}
                    except Exception:
                        pass
            if isinstance(result, dict) and result.get("success") is False:
                error_text = (
                    str(result.get("error", "")).strip()
                    or str(result.get("message", "")).strip()
                    or f"Tool {name} returned success=false"
                )
                return {"success": False, "error": error_text, "result": result}
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_tool_schemas(self) -> List[Dict[str, Any]]:
        schemas = []
        for spec in self._tools.values():
            schemas.append(
                {
                    "name": spec.name,
                    "description": spec.description or "",
                    "parameters": spec.parameters or {},
                }
            )
        return schemas

    def pretty_schemas_json(self) -> str:
        return json.dumps(self.list_tool_schemas(), ensure_ascii=False, indent=2)
