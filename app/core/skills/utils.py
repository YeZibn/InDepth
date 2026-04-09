import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


def is_safe_path(base_dir: Path, requested_path: str) -> bool:
    try:
        full_path = (base_dir / requested_path).resolve()
        return full_path.is_relative_to(base_dir.resolve())
    except Exception:
        return False


def read_file_safe(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8")


def ensure_executable(file_path: Path) -> None:
    mode = file_path.stat().st_mode
    if not (mode & stat.S_IXUSR):
        os.chmod(file_path, mode | stat.S_IXUSR)


@dataclass
class ScriptResult:
    stdout: str
    stderr: str
    returncode: int


def run_script(script_path: Path, args: Optional[List[str]] = None, timeout: int = 30, cwd: Optional[Path] = None) -> ScriptResult:
    ensure_executable(script_path)
    result = subprocess.run(
        [str(script_path), *((args or []))],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
    )
    return ScriptResult(stdout=result.stdout, stderr=result.stderr, returncode=result.returncode)
