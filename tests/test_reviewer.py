"""Tests for enigma.reviewer — Stage D: Review and controlled maintenance."""

from __future__ import annotations

from pathlib import Path

import pytest

from enigma.finding import Finding
from enigma.inspector import EvidenceRef
from enigma.model_adapter import ModelResult
from enigma.reviewer import (
    ReviewResult,
    _compute_changes,
    _migrate_config_py,
    _migrate_requirements_txt,
    review_and_apply,
)


PYDANTIC_V1_CONFIG = """\
from typing import List
import toml
from pydantic import BaseModel, validator


class Site(BaseModel):
    name: str
    url: str

    class Config:
        anystr_strip_whitespace = True

    @validator("name")
    def name_not_empty(cls, value):
        if not value:
            raise ValueError("site name can not be empty")
        return value


class Settings(BaseModel):
    title: str = "linkwatch"
    sites: List[Site] = []

    class Config:
        extra = "forbid"
"""


def _make_finding() -> Finding:
    return Finding(
        title="Pydantic v1/v2 conflict",
        description="test",
        classification="DEPENDENCY_VERSION_CONFLICT",
        severity="HIGH",
        affected_files=["/fake/config.py"],
        evidence=[EvidenceRef("/fake/config.py", 5, "@validator", "OBSERVED")],
        expected_outcome="v2 compat",
        proposed_action="migrate",
        confidence=0.97,
        uncertainty="minor",
    )


def _make_blocked_model() -> ModelResult:
    return ModelResult(status="BLOCKED", blocker_reason="no ollama")


class TestMigrateConfigPy:
    def test_validator_replaced_with_field_validator(self):
        result = _migrate_config_py(PYDANTIC_V1_CONFIG)
        assert "field_validator" in result
        assert "@validator" not in result

    def test_import_updated(self):
        result = _migrate_config_py(PYDANTIC_V1_CONFIG)
        assert "ConfigDict" in result or "field_validator" in result

    def test_class_config_replaced(self):
        result = _migrate_config_py(PYDANTIC_V1_CONFIG)
        assert "model_config" in result or "ConfigDict" in result

    def test_anystr_strip_whitespace_removed(self):
        result = _migrate_config_py(PYDANTIC_V1_CONFIG)
        assert "anystr_strip_whitespace" not in result

    def test_output_differs_from_input(self):
        result = _migrate_config_py(PYDANTIC_V1_CONFIG)
        assert result != PYDANTIC_V1_CONFIG

    def test_idempotent_on_already_migrated(self):
        first = _migrate_config_py(PYDANTIC_V1_CONFIG)
        second = _migrate_config_py(first)
        # Should not regress
        assert "field_validator" in second


class TestMigrateRequirementsTxt:
    def test_pydantic_v1_replaced(self):
        req = "requests==2.31.0\npydantic==1.10.13\nsix\n"
        result = _migrate_requirements_txt(req)
        assert "pydantic>=2,<3" in result
        assert "pydantic==1.10.13" not in result

    def test_other_deps_unchanged(self):
        req = "requests==2.31.0\npydantic==1.10.13\nsix\n"
        result = _migrate_requirements_txt(req)
        assert "requests==2.31.0" in result
        assert "six" in result


class TestComputeChanges:
    def test_changes_detected_for_v1_repo(self, tmp_path):
        pkg = tmp_path / "linkwatch"
        pkg.mkdir()
        (pkg / "config.py").write_text(PYDANTIC_V1_CONFIG, encoding="utf-8")
        (tmp_path / "requirements.txt").write_text(
            "pydantic==1.10.13\nrequests==2.31.0\n", encoding="utf-8"
        )
        changes = _compute_changes(tmp_path)
        assert len(changes) >= 1

    def test_no_changes_when_already_migrated(self, tmp_path):
        pkg = tmp_path / "linkwatch"
        pkg.mkdir()
        migrated = _migrate_config_py(PYDANTIC_V1_CONFIG)
        (pkg / "config.py").write_text(migrated, encoding="utf-8")
        # requirements already updated
        (tmp_path / "requirements.txt").write_text(
            "pydantic>=2,<3\nrequests==2.31.0\n", encoding="utf-8"
        )
        changes = _compute_changes(tmp_path)
        assert changes == []


class TestReviewAndApply:
    def test_dry_run_does_not_modify_files(self, tmp_path):
        pkg = tmp_path / "linkwatch"
        pkg.mkdir()
        config_path = pkg / "config.py"
        config_path.write_text(PYDANTIC_V1_CONFIG, encoding="utf-8")
        (tmp_path / "requirements.txt").write_text("pydantic==1.10.13\n", encoding="utf-8")

        original = config_path.read_text(encoding="utf-8")
        review_and_apply(
            _make_finding(), _make_blocked_model(),
            str(tmp_path), dry_run=True,
        )
        assert config_path.read_text(encoding="utf-8") == original

    def test_auto_approve_modifies_files(self, tmp_path):
        pkg = tmp_path / "linkwatch"
        pkg.mkdir()
        config_path = pkg / "config.py"
        config_path.write_text(PYDANTIC_V1_CONFIG, encoding="utf-8")
        (tmp_path / "requirements.txt").write_text("pydantic==1.10.13\n", encoding="utf-8")

        result = review_and_apply(
            _make_finding(), _make_blocked_model(),
            str(tmp_path), dry_run=False, auto_approve=True,
        )
        assert result.approved is True
        new_content = config_path.read_text(encoding="utf-8")
        assert "field_validator" in new_content or "@validator" not in new_content

    def test_backup_created_on_apply(self, tmp_path):
        pkg = tmp_path / "linkwatch"
        pkg.mkdir()
        config_path = pkg / "config.py"
        config_path.write_text(PYDANTIC_V1_CONFIG, encoding="utf-8")
        (tmp_path / "requirements.txt").write_text("pydantic==1.10.13\n", encoding="utf-8")

        review_and_apply(
            _make_finding(), _make_blocked_model(),
            str(tmp_path), dry_run=False, auto_approve=True,
        )
        assert config_path.with_suffix(".py.bak").exists()

    def test_unrelated_files_unchanged(self, tmp_path):
        pkg = tmp_path / "linkwatch"
        pkg.mkdir()
        (pkg / "config.py").write_text(PYDANTIC_V1_CONFIG, encoding="utf-8")
        (tmp_path / "requirements.txt").write_text("pydantic==1.10.13\n", encoding="utf-8")
        unrelated = tmp_path / "unrelated.py"
        unrelated.write_text("x = 1\n", encoding="utf-8")

        review_and_apply(
            _make_finding(), _make_blocked_model(),
            str(tmp_path), dry_run=False, auto_approve=True,
        )
        assert unrelated.read_text(encoding="utf-8") == "x = 1\n"
