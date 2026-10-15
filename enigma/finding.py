"""Stage B: Structured Finding model.

Represents a single evidence-backed maintenance issue.
Uses deterministic IDs based on file+classification.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

from .inspector import EvidenceRef


SEVERITY_LEVELS = ("LOW", "MEDIUM", "HIGH")
CLASSIFICATION_TYPES = (
    "DEPENDENCY_VERSION_CONFLICT",
    "STALE_DEPENDENCY",
    "DEPRECATED_API",
    "OUTDATED_METADATA",
    "UNMAINTAINED_DEPENDENCY",
    "CONFIGURATION_MISMATCH",
)
STATUS_VALUES = ("OPEN", "PROPOSED", "APPLIED", "SKIPPED", "REJECTED")


@dataclass
class Finding:
    """A single, evidence-backed maintenance finding."""
    title: str
    description: str
    classification: str
    severity: str
    affected_files: list[str]
    evidence: list[EvidenceRef]
    expected_outcome: str
    proposed_action: str
    confidence: float          # 0.0–1.0
    uncertainty: str
    status: str = "OPEN"
    status_reason: str = ""
    finding_id: str = ""

    def __post_init__(self):
        if not self.finding_id:
            # deterministic ID from title + first affected file
            key = f"{self.title}:{self.affected_files[0] if self.affected_files else ''}"
            self.finding_id = "FND-" + hashlib.sha1(key.encode()).hexdigest()[:8].upper()

    def to_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "title": self.title,
            "description": self.description,
            "classification": self.classification,
            "severity": self.severity,
            "affected_files": self.affected_files,
            "evidence": [
                {
                    "file_path": e.file_path,
                    "line_number": e.line_number,
                    "excerpt": e.excerpt,
                    "status": e.status,
                }
                for e in self.evidence
            ],
            "expected_outcome": self.expected_outcome,
            "proposed_action": self.proposed_action,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "status": self.status,
            "status_reason": self.status_reason,
        }


def build_pydantic_conflict_finding(inspection_result) -> Optional[Finding]:
    """
    Build a Finding for the Pydantic v1/v2 conflict observed in LinkWatch.

    pyproject.toml: pydantic>=2  (v2 required)
    requirements.txt: pydantic==1.10.13  (v1 pinned)
    config.py: uses @validator, class Config (v1 API, broken on v2)

    Returns None if the evidence is insufficient.
    """
    pydantic_evidence = [
        e for e in inspection_result.evidence
        if "pydantic" in e.excerpt.lower() or "validator" in e.excerpt.lower()
           or "Config" in e.excerpt or "anystr" in e.excerpt
    ]

    if not pydantic_evidence:
        return None

    pyproject_dep = inspection_result.pyproject_deps.get("pydantic", "")
    req_dep = inspection_result.requirements_deps.get("pydantic", "")

    affected = []
    if inspection_result.pyproject_path:
        affected.append(inspection_result.pyproject_path)
    if inspection_result.requirements_path:
        affected.append(inspection_result.requirements_path)
    # add config.py path from evidence
    for e in pydantic_evidence:
        if "config.py" in e.file_path and e.file_path not in affected:
            affected.append(e.file_path)

    desc = (
        f"LinkWatch declares pydantic>=2 in pyproject.toml ({pyproject_dep!r}) "
        f"but pins pydantic==1.10.13 in requirements.txt. "
        f"The source file linkwatch/config.py uses the Pydantic v1 API "
        f"(@validator decorator, inner Config class, anystr_strip_whitespace) "
        f"which was removed in Pydantic v2. "
        f"Installing pydantic>=2 breaks the application at import time. "
        f"Installing pydantic==1.10.13 contradicts the declared constraint."
    )

    return Finding(
        title="Pydantic v1/v2 version conflict and deprecated API usage",
        description=desc,
        classification="DEPENDENCY_VERSION_CONFLICT",
        severity="HIGH",
        affected_files=affected,
        evidence=pydantic_evidence,
        expected_outcome=(
            "requirements.txt updated to pydantic>=2,<3; "
            "config.py migrated from @validator / inner Config to Pydantic v2 "
            "field_validator / model_config. Application imports without error "
            "on pydantic 2.x."
        ),
        proposed_action=(
            "1. Update requirements.txt: replace 'pydantic==1.10.13' with 'pydantic>=2,<3'. "
            "2. Migrate config.py: replace @validator with @field_validator, "
            "replace 'class Config' with model_config = ConfigDict(...), "
            "replace anystr_strip_whitespace with str_strip_whitespace. "
            "Smallest safe change: migrate config.py to Pydantic v2 API "
            "and update requirements.txt pin."
        ),
        confidence=0.97,
        uncertainty=(
            "Other files may also use Pydantic v1 API if added after inspection. "
            "The fix must be tested with pydantic 2.x installed."
        ),
    )
