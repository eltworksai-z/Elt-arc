from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.agents.engine import DiagnosticEngine
from app.core.config import get_settings
from app.core.timeutil import utc_now_iso
from app.simulator.palletizer import PalletizerSimulator

AgentMode = Literal["improved", "baseline"]
Emit = Callable[[str, dict[str, Any]], None]


def _new_engine() -> DiagnosticEngine:
    settings = get_settings()
    return DiagnosticEngine(max_tests=settings.max_diagnostic_tests, timeout_s=settings.investigation_timeout_s)


@dataclass
class AgentContext:
    session_id: str
    mode: AgentMode
    sim: PalletizerSimulator
    emit: Emit
    record_history: bool = True
    incident_id: str | None = None
    incident_closed: bool = False
    engine: DiagnosticEngine = field(default_factory=lambda: _new_engine())
    evidence: list[dict[str, Any]] = field(default_factory=list)
    tool_log: list[dict[str, Any]] = field(default_factory=list)
    executed_tests: list[dict[str, Any]] = field(default_factory=list)
    blocked_attempts: list[dict[str, Any]] = field(default_factory=list)
    declined_requests: list[dict[str, Any]] = field(default_factory=list)
    operator_inbox: list[str] = field(default_factory=list)
    operator_notes: list[str] = field(default_factory=list)
    reports: dict[str, dict[str, Any]] = field(default_factory=dict)
    spoken: list[str] = field(default_factory=list)

    def reset_investigation(self) -> None:
        self.incident_id = None
        self.incident_closed = False
        self.engine = _new_engine()
        self.executed_tests = []
        self.blocked_attempts = []

    def add_evidence(self, source: str, summary: str, data: dict[str, Any] | None = None) -> str:
        evidence_id = f"E{len(self.evidence) + 1}"
        item = {"id": evidence_id, "source": source, "summary": summary, "data": data or {}, "ts": utc_now_iso()}
        self.evidence.append(item)
        self.emit("evidence.added", item)
        return evidence_id

    def evidence_ids(self) -> set[str]:
        return {e["id"] for e in self.evidence}

    def drain_operator_inbox(self) -> list[dict[str, str]]:
        drained = []
        while self.operator_inbox:
            text = self.operator_inbox.pop(0)
            self.operator_notes.append(text)
            evidence_id = self.add_evidence("operator", f"Operator said: {text}")
            drained.append({"evidence_id": evidence_id, "text": text})
            self.emit("timeline", {"kind": "operator", "label": "Operator input added to investigation", "detail": text})
        return drained

    def timeline(self, kind: str, label: str, detail: str = "") -> None:
        self.emit("timeline", {"kind": kind, "label": label, "detail": detail})
