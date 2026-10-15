"""Tests for enigma.inspector — Stage A: Deterministic inspection."""

from __future__ import annotations

from pathlib import Path

import pytest

from enigma.inspector import inspect_repository


def test_valid_repo_returns_pyproject_path(tmp_repo):
    result = inspect_repository(str(tmp_repo))
    assert result.pyproject_path is not None
    assert Path(result.pyproject_path).name == "pyproject.toml"


def test_valid_repo_parses_dependencies(tmp_repo):
    result = inspect_repository(str(tmp_repo))
    assert "pydantic" in result.pyproject_deps
    assert "requests" in result.pyproject_deps


def test_valid_repo_parses_requirements(tmp_repo):
    result = inspect_repository(str(tmp_repo))
    assert "pydantic" in result.requirements_deps
    assert result.requirements_deps["pydantic"] == "==1.10.13"


def test_valid_repo_detects_classifiers(tmp_repo):
    result = inspect_repository(str(tmp_repo))
    assert any("3.8" in c for c in result.classifiers)


def test_valid_repo_has_evidence(tmp_repo):
    result = inspect_repository(str(tmp_repo))
    assert len(result.evidence) > 0


def test_evidence_has_file_and_line(tmp_repo):
    result = inspect_repository(str(tmp_repo))
    for e in result.evidence:
        assert e.file_path
        # line_number may be None for some evidence items but file_path always set
        assert e.excerpt


def test_pydantic_v1_api_detected(tmp_repo):
    result = inspect_repository(str(tmp_repo))
    excerpts = [e.excerpt for e in result.evidence]
    # Should detect @validator and class Config
    assert any("validator" in x.lower() for x in excerpts)


def test_missing_directory_returns_error():
    result = inspect_repository("/nonexistent/path/12345")
    assert len(result.errors) > 0
    assert "not exist" in result.errors[0].lower() or "error" in result.errors[0].lower()


def test_malformed_pyproject_captured(malformed_repo):
    result = inspect_repository(str(malformed_repo))
    assert len(result.errors) > 0


def test_empty_repo_no_crash(empty_repo):
    result = inspect_repository(str(empty_repo))
    # Should not raise; errors captured instead
    assert isinstance(result.errors, list)


def test_skips_git_dir(tmp_repo):
    # Create a fake .git file to ensure we don't scan it
    git_dir = tmp_repo / ".git"
    git_dir.mkdir(exist_ok=True)
    (git_dir / "config.py").write_text("import evil_thing", encoding="utf-8")
    result = inspect_repository(str(tmp_repo))
    # Evidence from .git should not appear
    for e in result.evidence:
        assert ".git" not in e.file_path.replace("\\", "/").split("/")


def test_real_linkwatch(linkwatch_repo):
    if linkwatch_repo is None:
        pytest.skip("LinkWatch repo not found")
    result = inspect_repository(str(linkwatch_repo))
    assert result.pyproject_path is not None
    assert "pydantic" in result.pyproject_deps or "pydantic" in result.requirements_deps
    # The key finding: pydantic version conflict evidence
    pydantic_evidence = [e for e in result.evidence if "pydantic" in e.excerpt.lower()]
    assert len(pydantic_evidence) >= 1
