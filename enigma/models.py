"""Core data models for the Enigma maintenance workflow."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Status(str, Enum):
    OBSERVED = "OBSERVED"
    AI_RECOMMENDATION = "AI_RECOMMENDATION"
    VERIFIED_BY_EXECUTION = "VERIFIED_BY_EXECUTION"
    NOT_VERIFIED = "NOT_VERIFIED"
    BLOCKED = "BLOCKED"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class OverallStatus(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


@dataclass
class EvidenceRef:
    """A reference to evidence found in the repository."""
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    snippet: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "snippet": self.snippet,
            "description": self.description,
        }


@dataclass
class Finding:
    """A maintenance finding backed by evidence."""
    finding_id: str = ""
    title: str = ""
    description: str = ""
    classification: str = "dependency-maintenance"
    severity: Severity = Severity.MEDIUM
    evidence: list[EvidenceRef] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    expected_outcome: str = ""
    confidence: float = 0.0
    uncertainty: str = ""
    proposed_action: str = ""
    status: Status = Status.OBSERVED
    reason: str = ""

    def __post_init__(self):
        if not self.finding_id:
            self.finding_id = f"ENIGMA-{uuid.uuid4().hex[:8].upper()}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "title": self.title,
            "description": self.description,
            "classification": self.classification,
            "severity": self.severity.value,
            "evidence": [e.to_dict() for e in self.evidence],
            "affected_files": self.affected_files,
            "expected_outcome": self.expected_outcome,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "proposed_action": self.proposed_action,
            "status": self.status.value,
            "reason": self.reason,
        }


@dataclass
class ModelRecommendation:
    """A recommendation from a language model."""
    model_name: str = ""
    model_runtime: str = ""
    recommendation: str = ""
    reasoning: str = ""
    proposed_changes: list[dict[str, str]] = field(default_factory=list)
    validation_result: str = "NOT_VERIFIED"
    inference_occurred: bool = False
    error: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "model_runtime": self.model_runtime,
            "recommendation": self.recommendation,
            "reasoning": self.reasoning,
            "proposed_changes": self.proposed_changes,
            "validation_result": self.validation_result,
            "inference_occurred": self.inference_occurred,
            "error": self.error,
        }


@dataclass
class CommandResult:
    """Result of executing a verification command."""
    command: list[str] | str = ""
    working_dir: str = ""
    interpreter: str = ""
    interpreter_version: str = ""
    exit_code: int | None = None
    stdout_summary: str = ""
    stderr_summary: str = ""
    started_at: str = ""
    ended_at: str = ""
    duration_seconds: float = 0.0
    status: str = "NOT_RUN"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command if isinstance(self.command, str) else " ".join(self.command),
            "working_dir": self.working_dir,
            "interpreter": self.interpreter,
            "interpreter_version": self.interpreter_version,
            "exit_code": self.exit_code,
            "stdout_summary": self.stdout_summary[:2000],
            "stderr_summary": self.stderr_summary[:2000],
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass
class ChangeRecord:
    """Record of a change applied to the target repository."""
    file_path: str = ""
    change_type: str = ""  # 'modified', 'created', 'deleted'
    description: str = ""
    diff_summary: str = ""
    approved: bool = False
    applied: bool = False
    recovery: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "change_type": self.change_type,
            "description": self.description,
            "diff_summary": self.diff_summary,
            "approved": self.approved,
            "applied": self.applied,
            "recovery": self.recovery,
        }


@dataclass
class Capsule:
    """The canonical report capsule from which JSON and Markdown are generated."""
    schema_version: str = "1.0.0"
    run_id: str = ""
    timestamp_utc: str = ""
    overall_status: str = OverallStatus.PARTIAL.value
    project_name: str = "enigma-maintainer"
    repository_url: str = ""
    initial_commit: str = ""
    final_commit: str = ""
    branch: str = ""
    git_state: str = ""
    os_info: str = ""
    python_version: str = ""
    python_312_tested: bool = False
    python_313_tested: bool = False
    finding: dict[str, Any] | None = None
    model_recommendation: dict[str, Any] | None = None
    changes: list[dict[str, Any]] = field(default_factory=list)
    human_approval: str = "auto-approved-dry-run"
    baseline_checks: list[dict[str, Any]] = field(default_factory=list)
    post_change_checks: list[dict[str, Any]] = field(default_factory=list)
    hermes_status: str = "NOT_VERIFIED"
    blockers: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    recovery_instructions: str = ""
    next_steps: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.run_id:
            self.run_id = uuid.uuid4().hex[:12]
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def compute_overall_status(self) -> str:
        """Compute overall status from checks."""
        all_checks = self.baseline_checks + self.post_change_checks
        if not all_checks:
            return OverallStatus.PARTIAL.value
        statuses = [c.get("status", "NOT_RUN") for c in all_checks]
        if all(s == "PASSED" for s in statuses):
            return OverallStatus.PASS.value
        if any(s == "FAILED" for s in statuses):
            return OverallStatus.FAIL.value
        if any(s == "BLOCKED" for s in statuses):
            return OverallStatus.BLOCKED.value
        return OverallStatus.PARTIAL.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "timestamp_utc": self.timestamp_utc,
            "overall_status": self.overall_status,
            "project_name": self.project_name,
            "repository_url": self.repository_url,
            "initial_commit": self.initial_commit,
            "final_commit": self.final_commit,
            "branch": self.branch,
            "git_state": self.git_state,
            "os_info": self.os_info,
            "python_version": self.python_version,
            "python_312_tested": self.python_312_tested,
            "python_313_tested": self.python_313_tested,
            "finding": self.finding,
            "model_recommendation": self.model_recommendation,
            "changes": self.changes,
            "human_approval": self.human_approval,
            "baseline_checks": self.baseline_checks,
            "post_change_checks": self.post_change_checks,
            "hermes_status": self.hermes_status,
            "blockers": self.blockers,
            "limitations": self.limitations,
            "recovery_instructions": self.recovery_instructions,
            "next_steps": self.next_steps,
        }
