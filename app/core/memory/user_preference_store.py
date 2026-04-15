import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


class UserPreferenceStore:
    """Single-file markdown store for user preferences."""

    def __init__(self, file_path: str = "memory/preferences/user-preferences.md"):
        self.file_path = file_path
        self._ensure_file()

    def _now_iso(self) -> str:
        return datetime.now().astimezone().replace(microsecond=0).isoformat()

    def _ensure_file(self) -> None:
        path = Path(self.file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return
        self._write_data(
            {
                "meta": {"version": 1, "updated_at": self._now_iso(), "enabled": True},
                "preferences": {},
            }
        )

    def _read_text(self) -> str:
        try:
            return Path(self.file_path).read_text(encoding="utf-8")
        except Exception:
            return ""

    def _write_text_atomic(self, text: str) -> None:
        path = Path(self.file_path)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(str(tmp), str(path))

    def _parse_value(self, raw: str) -> Any:
        text = (raw or "").strip()
        if text.startswith("[") and text.endswith("]"):
            items = [x.strip() for x in text[1:-1].split(",") if x.strip()]
            return items
        return text

    def _format_value(self, value: Any) -> str:
        if isinstance(value, list):
            cleaned = [str(x).strip() for x in value if str(x).strip()]
            return "[" + ", ".join(cleaned) + "]"
        return str(value or "").strip()

    def _parse_enabled(self, line: str) -> bool:
        raw = (line.split(":", 1)[1] if ":" in line else "").strip().lower()
        return raw in {"true", "1", "yes", "on", "__yes__"}

    def _read_data(self) -> Dict[str, Any]:
        text = self._read_text()
        if not text.strip():
            return {"meta": {"version": 1, "updated_at": self._now_iso(), "enabled": True}, "preferences": {}}

        meta: Dict[str, Any] = {"version": 1, "updated_at": self._now_iso(), "enabled": True}
        prefs: Dict[str, Dict[str, Any]] = {}
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("- version:"):
                raw = (line.split(":", 1)[1] if ":" in line else "").strip()
                try:
                    meta["version"] = int(raw)
                except Exception:
                    pass
            elif line.startswith("- updated_at:"):
                meta["updated_at"] = (line.split(":", 1)[1] if ":" in line else "").strip()
            elif line.startswith("- enabled:"):
                meta["enabled"] = self._parse_enabled(line)
            elif line.startswith("### "):
                key = line[4:].strip()
                record: Dict[str, Any] = {
                    "value": "",
                    "source": "explicit_user",
                    "confidence": 1.0,
                    "updated_at": meta["updated_at"],
                    "note": "",
                }
                j = i + 1
                while j < len(lines):
                    row = lines[j].strip()
                    if not row:
                        j += 1
                        continue
                    if row.startswith("### "):
                        break
                    if row.startswith("- value:"):
                        record["value"] = self._parse_value(row.split(":", 1)[1] if ":" in row else "")
                    elif row.startswith("- source:"):
                        record["source"] = (row.split(":", 1)[1] if ":" in row else "").strip() or "explicit_user"
                    elif row.startswith("- confidence:"):
                        raw = (row.split(":", 1)[1] if ":" in row else "").strip()
                        try:
                            record["confidence"] = float(raw)
                        except Exception:
                            record["confidence"] = 1.0
                    elif row.startswith("- updated_at:"):
                        record["updated_at"] = (row.split(":", 1)[1] if ":" in row else "").strip() or meta["updated_at"]
                    elif row.startswith("- note:"):
                        record["note"] = (row.split(":", 1)[1] if ":" in row else "").strip()
                    j += 1
                prefs[key] = record
                i = j - 1
            i += 1

        return {"meta": meta, "preferences": prefs}

    def _render(self, data: Dict[str, Any]) -> str:
        meta = data.get("meta", {}) if isinstance(data.get("meta"), dict) else {}
        prefs = data.get("preferences", {}) if isinstance(data.get("preferences"), dict) else {}
        lines: List[str] = [
            "# User Preferences",
            "",
            "meta:",
            f"- version: {int(meta.get('version', 1) or 1)}",
            f"- updated_at: {str(meta.get('updated_at', self._now_iso()) or self._now_iso())}",
            f"- enabled: {'true' if bool(meta.get('enabled', True)) else 'false'}",
            "",
            "## preferences",
            "",
        ]
        for key in sorted(prefs.keys()):
            rec = prefs.get(key, {}) if isinstance(prefs.get(key), dict) else {}
            lines.extend(
                [
                    f"### {key}",
                    f"- value: {self._format_value(rec.get('value', ''))}",
                    f"- source: {str(rec.get('source', 'explicit_user') or 'explicit_user').strip()}",
                    f"- confidence: {float(rec.get('confidence', 1.0) or 1.0):.2f}",
                    f"- updated_at: {str(rec.get('updated_at', self._now_iso()) or self._now_iso()).strip()}",
                    f"- note: {str(rec.get('note', '') or '').strip()}",
                    "",
                ]
            )
        return "\n".join(lines).rstrip() + "\n"

    def _write_data(self, data: Dict[str, Any]) -> None:
        rendered = self._render(data)
        self._write_text_atomic(rendered)

    def is_enabled(self) -> bool:
        data = self._read_data()
        meta = data.get("meta", {}) if isinstance(data.get("meta"), dict) else {}
        return bool(meta.get("enabled", True))

    def set_enabled(self, enabled: bool) -> None:
        data = self._read_data()
        meta = data.get("meta", {}) if isinstance(data.get("meta"), dict) else {}
        meta["enabled"] = bool(enabled)
        meta["updated_at"] = self._now_iso()
        data["meta"] = meta
        self._write_data(data)

    def list_preferences(self) -> Dict[str, Dict[str, Any]]:
        data = self._read_data()
        prefs = data.get("preferences", {})
        return prefs if isinstance(prefs, dict) else {}

    def upsert_preference(
        self,
        key: str,
        value: Any,
        source: str = "explicit_user",
        confidence: float = 1.0,
        note: str = "",
    ) -> None:
        key_norm = str(key or "").strip()
        if not key_norm:
            return
        if isinstance(value, list):
            dedup: List[str] = []
            for item in value:
                part = str(item or "").strip()
                if part and part not in dedup:
                    dedup.append(part)
            value = dedup
        data = self._read_data()
        prefs = data.get("preferences", {}) if isinstance(data.get("preferences"), dict) else {}
        now = self._now_iso()
        prefs[key_norm] = {
            "value": value,
            "source": str(source or "explicit_user").strip() or "explicit_user",
            "confidence": max(0.0, min(1.0, float(confidence))),
            "updated_at": now,
            "note": str(note or "").strip(),
        }
        data["preferences"] = prefs
        meta = data.get("meta", {}) if isinstance(data.get("meta"), dict) else {}
        meta["updated_at"] = now
        data["meta"] = meta
        self._write_data(data)

    def delete_preference(self, key: str) -> None:
        key_norm = str(key or "").strip()
        if not key_norm:
            return
        data = self._read_data()
        prefs = data.get("preferences", {}) if isinstance(data.get("preferences"), dict) else {}
        if key_norm in prefs:
            prefs.pop(key_norm, None)
            data["preferences"] = prefs
            meta = data.get("meta", {}) if isinstance(data.get("meta"), dict) else {}
            meta["updated_at"] = self._now_iso()
            data["meta"] = meta
            self._write_data(data)

    def clear_preferences(self) -> None:
        data = self._read_data()
        data["preferences"] = {}
        meta = data.get("meta", {}) if isinstance(data.get("meta"), dict) else {}
        meta["updated_at"] = self._now_iso()
        data["meta"] = meta
        self._write_data(data)

    def extract_explicit_updates(self, user_input: str) -> Dict[str, Any]:
        text = str(user_input or "").strip()
        if not text:
            return {}
        updates: Dict[str, Any] = {}

        m = re.search(r"(?:我是|我是一名|我的职业是)\s*([^\n，。；;]{2,30})", text)
        if m:
            updates["job_role"] = m.group(1).strip()

        m = re.search(r"(?:我喜欢|我感兴趣的是)\s*([^\n。；;]{2,80})", text)
        if m:
            raw = m.group(1).strip()
            topics = [x.strip() for x in re.split(r"[、,，/和与]", raw) if x.strip()]
            if topics:
                updates["interest_topics"] = topics[:8]

        if re.search(r"(请用中文|中文回答|使用中文)", text):
            updates["language_preference"] = "中文"
        elif re.search(r"(请用英文|英文回答|使用英文)", text, flags=re.IGNORECASE):
            updates["language_preference"] = "英文"

        if re.search(r"(简洁|精简|结论先行)", text):
            updates["response_style"] = "简洁、结论先行"
        elif re.search(r"(详细|展开|一步一步|步骤)", text):
            updates["response_style"] = "详细、步骤化"

        m = re.search(r"(?:常用(?:技术栈|工具)|技术栈是)\s*([^\n。；;]{2,120})", text)
        if m:
            raw = m.group(1).strip()
            stack = [x.strip() for x in re.split(r"[、,，/和与]", raw) if x.strip()]
            if stack:
                updates["tooling_stack"] = stack[:10]

        return updates

    def capture_from_user_input(self, user_input: str, allow_inferred_write: bool = False) -> List[str]:
        updates = self.extract_explicit_updates(user_input)
        # V1 默认只做显式声明写入，inferred 预留开关由上层控制。
        if not updates and not allow_inferred_write:
            return []
        changed: List[str] = []
        for key, value in updates.items():
            self.upsert_preference(key=key, value=value, source="explicit_user", confidence=1.0)
            changed.append(key)
        return changed

    def _flatten_value(self, value: Any) -> str:
        if isinstance(value, list):
            return ", ".join([str(x).strip() for x in value if str(x).strip()])
        return str(value or "").strip()

    def _score(self, key: str, value: Any, user_input: str) -> int:
        score = 0
        text = (user_input or "").lower()
        if key in {"language_preference", "response_style"}:
            score += 3
        value_text = self._flatten_value(value).lower()
        for token in [t for t in re.split(r"[\s,，。；;:：/]+", text) if t]:
            if token and (token in key.lower() or token in value_text):
                score += 1
        return score

    def build_recall_items(
        self,
        user_input: str,
        top_k: int = 5,
        always_include_keys: List[str] | Tuple[str, ...] | None = None,
    ) -> List[Tuple[str, str]]:
        if not self.is_enabled():
            return []
        prefs = self.list_preferences()
        if not prefs:
            return []
        always = {str(x).strip() for x in (always_include_keys or []) if str(x).strip()}
        rows: List[Tuple[int, str, str]] = []
        for key, rec in prefs.items():
            if not isinstance(rec, dict):
                continue
            value_text = self._flatten_value(rec.get("value", ""))
            if not value_text:
                continue
            score = self._score(key=key, value=rec.get("value", ""), user_input=user_input)
            if key in always:
                score += 100
            rows.append((score, key, value_text))
        rows.sort(key=lambda x: (-x[0], x[1]))
        picked = [(key, value) for _, key, value in rows[: max(1, int(top_k))] if _ > 0]
        if not picked:
            picked = [(key, value) for _, key, value in rows if key in always][: max(1, int(top_k))]
        return picked

    def render_recall_block(
        self,
        user_input: str,
        top_k: int = 5,
        always_include_keys: List[str] | Tuple[str, ...] | None = None,
        max_chars: int = 240,
    ) -> str:
        items = self.build_recall_items(
            user_input=user_input,
            top_k=top_k,
            always_include_keys=always_include_keys,
        )
        if not items:
            return ""
        segments = [f"{key}={value}" for key, value in items]
        text = "用户偏好召回： " + "；".join(segments) + "。"
        text = text.strip()
        if len(text) <= max(40, int(max_chars)):
            return text
        return text[: max(40, int(max_chars)) - 3] + "..."
