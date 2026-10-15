"""Shared fixtures for the Enigma test suite."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


VALID_PYPROJECT = """\
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "testproject"
version = "1.2.3"
requires-python = ">=3.10"
classifiers = [
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
]
dependencies = [
    "pydantic>=2",
    "requests==2.31.0",
    "six",
    "Jinja2==2.11.3",
]
"""

VALID_REQUIREMENTS = """\
pydantic==1.10.13
requests==2.31.0
six
Jinja2==2.11.3
"""

VALID_CONFIG_PY_V1 = """\
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


def load_settings(path="sites.toml"):
    data = toml.load(path)
    return Settings(**data)
"""

MALFORMED_PYPROJECT = """\
[project
name = "broken"
"""


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a minimal synthetic repository for testing."""
    (tmp_path / "pyproject.toml").write_text(VALID_PYPROJECT, encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(VALID_REQUIREMENTS, encoding="utf-8")
    pkg = tmp_path / "mypackage"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "config.py").write_text(VALID_CONFIG_PY_V1, encoding="utf-8")
    return tmp_path


@pytest.fixture
def empty_repo(tmp_path: Path) -> Path:
    """An empty directory — no files."""
    return tmp_path


@pytest.fixture
def malformed_repo(tmp_path: Path) -> Path:
    """Repository with malformed pyproject.toml."""
    (tmp_path / "pyproject.toml").write_text(MALFORMED_PYPROJECT, encoding="utf-8")
    return tmp_path


@pytest.fixture
def linkwatch_repo() -> Path | None:
    """Return the real LinkWatch path if available, else None."""
    candidates = [
        Path(__file__).parent.parent / "linkwatch",
        Path("linkwatch"),
    ]
    for p in candidates:
        if p.exists() and (p / "pyproject.toml").exists():
            return p.resolve()
    return None
