"""Tests for enigma.workflow — End-to-end workflow integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from enigma.model_adapter import ModelResult

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
            raise ValueError("empty")
        return value


class Settings(BaseModel):
    title: str = "linkwatch"
    sites: List[Site] = []

    class Config:
        extra = "forbid"
"""

VALID_PYPROJECT = """\
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "linkwatch"
version = "0.3.1"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2",
    "requests==2.31.0",
]
"""

VALID_REQUIREMENTS = "pydantic==1.10.13\nrequests==2.31.0\n"


def _make_fixture_repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    pkg = tmp_path / "linkwatch"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "config.py").write_text(PYDANTIC_V1_CONFIG, encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(VALID_PYPROJECT, encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(VALID_REQUIREMENTS, encoding="utf-8")
    return tmp_path


def _blocked_model():
    return ModelResult(status="BLOCKED", blocker_reason="no ollama in tests")


class TestWorkflowDryRun:
    def test_dry_run_produces_capsule_files(self, tmp_path):
        repo = _make_fixture_repo(tmp_path / "repo")
        out_dir = str(tmp_path / "reports")

        with patch("enigma.workflow.get_recommendation", return_value=_blocked_model()), \
             patch("enigma.workflow._ensure_deps", return_value=None), \
             patch("enigma.verifier.run_check") as mock_check:
            from enigma.verifier import CheckResult
            mock_check.return_value = CheckResult(
                label="mock", command=["python", "-c", "pass"],
                cwd=str(repo), interpreter="Python 3.12.0",
                exit_code=0, status="PASS", elapsed_seconds=0.1,
            )
            from enigma.workflow import run_workflow
            capsule, json_path, md_path = run_workflow(
                target_repo=str(repo),
                dry_run=True,
                output_dir=out_dir,
            )

        assert Path(json_path).exists()
        assert Path(md_path).exists()

    def test_dry_run_does_not_modify_repo(self, tmp_path):
        repo = _make_fixture_repo(tmp_path / "repo")
        config_before = (repo / "linkwatch" / "config.py").read_text(encoding="utf-8")
        out_dir = str(tmp_path / "reports")

        with patch("enigma.workflow.get_recommendation", return_value=_blocked_model()), \
             patch("enigma.workflow._ensure_deps", return_value=None), \
             patch("enigma.verifier.run_check") as mock_check:
            from enigma.verifier import CheckResult
            mock_check.return_value = CheckResult(
                label="mock", command=["python", "-c", "pass"],
                cwd=str(repo), interpreter="Python 3.12.0",
                exit_code=0, status="PASS", elapsed_seconds=0.1,
            )
            from enigma.workflow import run_workflow
            run_workflow(target_repo=str(repo), dry_run=True, output_dir=out_dir)

        config_after = (repo / "linkwatch" / "config.py").read_text(encoding="utf-8")
        assert config_before == config_after

    def test_json_capsule_is_valid_json(self, tmp_path):
        repo = _make_fixture_repo(tmp_path / "repo")
        out_dir = str(tmp_path / "reports")

        with patch("enigma.workflow.get_recommendation", return_value=_blocked_model()), \
             patch("enigma.workflow._ensure_deps", return_value=None), \
             patch("enigma.verifier.run_check") as mock_check:
            from enigma.verifier import CheckResult
            mock_check.return_value = CheckResult(
                label="mock", command=["python", "-c", "pass"],
                cwd=str(repo), interpreter="Python 3.12.0",
                exit_code=0, status="PASS", elapsed_seconds=0.1,
            )
            from enigma.workflow import run_workflow
            _, json_path, _ = run_workflow(
                target_repo=str(repo), dry_run=True, output_dir=out_dir
            )

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["finding"] is not None
        assert data["overall_status"] in {"PASS", "PARTIAL", "FAIL", "BLOCKED"}

    def test_schema_validates_capsule(self, tmp_path):
        repo = _make_fixture_repo(tmp_path / "repo")
        out_dir = str(tmp_path / "reports")

        with patch("enigma.workflow.get_recommendation", return_value=_blocked_model()), \
             patch("enigma.workflow._ensure_deps", return_value=None), \
             patch("enigma.verifier.run_check") as mock_check:
            from enigma.verifier import CheckResult
            mock_check.return_value = CheckResult(
                label="mock", command=["python", "-c", "pass"],
                cwd=str(repo), interpreter="Python 3.12.0",
                exit_code=0, status="PASS", elapsed_seconds=0.1,
            )
            from enigma.workflow import run_workflow
            _, json_path, _ = run_workflow(
                target_repo=str(repo), dry_run=True, output_dir=out_dir
            )

        from enigma.schema import validate_capsule
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        result = validate_capsule(data)
        assert result.valid, f"Schema errors: {result.errors}"
