"""Tests for enigma.capsule — Stage F: Capsule generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from enigma.capsule import EnigmaCapsule, generate_capsule_files
from enigma.schema import validate_capsule, ValidationResult


def _make_full_capsule(tmp_path) -> EnigmaCapsule:
    capsule = EnigmaCapsule(
        repo_path=str(tmp_path),
        project_name="linkwatch",
        project_version="0.3.1",
        initial_commit="f52f3930",
        branch="main",
        python_312_tested=True,
        finding={
            "finding_id": "FND-TEST0001",
            "title": "Pydantic v1/v2 conflict",
            "description": "test description",
            "classification": "DEPENDENCY_VERSION_CONFLICT",
            "severity": "HIGH",
            "affected_files": ["pyproject.toml", "requirements.txt"],
            "evidence": [],
            "expected_outcome": "pydantic v2 compat",
            "proposed_action": "migrate config.py",
            "confidence": 0.97,
            "uncertainty": "minor",
            "status": "OPEN",
            "status_reason": "",
        },
        model_result={
            "status": "BLOCKED",
            "inference_performed": False,
            "label": "NOT_VERIFIED",
            "blocker_reason": "no ollama",
            "model_id": None,
            "runtime": "ollama",
        },
        review_result={
            "approved": False,
            "dry_run": True,
            "approval_source": "dry_run",
            "skipped_reason": "dry_run",
            "changes_applied": [],
        },
        baseline_checks=[
            {"label": "import_check", "command": ["python", "-c", "import linkwatch"],
             "cwd": str(tmp_path), "interpreter": "Python 3.12.0",
             "exit_code": 0, "status": "PASS", "elapsed_seconds": 0.5,
             "stdout_excerpt": "import OK", "stderr_excerpt": ""},
        ],
    )
    capsule.blockers = ["Gemma model not installed"]
    capsule.limitations = ["Python 3.13 not tested"]
    capsule.recovery_instructions = ["git checkout -- linkwatch/config.py"]
    capsule.next_steps = ["Run ollama pull gemma:2b"]
    return capsule


class TestCapsuleGeneration:
    def test_generates_json_file(self, tmp_path):
        capsule = _make_full_capsule(tmp_path)
        json_path, md_path = generate_capsule_files(capsule, str(tmp_path / "reports"))
        assert Path(json_path).exists()

    def test_generates_md_file(self, tmp_path):
        capsule = _make_full_capsule(tmp_path)
        json_path, md_path = generate_capsule_files(capsule, str(tmp_path / "reports"))
        assert Path(md_path).exists()

    def test_json_is_valid(self, tmp_path):
        capsule = _make_full_capsule(tmp_path)
        json_path, _ = generate_capsule_files(capsule, str(tmp_path / "reports"))
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_json_has_required_fields(self, tmp_path):
        capsule = _make_full_capsule(tmp_path)
        json_path, _ = generate_capsule_files(capsule, str(tmp_path / "reports"))
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        for field in ["schema_version", "run_id", "timestamp_utc", "overall_status",
                      "project", "environment", "finding", "model", "review",
                      "verification", "hermes"]:
            assert field in data, f"Missing field: {field}"

    def test_md_is_non_empty(self, tmp_path):
        capsule = _make_full_capsule(tmp_path)
        _, md_path = generate_capsule_files(capsule, str(tmp_path / "reports"))
        content = Path(md_path).read_text(encoding="utf-8")
        assert len(content) > 200

    def test_md_contains_finding_id(self, tmp_path):
        capsule = _make_full_capsule(tmp_path)
        _, md_path = generate_capsule_files(capsule, str(tmp_path / "reports"))
        content = Path(md_path).read_text(encoding="utf-8")
        assert "FND-TEST0001" in content

    def test_json_and_md_from_same_run_id(self, tmp_path):
        capsule = _make_full_capsule(tmp_path)
        json_path, md_path = generate_capsule_files(capsule, str(tmp_path / "reports"))
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        md_content = Path(md_path).read_text(encoding="utf-8")
        assert data["run_id"] in md_content

    def test_blocked_status_in_json(self, tmp_path):
        capsule = _make_full_capsule(tmp_path)
        capsule.blockers = ["Critical blocker"]
        capsule.baseline_checks = []  # no passes
        json_path, _ = generate_capsule_files(capsule, str(tmp_path / "reports"))
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        # Status should reflect blocker
        assert data["overall_status"] in {"PARTIAL", "BLOCKED", "FAIL"}

    def test_output_dir_created_if_missing(self, tmp_path):
        capsule = _make_full_capsule(tmp_path)
        out = tmp_path / "newdir" / "nested"
        generate_capsule_files(capsule, str(out))
        assert out.exists()


class TestSchemaValidation:
    def test_valid_capsule_passes(self, tmp_path):
        capsule = _make_full_capsule(tmp_path)
        json_path, _ = generate_capsule_files(capsule, str(tmp_path / "reports"))
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        result = validate_capsule(data)
        assert result.valid, f"Unexpected errors: {result.errors}"

    def test_invalid_capsule_fails(self):
        bad_data = {"schema_version": "1.0.0"}  # missing many required fields
        result = validate_capsule(bad_data)
        assert not result.valid
        assert len(result.errors) > 0

    def test_invalid_overall_status_fails(self, tmp_path):
        capsule = _make_full_capsule(tmp_path)
        json_path, _ = generate_capsule_files(capsule, str(tmp_path / "reports"))
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        data["overall_status"] = "UNKNOWN_STATUS"
        result = validate_capsule(data)
        assert not result.valid

    def test_validation_result_str(self):
        vr = ValidationResult(valid=True, validator_used="test")
        assert "VALID" in str(vr)
        vr2 = ValidationResult(valid=False, errors=["missing x"], validator_used="test")
        assert "INVALID" in str(vr2)
