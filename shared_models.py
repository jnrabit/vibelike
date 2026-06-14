"""Gemeinsame Datenmodelle, um zirkuläre Importe zu vermeiden."""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from pathlib import Path
import json
import time

ROOT = Path(__file__).parent
AGENT_LOG = ROOT / "data" / "agent_log.jsonl"

@dataclass
class Step:
    """Eine Iteration des Agent-Loops: was wurde versucht, was passierte."""
    query: str
    action: str
    params: Dict[str, Any]
    result: str
    state_before: Dict[str, Any]
    state_after: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    correlation_id: Optional[str] = None

    def to_json(self) -> str:
        d = asdict(self)
        d["timestamp"] = self.timestamp
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> "Step":
        d = json.loads(line)
        return cls(**d)


class AgentLog:
    def __init__(self, log_path: Path = AGENT_LOG):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, step: Step) -> None:
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(step.to_json() + "\n")

    def read_all(self) -> List[Step]:
        if not self.log_path.exists():
            return []
        with open(self.log_path, "r", encoding="utf-8") as f:
            return [Step.from_json(line) for line in f if line.strip()]

    def recent(self, n: int = 10) -> List[Step]:
        """Letzte N Steps aus dem Log."""
        all_steps = self.read_all()
        return all_steps[-n:] if all_steps else []

    def stats(self) -> Dict[str, Any]:
        """Statistiken über das Log."""
        all_steps = self.read_all()
        by_action = {}
        for s in all_steps:
            by_action[s.action] = by_action.get(s.action, 0) + 1
        return {"total": len(all_steps), "by_action": by_action}
