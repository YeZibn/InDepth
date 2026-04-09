from typing import Any, Dict, List, Tuple


_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


def validate_args(schema: Dict[str, Any], args: Dict[str, Any]) -> Tuple[bool, List[str]]:
    def _validate_node(node_schema: Dict[str, Any], value: Any, path: str, errors: List[str]) -> None:
        if not isinstance(node_schema, dict):
            return

        expected_type = node_schema.get("type")
        if expected_type is None and ("properties" in node_schema or "required" in node_schema):
            expected_type = "object"
        if expected_type and expected_type in _TYPE_MAP:
            expected_cls = _TYPE_MAP[expected_type]
            if expected_type == "integer" and isinstance(value, bool):
                errors.append(f"Field '{path}' must be integer, got bool")
                return
            if not isinstance(value, expected_cls):
                errors.append(f"Field '{path}' must be {expected_type}, got {type(value).__name__}")
                return

        if isinstance(value, (int, float)):
            if "minimum" in node_schema and value < node_schema["minimum"]:
                errors.append(f"Field '{path}' must be >= {node_schema['minimum']}")
            if "maximum" in node_schema and value > node_schema["maximum"]:
                errors.append(f"Field '{path}' must be <= {node_schema['maximum']}")

        if "enum" in node_schema and value not in node_schema["enum"]:
            errors.append(f"Field '{path}' must be one of {node_schema['enum']}")

        if expected_type == "object" and isinstance(value, dict):
            required = node_schema.get("required", []) or []
            properties = node_schema.get("properties", {}) or {}
            for key in required:
                if key not in value:
                    errors.append(f"Missing required field: {path}.{key}" if path else f"Missing required field: {key}")
            for key, child in value.items():
                child_schema = properties.get(key)
                if isinstance(child_schema, dict):
                    child_path = f"{path}.{key}" if path else key
                    _validate_node(child_schema, child, child_path, errors)

            any_of = node_schema.get("anyOf")
            if isinstance(any_of, list) and any_of:
                matched = False
                for branch in any_of:
                    branch_errors: List[str] = []
                    _validate_node(branch if isinstance(branch, dict) else {}, value, path, branch_errors)
                    if not branch_errors:
                        matched = True
                        break
                if not matched:
                    errors.append(f"Field '{path}' does not match any allowed schema")

        if expected_type == "array" and isinstance(value, list):
            item_schema = node_schema.get("items")
            if isinstance(item_schema, dict):
                for idx, item in enumerate(value):
                    item_path = f"{path}[{idx}]"
                    _validate_node(item_schema, item, item_path, errors)

    errors: List[str] = []
    if not schema:
        return True, errors
    if not isinstance(args, dict):
        return False, ["Tool args must be a JSON object."]

    _validate_node(schema, args, "", errors)

    return len(errors) == 0, errors
