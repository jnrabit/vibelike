"""Request-Modell für das Vibelike-System."""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Any


@dataclass
class Request:
    """Repräsentiert einen Ausführungs-Request."""

    req_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str = ""
    operation: str = ""
    input_files: list[Path] = field(default_factory=list)
    output_dir: Optional[Path] = None
    command: Optional[str] = None
    args: list[str] = field(default_factory=list)
    env: dict = field(default_factory=dict)
    timeout: int = 20
    working_dir: str = "/workspace"
    git_project: Optional[str] = None
    git_user: Optional[dict] = None
    status: str = "pending"
    priority: int = 0
    retries: int = 0
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    duration_ms: Optional[float] = None
    output_files: list[Path] = field(default_factory=list)
    user: str = ""
    comment: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Konvertiert das Request-Objekt in ein Dictionary."""
        result = asdict(self)
        # Konvertiere Path-Objekte zu Strings
        result["input_files"] = [str(p) for p in self.input_files]
        result["output_dir"] = str(self.output_dir) if self.output_dir else None
        result["output_files"] = [str(p) for p in self.output_files]
        # Konvertiere datetime zu ISO-Format
        for key in ["created_at", "started_at", "completed_at"]:
            if result[key] is not None:
                result[key] = result[key].isoformat()
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "Request":
        """Erstellt ein Request-Objekt aus einem Dictionary."""
        # Konvertiere Strings zurück zu Path
        if "input_files" in data:
            data["input_files"] = [Path(p) for p in data["input_files"]]
        if "output_dir" in data and data["output_dir"]:
            data["output_dir"] = Path(data["output_dir"])
        if "output_files" in data:
            data["output_files"] = [Path(p) for p in data["output_files"]]
        # Konvertiere ISO-Strings zurück zu datetime
        for key in ["created_at", "started_at", "completed_at"]:
            if data.get(key):
                data[key] = datetime.fromisoformat(data[key])
        return cls(**data)

    def to_json(self) -> str:
        """Konvertiert das Request-Objekt in JSON."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "Request":
        """Erstellt ein Request-Objekt aus JSON."""
        return cls.from_dict(json.loads(json_str))

    def generate_triples(
        self,
        tool: "Tool",  # type: ignore
        exit_code: int,
        output_files: list[Path],
        duration_ms: float
    ) -> list[dict]:
        """
        Generiert Triples aus dem Request und dem Ergebnis.

        Args:
            tool: Verwendetes Tool
            exit_code: Exit-Code der Ausführung
            output_files: Liste der Output-Dateien
            duration_ms: Ausführungsdauer in ms

        Returns:
            Liste von Triple-Dicts für ossifikat
        """
        triples = []
        context = {
            "req_id": self.req_id,
            "tool_name": tool.name,
            "tool_version": tool.version or "unknown",
            "tool_path": str(tool.path),
            "input": ", ".join(p.name for p in self.input_files) if self.input_files else "",
            "input_path": ", ".join(str(p) for p in self.input_files) if self.input_files else "",
            "output": ", ".join(p.name for p in output_files) if output_files else "",
            "output_path": ", ".join(str(p) for p in output_files) if output_files else "",
            "exit_code": str(exit_code),
            "duration_ms": str(duration_ms),
            "operation": self.operation,
            "user": self.user,
            "git_project": self.git_project or "",
            "status": "success" if exit_code == 0 else "failed"
        }

        # Tool-spezifische Triples
        for template in tool.triple_templates:
            if template.evaluate(**context):
                subject, predicate, obj, confidence = template.render(**context)
                triples.append({
                    "subject": subject,
                    "predicate": predicate,
                    "object": obj,
                    "source": f"tool:{self.req_id}",
                    "confidence": confidence
                })

        # Generische Triples (falls keine tool-spezifischen)
        if not triples:
            triples.append({
                "subject": self.req_id,
                "predicate": "executed_tool",
                "object": tool.name,
                "source": f"tool:{self.req_id}",
                "confidence": 1.0
            })
            triples.append({
                "subject": self.req_id,
                "predicate": "has_status",
                "object": "success" if exit_code == 0 else "failed",
                "source": f"tool:{self.req_id}",
                "confidence": 1.0
            })
            triples.append({
                "subject": self.req_id,
                "predicate": "has_exit_code",
                "object": str(exit_code),
                "source": f"tool:{self.req_id}",
                "confidence": 1.0
            })
            triples.append({
                "subject": self.req_id,
                "predicate": "has_duration_ms",
                "object": str(duration_ms),
                "source": f"tool:{self.req_id}",
                "confidence": 1.0
            })

        # Git-spezifische Triples
        if self.git_project:
            triples.append({
                "subject": self.git_project,
                "predicate": "tool_operation",
                "object": f"{tool.name} {self.operation}",
                "source": f"tool:{self.req_id}",
                "confidence": 0.9 if exit_code != 0 else 1.0
            })

        return triples
