"""Tests for enigma.finding — Stage B: Structured Finding."""

from __future__ import annotations

import pytest

from enigma.finding import Finding, build_pydantic_conflict_finding
from enigma.inspector import EvidenceRef, InspectionResult


def _make_inspection_with_conflict():
    """Build a synthetic InspectionResult that triggers the pydantic finding."""
    result = InspectionResult(repo_path="/fake/repo")
    result.pyproject_deps = {"pydantic": ">=2", "requests": "==2.31.0"}
    result.requirements_deps = {"pydantic": "==1.10.13"}
    result.pyproject_path = "/fake/repo/pyproject.toml"
    result.requirements_path = "/fake/repo/requirements.txt"
    result.evidence = [
        EvidenceRef("/fake/repo/pyproject.toml", 12, 'pydantic>=2', "OBSERVED"),
        EvidenceRef("/fake/repo/requirements.txt", 1, 'pydantic==1.10.13', "OBSERVED"),
        EvidenceRef(
            "/fake/repo/mypackage/config.py", 5,
            '[Pydantic v1 @validator decorator (removed in v2)] @validator("name")',
            "OBSERVED",
        ),
        EvidenceRef(
            "/fake/repo/mypackage/config.py", 8,
            "[Pydantic v1 inner Config class (removed in v2)] class Config:",
            "OBSERVED",
        ),
    ]
    return result


def test_finding_built_from_conflict_evidence():
    inspection = _make_inspection_with_conflict()
    finding = build_pydantic_conflict_finding(inspection)
    assert finding is not None
    assert finding.classification == "DEPENDENCY_VERSION_CONFLICT"
    assert finding.severity == "HIGH"


def test_finding_has_deterministic_id():
    inspection = _make_inspection_with_conflict()
    f1 = build_pydantic_conflict_finding(inspection)
    f2 = build_pydantic_conflict_finding(inspection)
    assert f1.finding_id == f2.finding_id
    assert f1.finding_id.startswith("FND-")


def test_finding_id_is_stable_across_runs():
    """Same input → same ID every time."""
    inspection = _make_inspection_with_conflict()
    finding = build_pydantic_conflict_finding(inspection)
    assert finding.finding_id == "FND-" + finding.finding_id[4:]  # prefix check


def test_finding_to_dict_has_required_keys():
    inspection = _make_inspection_with_conflict()
    finding = build_pydantic_conflict_finding(inspection)
    d = finding.to_dict()
    required = {"finding_id", "title", "description", "classification",
                "severity", "affected_files", "evidence", "expected_outcome",
                "proposed_action", "confidence", "uncertainty", "status"}
    assert required.issubset(d.keys())


def test_finding_confidence_range():
    inspection = _make_inspection_with_conflict()
    finding = build_pydantic_conflict_finding(inspection)
    assert 0.0 <= finding.confidence <= 1.0


def test_finding_returns_none_without_evidence():
    inspection = InspectionResult(repo_path="/fake")
    inspection.evidence = []
    finding = build_pydantic_conflict_finding(inspection)
    assert finding is None


def test_finding_not_labelled_security():
    inspection = _make_inspection_with_conflict()
    finding = build_pydantic_conflict_finding(inspection)
    assert "security" not in finding.classification.lower()
    assert "vulnerability" not in finding.title.lower()


def test_finding_affected_files_not_empty():
    inspection = _make_inspection_with_conflict()
    finding = build_pydantic_conflict_finding(inspection)
    assert len(finding.affected_files) > 0


def test_finding_serialization_roundtrip():
    """Dict conversion must produce JSON-serializable output."""
    import json
    inspection = _make_inspection_with_conflict()
    finding = build_pydantic_conflict_finding(inspection)
    d = finding.to_dict()
    serialized = json.dumps(d)
    restored = json.loads(serialized)
    assert restored["finding_id"] == finding.finding_id
