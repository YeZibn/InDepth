import json
import os
import re
from typing import Any, Dict, Optional

from app.core.model.base import GenerationConfig, ModelProvider
from app.eval.schema import RunOutcome, TaskSpec
from app.observability.store import _find_project_root


VERIFIER_AGENT_SYSTEM_PROMPT = (
    "你是独立的评估代理 VerifierAgent。"
    "请根据任务目标、约束和执行证据判断任务是否完成。"
    "你可以使用只读工具检查任务输出相关目录和文件内容。"
    "输出必须是 JSON 对象，字段固定为："
    "passed(boolean), score(number 0~1), reason(string), checks(array of string)。"
    "不要输出除 JSON 之外的任何内容。"
)


class VerifierAgent:
    """Dedicated evaluation agent, independent from SubAgent runtime."""

    def __init__(
        self,
        model_provider: ModelProvider,
        generation_config: Optional[GenerationConfig] = None,
    ):
        self.model_provider = model_provider
        self.generation_config = generation_config
        self.project_root = _find_project_root()
        self._active_evidence_roots: list[str] = []

    def _sanitize_segment(self, value: str, fallback: str) -> str:
        raw = (value or "").strip()
        if not raw:
            return fallback
        sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._")
        return sanitized or fallback

    def _infer_evidence_roots(self, task_spec: TaskSpec, run_outcome: RunOutcome) -> list[str]:
        roots: list[str] = []

        for artifact in task_spec.expected_artifacts:
            raw_path = (artifact.path or "").strip()
            if not raw_path:
                continue
            resolved = self._resolve_under_project(raw_path)
            if os.path.isdir(resolved):
                roots.append(resolved)
            else:
                roots.append(os.path.dirname(resolved))

        # 当前任务的评估输出目录（按 task/run 分目录）
        task_seg = self._sanitize_segment(run_outcome.task_id, "task")
        run_seg = self._sanitize_segment(run_outcome.run_id, "run")
        roots.append(os.path.join(self.project_root, "observability-evals", f"{task_seg}__{run_seg}"))
        roots.append(os.path.join(self.project_root, "observability-evals", task_seg))

        # 兼容历史默认目录
        roots.append(os.path.join(self.project_root, "work"))

        unique: list[str] = []
        seen = set()
        for root in roots:
            abs_root = os.path.abspath(root)
            if abs_root in seen:
                continue
            if os.path.commonpath([abs_root, self.project_root]) != os.path.abspath(self.project_root):
                continue
            seen.add(abs_root)
            unique.append(abs_root)
        return unique

    def _build_user_prompt(
        self,
        task_spec: TaskSpec,
        run_outcome: RunOutcome,
        evidence_roots: list[str],
    ) -> str:
        constraints = "\n".join([f"- {x}" for x in task_spec.constraints]) or "- (none)"
        rubric = task_spec.llm_judge_rubric or "评估任务完成度、约束满足度、证据充分性。"
        roots_text = (
            "\n".join([f"- {os.path.relpath(x, self.project_root)}" for x in evidence_roots])
            if evidence_roots
            else "- (none)"
        )
        return (
            f"[任务目标]\n{task_spec.goal or '(empty)'}\n\n"
            f"[任务类型]\n{task_spec.task_type}\n\n"
            f"[约束]\n{constraints}\n\n"
            f"[评分标准]\n{rubric}\n\n"
            f"[证据根目录（由先前任务输出推断）]\n{roots_text}\n\n"
            f"[用户输入]\n{run_outcome.user_input}\n\n"
            f"[最终回答]\n{run_outcome.final_answer}\n\n"
            f"[执行证据]\n"
            f"- stop_reason: {run_outcome.stop_reason}\n"
            f"- runtime_status: {run_outcome.runtime_status}\n"
            f"- tool_failures: {json.dumps(run_outcome.tool_failures[:5], ensure_ascii=False)}\n\n"
            "要求：请优先通过工具检查上述证据根目录，再给出结论。"
            "请直接输出 JSON。"
        )

    def _extract_finish_reason_and_message(self, raw: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        if not isinstance(raw, dict):
            return "", {}
        choices = raw.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return "", {}
        choice0 = choices[0] if isinstance(choices[0], dict) else {}
        finish_reason = str(choice0.get("finish_reason", "") or "").strip()
        message = choice0.get("message", {})
        if not isinstance(message, dict):
            message = {}
        return finish_reason, message

    def _resolve_under_project(self, path: str) -> str:
        path = (path or "").strip()
        if not path:
            raise ValueError("path is required")
        candidate = path if os.path.isabs(path) else os.path.join(self.project_root, path)
        abs_path = os.path.abspath(candidate)
        common = os.path.commonpath([abs_path, self.project_root])
        if common != os.path.abspath(self.project_root):
            raise ValueError("path outside project root is not allowed")
        return abs_path

    def _resolve_evidence_root(self, root_path: str = "") -> str:
        if root_path and root_path.strip():
            return self._resolve_under_project(root_path)
        if self._active_evidence_roots:
            return self._active_evidence_roots[0]
        return os.path.join(self.project_root, "work")

    def _tool_list_work_files(self, subpath: str = "", max_entries: int = 200, root_path: str = "") -> Dict[str, Any]:
        max_entries = max(1, min(int(max_entries), 2000))
        root_base = self._resolve_evidence_root(root_path)
        root = root_base if not subpath else self._resolve_under_project(os.path.join(root_base, subpath))
        if not os.path.exists(root):
            return {"success": False, "error": f"path not found: {root}"}
        if not os.path.isdir(root):
            return {"success": False, "error": f"not a directory: {root}"}

        rows = []
        count = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            filenames.sort()
            rel_dir = os.path.relpath(dirpath, self.project_root)
            for name in filenames:
                if count >= max_entries:
                    break
                abs_path = os.path.join(dirpath, name)
                rows.append(
                    {
                        "path": os.path.relpath(abs_path, self.project_root),
                        "size": os.path.getsize(abs_path),
                        "dir": rel_dir,
                    }
                )
                count += 1
            if count >= max_entries:
                break
        return {"success": True, "root": os.path.relpath(root, self.project_root), "files": rows, "count": len(rows)}

    def _tool_read_project_file(self, path: str, max_chars: int = 8000) -> Dict[str, Any]:
        max_chars = max(256, min(int(max_chars), 50000))
        abs_path = self._resolve_under_project(path)
        if not os.path.exists(abs_path):
            return {"success": False, "error": f"file not found: {path}"}
        if not os.path.isfile(abs_path):
            return {"success": False, "error": f"not a file: {path}"}
        with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(max_chars)
        return {
            "success": True,
            "path": os.path.relpath(abs_path, self.project_root),
            "content": content,
            "truncated": os.path.getsize(abs_path) > len(content.encode("utf-8")),
        }

    def _tool_schemas(self) -> list[Dict[str, Any]]:
        return [
            {
                "name": "list_work_files",
                "description": "List files under selected evidence directory for evidence checks.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "root_path": {
                            "type": "string",
                            "description": "optional project-relative evidence root path; default is first inferred evidence root",
                        },
                        "subpath": {"type": "string", "description": "relative subpath under selected root_path"},
                        "max_entries": {"type": "integer", "minimum": 1, "maximum": 2000},
                    },
                    "required": [],
                },
            },
            {
                "name": "read_project_file",
                "description": "Read a text file under current project root.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "max_chars": {"type": "integer", "minimum": 256, "maximum": 50000},
                    },
                    "required": ["path"],
                },
            },
        ]

    def _invoke_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if tool_name == "list_work_files":
                return self._tool_list_work_files(
                    subpath=str(args.get("subpath", "") or ""),
                    max_entries=int(args.get("max_entries", 200) or 200),
                    root_path=str(args.get("root_path", "") or ""),
                )
            if tool_name == "read_project_file":
                return self._tool_read_project_file(
                    path=str(args.get("path", "") or ""),
                    max_chars=int(args.get("max_chars", 8000) or 8000),
                )
            return {"success": False, "error": f"unknown tool: {tool_name}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _parse_json(self, text: str) -> Dict[str, Any]:
        content = (text or "").strip()
        if not content:
            return {"passed": False, "score": 0.0, "reason": "empty_response", "checks": []}
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:].strip()
        try:
            payload = json.loads(content)
            passed = bool(payload.get("passed", False))
            score = float(payload.get("score", 0.0))
            score = max(0.0, min(1.0, score))
            reason = str(payload.get("reason", "")).strip() or "no_reason"
            checks = payload.get("checks", [])
            if not isinstance(checks, list):
                checks = []
            checks = [str(x).strip() for x in checks if str(x).strip()]
            return {"passed": passed, "score": score, "reason": reason, "checks": checks}
        except Exception:
            lowered = content.lower()
            if "pass" in lowered or "完成" in content or "success" in lowered:
                return {"passed": True, "score": 0.7, "reason": "fallback_positive_parse", "checks": []}
            return {"passed": False, "score": 0.3, "reason": "fallback_negative_parse", "checks": []}

    def evaluate(self, task_spec: TaskSpec, run_outcome: RunOutcome) -> Dict[str, Any]:
        evidence_roots = self._infer_evidence_roots(task_spec=task_spec, run_outcome=run_outcome)
        self._active_evidence_roots = evidence_roots
        messages = [
            {"role": "system", "content": VERIFIER_AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": self._build_user_prompt(task_spec, run_outcome, evidence_roots)},
        ]
        tools = self._tool_schemas()

        max_steps = 8
        last_text = ""
        for _ in range(max_steps):
            output = self.model_provider.generate(
                messages=messages,
                tools=tools,
                config=self.generation_config,
            )
            last_text = output.content or ""
            finish_reason, raw_message = self._extract_finish_reason_and_message(output.raw)
            if finish_reason == "tool_calls":
                tool_calls = raw_message.get("tool_calls", []) if isinstance(raw_message, dict) else []
                messages.append(
                    {
                        "role": "assistant",
                        "content": raw_message.get("content", "") if isinstance(raw_message, dict) else "",
                        "tool_calls": tool_calls,
                    }
                )
                for call in tool_calls:
                    call_id = str(call.get("id", ""))
                    fn = call.get("function", {}) if isinstance(call, dict) else {}
                    name = str(fn.get("name", "")).strip()
                    raw_args = fn.get("arguments", "{}")
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                        if not isinstance(args, dict):
                            args = {}
                    except Exception:
                        args = {}
                    tool_result = self._invoke_tool(name, args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": json.dumps(tool_result, ensure_ascii=False),
                        }
                    )
                continue

            parsed = self._parse_json(last_text)
            parsed["raw"] = (last_text or "")[:1200]
            return parsed

        return {
            "passed": False,
            "score": 0.0,
            "reason": "verifier_agent_max_steps_reached",
            "checks": [],
            "raw": (last_text or "")[:1200],
        }
