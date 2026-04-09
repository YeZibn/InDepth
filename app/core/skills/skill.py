from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Skill:
    name: str
    description: str
    instructions: str
    source_path: str
    scripts: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None
    license: Optional[str] = None
    compatibility: Optional[str] = None
    allowed_tools: Optional[List[str]] = None
